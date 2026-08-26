from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import logging

from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session

from backend.core.file_locks import FileLockManager
from backend.core.ical_sync_config import (
    MAX_BACKOFF_MINUTES,
    backoff_minutes,
    sync_interval_minutes,
)
from backend.core.operation_result import OperationResult
from backend.repositories.room_calendar_repository import RoomCalendarRepository
from backend.services.ical_sync_service import IcalSyncService


logger = logging.getLogger(__name__)

TEMPORARY_ERRORS = {
    "room_calendar_sync_timeout",
    "room_calendar_sync_download_failed",
    "room_calendar_sync_http_server_error",
    "room_calendar_sync_rate_limited",
    "room_calendar_sync_database_locked",
}

ERROR_MESSAGES = {
    "room_calendar_sync_timeout": "La descarga agotó el tiempo disponible.",
    "room_calendar_sync_download_failed": "No se pudo conectar con el calendario externo.",
    "room_calendar_sync_http_server_error": "La plataforma devolvió un error temporal.",
    "room_calendar_sync_rate_limited": "La plataforma ha limitado temporalmente las consultas.",
    "room_calendar_sync_http_access_error": "La plataforma rechazó el acceso a la URL configurada.",
    "room_calendar_sync_http_error": "La plataforma rechazó la solicitud del calendario.",
    "room_calendar_sync_too_large": "El calendario supera el tamaño permitido.",
    "room_calendar_sync_too_many_redirects": "La URL produce demasiadas redirecciones.",
    "room_calendar_sync_too_many_events": "El calendario supera el número máximo de eventos.",
    "room_calendar_sync_unsafe_url": "La URL apunta a un destino de red no permitido.",
    "room_calendar_sync_invalid_feed": "El contenido recibido no es un calendario válido.",
    "room_calendar_sync_recurrence_not_supported": "El calendario contiene recurrencias no admitidas.",
    "room_calendar_sync_incompatible_stay": "El calendario contiene una estancia incompatible.",
    "room_calendar_sync_overlap": "El calendario se solapa con otra reserva.",
    "room_calendar_sync_failed": "La sincronización no pudo aplicarse.",
    "room_calendar_inactive": "El calendario está inactivo.",
    "room_calendar_room_inactive": "La habitación está archivada.",
    "room_calendar_platform_inactive": "La plataforma está inactiva.",
    "room_calendar_import_not_supported": "La importación no está disponible.",
    "room_calendar_sync_database_locked": "La base de datos estaba ocupada; se intentará más tarde.",
    "room_calendar_sync_database_error": "Se produjo un error de base de datos.",
    "room_calendar_sync_unexpected_error": "Se produjo un error inesperado.",
}


@dataclass(frozen=True)
class AutomaticSyncCycleReport:
    lock_acquired: bool
    selected: int = 0
    attempted: int = 0
    succeeded: int = 0
    warnings: int = 0
    failed: int = 0
    skipped_locked: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


class RoomCalendarSyncRunner:
    def __init__(
        self,
        sync_service: IcalSyncService | None = None,
        lock_manager: FileLockManager | None = None,
        now_factory=None,
    ):
        self.sync_service = sync_service or IcalSyncService()
        self.lock_manager = lock_manager or FileLockManager()
        self.now_factory = now_factory or (
            lambda: datetime.now(timezone.utc).replace(tzinfo=None)
        )
        self.repository = RoomCalendarRepository()

    @staticmethod
    def _is_database_locked(error: OperationalError) -> bool:
        return "database is locked" in str(error.orig).casefold()

    @staticmethod
    def error_message(code: str | None) -> str | None:
        return ERROR_MESSAGES.get(code) if code else None

    @staticmethod
    def _safe_error_code(code: str) -> str:
        return (
            code
            if code in ERROR_MESSAGES
            else "room_calendar_sync_unexpected_error"
        )

    def is_due(self, calendar, now: datetime | None = None) -> bool:
        if (
            not calendar.room.active
            or not calendar.active
            or not calendar.automatic_sync_enabled
            or not calendar.import_url
        ):
            return False
        now = now or self.now_factory()
        if calendar.last_sync_attempt_at is None:
            return True
        if calendar.last_sync_status == "error":
            if calendar.last_sync_error not in TEMPORARY_ERRORS:
                return False
            delay = (
                MAX_BACKOFF_MINUTES
                if calendar.last_sync_error == "room_calendar_sync_rate_limited"
                else backoff_minutes(calendar.consecutive_failures)
            )
        else:
            delay = sync_interval_minutes(calendar.platform.slug)
        return calendar.last_sync_attempt_at + timedelta(minutes=delay) <= now

    def is_overdue(self, calendar, now: datetime | None = None) -> bool:
        if (
            not calendar.room.active
            or not calendar.active
            or not calendar.automatic_sync_enabled
            or not calendar.import_url
            or calendar.last_sync_attempt_at is None
        ):
            return False
        now = now or self.now_factory()
        threshold = sync_interval_minutes(calendar.platform.slug) * 3
        return calendar.last_sync_attempt_at + timedelta(minutes=threshold) < now

    def health_state(self, calendar, now: datetime | None = None) -> str:
        """Return the concise operational state used by read-only UI summaries."""
        if not calendar.room.active:
            return "room_archived"
        if not calendar.active:
            return "inactive"
        if not calendar.platform.active:
            return "platform_inactive"
        if not calendar.automatic_sync_enabled:
            return "paused"
        if calendar.last_sync_status == "error":
            return "error"
        if calendar.last_sync_at is None:
            return "never_synced"
        if self.is_overdue(calendar, now=now):
            return "overdue"
        return "ok"

    def _record_result(
        self,
        db: Session,
        calendar_id: int,
        result: OperationResult,
        attempted_at: datetime,
    ) -> None:
        db.rollback()
        calendar = self.repository.get_by_id(db, calendar_id)
        if calendar is None:
            return
        calendar.last_sync_attempt_at = attempted_at
        if result.success:
            calendar.last_sync_status = (
                "warning"
                if result.message == "room_calendar_sync_completed_with_warnings"
                else "ok"
            )
            calendar.last_sync_error = None
            calendar.consecutive_failures = 0
        else:
            calendar.last_sync_status = "error"
            calendar.last_sync_error = self._safe_error_code(result.message)
            calendar.consecutive_failures += 1
        self.repository.update(db, calendar)
        db.commit()

    def synchronize(self, db: Session, calendar_id: int) -> OperationResult:
        with self.lock_manager.acquire(f"room_calendar_{calendar_id}") as acquired:
            if not acquired:
                return OperationResult(
                    success=False,
                    message="room_calendar_sync_in_progress",
                )
            attempted_at = self.now_factory()
            try:
                result = self.sync_service.synchronize(db, calendar_id)
            except OperationalError as error:
                db.rollback()
                code = (
                    "room_calendar_sync_database_locked"
                    if self._is_database_locked(error)
                    else "room_calendar_sync_database_error"
                )
                result = OperationResult(success=False, message=code)
            except SQLAlchemyError:
                db.rollback()
                result = OperationResult(
                    success=False,
                    message="room_calendar_sync_database_error",
                )
            except Exception as error:
                db.rollback()
                logger.error(
                    "Unexpected iCal synchronization failure calendar_id=%s type=%s",
                    calendar_id,
                    type(error).__name__,
                )
                result = OperationResult(
                    success=False,
                    message="room_calendar_sync_unexpected_error",
                )
            try:
                self._record_result(db, calendar_id, result, attempted_at)
            except SQLAlchemyError as error:
                db.rollback()
                logger.error(
                    "Could not persist iCal status calendar_id=%s type=%s",
                    calendar_id,
                    type(error).__name__,
                )
            return result

    def run_cycle(self, session_factory) -> AutomaticSyncCycleReport:
        with self.lock_manager.acquire("ical_automatic_cycle") as acquired:
            if not acquired:
                return AutomaticSyncCycleReport(lock_acquired=False)
            selection_session = session_factory()
            try:
                now = self.now_factory()
                candidates = self.repository.list_automatic_candidates(
                    selection_session
                )
                calendar_ids = [
                    calendar.id
                    for calendar in candidates
                    if self.is_due(calendar, now)
                ]
            finally:
                selection_session.close()

            attempted = succeeded = warnings = failed = skipped = 0
            for calendar_id in calendar_ids:
                db = session_factory()
                try:
                    result = self.synchronize(db, calendar_id)
                finally:
                    db.close()
                if result.message == "room_calendar_sync_in_progress":
                    skipped += 1
                    continue
                attempted += 1
                if result.success:
                    succeeded += 1
                    if result.message == "room_calendar_sync_completed_with_warnings":
                        warnings += 1
                else:
                    failed += 1
                logger.info(
                    "Automatic iCal result calendar_id=%s success=%s code=%s",
                    calendar_id,
                    result.success,
                    result.message,
                )
            return AutomaticSyncCycleReport(
                lock_acquired=True,
                selected=len(calendar_ids),
                attempted=attempted,
                succeeded=succeeded,
                warnings=warnings,
                failed=failed,
                skipped_locked=skipped,
            )
