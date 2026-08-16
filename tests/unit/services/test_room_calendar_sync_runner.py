from datetime import date, datetime, timedelta
from pathlib import Path
import subprocess
import sys
import time

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.core.file_locks import FileLockManager
from backend.core.operation_result import OperationResult
from backend.database.base import Base
from backend.models.booking import Booking
from backend.models.platform import Platform
from backend.models.property import Property
from backend.models.room import Room
from backend.models.room_calendar import RoomCalendar
from backend.services.room_calendar_sync_runner import RoomCalendarSyncRunner


NOW = datetime(2026, 8, 16, 12, 0)


def seed_calendar(db, suffix="one"):
    property_obj = Property(
        name=f"Property {suffix}", address="Address", city="Madrid",
        owner="Owner", active=True,
    )
    db.add(property_obj)
    db.flush()
    room = Room(
        property_id=property_obj.id, code=f"R-{suffix}", display_order=1,
        base_price=500, active=True,
    )
    platform = Platform(
        name=f"Platform {suffix}", slug=f"platform-{suffix}", active=True,
        supports_import=True, supports_export=True,
    )
    db.add_all([room, platform])
    db.flush()
    calendar = RoomCalendar(
        room_id=room.id, platform_id=platform.id,
        import_url=f"https://calendar.example/{suffix}.ics", active=True,
    )
    db.add(calendar)
    db.commit()
    return room, calendar


class ResultService:
    def __init__(self, results):
        self.results = results
        self.calls = []

    def synchronize(self, db, calendar_id):
        self.calls.append(calendar_id)
        result = self.results[calendar_id]
        if result.success:
            calendar = db.get(RoomCalendar, calendar_id)
            calendar.last_sync_at = NOW
            db.commit()
        else:
            db.rollback()
        return result


def test_frequency_backoff_intervention_and_overdue(db_session, tmp_path):
    _room, calendar = seed_calendar(db_session)
    runner = RoomCalendarSyncRunner(
        lock_manager=FileLockManager(tmp_path), now_factory=lambda: NOW
    )
    assert runner.is_due(calendar)

    calendar.last_sync_attempt_at = NOW - timedelta(minutes=9)
    calendar.last_sync_status = "ok"
    assert not runner.is_due(calendar)
    calendar.last_sync_attempt_at = NOW - timedelta(minutes=10)
    assert runner.is_due(calendar)

    calendar.last_sync_status = "error"
    calendar.last_sync_error = "room_calendar_sync_timeout"
    for failures, minutes in ((1, 10), (2, 20), (3, 40), (4, 60), (8, 60)):
        calendar.consecutive_failures = failures
        calendar.last_sync_attempt_at = NOW - timedelta(minutes=minutes)
        assert runner.is_due(calendar)

    calendar.last_sync_error = "room_calendar_sync_rate_limited"
    calendar.last_sync_attempt_at = NOW - timedelta(minutes=59)
    assert not runner.is_due(calendar)
    calendar.last_sync_attempt_at = NOW - timedelta(minutes=60)
    assert runner.is_due(calendar)

    calendar.last_sync_error = "room_calendar_sync_invalid_feed"
    assert not runner.is_due(calendar)
    calendar.last_sync_status = "ok"
    calendar.last_sync_attempt_at = NOW - timedelta(minutes=31)
    assert runner.is_overdue(calendar)


def test_status_survives_failure_rollback_and_success_recovers(
    db_session, tmp_path
):
    room, calendar = seed_calendar(db_session)

    class FailingService:
        def synchronize(self, db, calendar_id):
            db.add(Booking(
                room_id=room.id, room_calendar_id=calendar_id,
                origin="platform-one", external_reference="ROLLBACK",
                check_in=date(2026, 9, 1), check_out=date(2026, 9, 5),
            ))
            db.flush()
            db.rollback()
            return OperationResult(
                success=False, message="room_calendar_sync_invalid_feed"
            )

    runner = RoomCalendarSyncRunner(
        FailingService(), FileLockManager(tmp_path), lambda: NOW
    )
    failed = runner.synchronize(db_session, calendar.id)
    db_session.refresh(calendar)
    assert not failed.success
    assert db_session.scalar(select(Booking)) is None
    assert calendar.last_sync_attempt_at == NOW
    assert calendar.last_sync_at is None
    assert calendar.last_sync_status == "error"
    assert calendar.last_sync_error == "room_calendar_sync_invalid_feed"
    assert calendar.consecutive_failures == 1

    success_service = ResultService({
        calendar.id: OperationResult(
            success=True, message="room_calendar_sync_completed"
        )
    })
    runner.sync_service = success_service
    runner.now_factory = lambda: NOW + timedelta(hours=1)
    recovered = runner.synchronize(db_session, calendar.id)
    db_session.refresh(calendar)
    assert recovered.success
    assert calendar.last_sync_status == "ok"
    assert calendar.last_sync_error is None
    assert calendar.consecutive_failures == 0
    assert calendar.last_sync_at == NOW


def test_warning_is_successful_operational_state(db_session, tmp_path):
    _room, calendar = seed_calendar(db_session)
    service = ResultService({
        calendar.id: OperationResult(
            success=True,
            message="room_calendar_sync_completed_with_warnings",
        )
    })
    runner = RoomCalendarSyncRunner(
        service, FileLockManager(tmp_path), lambda: NOW
    )
    assert runner.synchronize(db_session, calendar.id).success
    db_session.refresh(calendar)
    assert calendar.last_sync_status == "warning"
    assert calendar.last_sync_at == NOW


def test_cycle_uses_independent_sessions_and_continues_after_failure(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'cycle.db').as_posix()}")
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(engine)
    setup = factory()
    _room1, first = seed_calendar(setup, "one")
    _room2, second = seed_calendar(setup, "two")
    _room3, paused = seed_calendar(setup, "paused")
    paused.automatic_sync_enabled = False
    setup.commit()
    first_id, second_id = first.id, second.id
    setup.close()
    service = ResultService({
        first_id: OperationResult(
            success=False, message="room_calendar_sync_timeout"
        ),
        second_id: OperationResult(
            success=True, message="room_calendar_sync_completed"
        ),
    })
    sessions = []

    def tracked_factory():
        session = factory()
        sessions.append(session)
        return session

    report = RoomCalendarSyncRunner(
        service, FileLockManager(tmp_path / "locks"), lambda: NOW
    ).run_cycle(tracked_factory)
    assert report.lock_acquired
    assert report.selected == report.attempted == 2
    assert report.failed == 1 and report.succeeded == 1
    assert service.calls == [first_id, second_id]
    assert len(sessions) == 3
    check = factory()
    assert check.get(RoomCalendar, first_id).last_sync_status == "error"
    assert check.get(RoomCalendar, second_id).last_sync_status == "ok"
    check.close()
    engine.dispose()


def test_unexpected_error_is_sanitized_and_recorded(
    db_session, tmp_path, monkeypatch
):
    log_calls = []
    monkeypatch.setattr(
        "backend.services.room_calendar_sync_runner.logger.error",
        lambda *args: log_calls.append(args),
    )
    _room, calendar = seed_calendar(db_session)

    class ExplodingService:
        def synchronize(self, _db, _calendar_id):
            raise RuntimeError(
                "https://calendar.example/private-token.ics sensitive body"
            )

    result = RoomCalendarSyncRunner(
        ExplodingService(), FileLockManager(tmp_path), lambda: NOW
    ).synchronize(db_session, calendar.id)
    db_session.refresh(calendar)
    assert result.message == "room_calendar_sync_unexpected_error"
    assert calendar.last_sync_error == "room_calendar_sync_unexpected_error"
    logged = repr(log_calls)
    assert "private-token" not in logged
    assert "sensitive body" not in logged
    assert "RuntimeError" in logged


def test_global_and_calendar_locks_skip_competing_work(db_session, tmp_path):
    _room, calendar = seed_calendar(db_session)
    manager = FileLockManager(tmp_path)
    service = ResultService({
        calendar.id: OperationResult(
            success=True, message="room_calendar_sync_completed"
        )
    })
    runner = RoomCalendarSyncRunner(service, manager, lambda: NOW)
    with manager.acquire(f"room_calendar_{calendar.id}") as acquired:
        assert acquired
        result = runner.synchronize(db_session, calendar.id)
        assert result.message == "room_calendar_sync_in_progress"
        assert service.calls == []

    with manager.acquire("ical_automatic_cycle") as acquired:
        assert acquired
        report = runner.run_cycle(lambda: db_session)
        assert not report.lock_acquired


def test_file_lock_is_cross_process_and_released_after_termination(tmp_path):
    directory = Path(tmp_path) / "process-locks"
    code = (
        "import sys,time; from pathlib import Path; "
        "from backend.core.file_locks import FileLockManager; "
        f"m=FileLockManager(Path({str(directory)!r})); "
        "ctx=m.acquire('shared'); acquired=ctx.__enter__(); "
        "print('READY' if acquired else 'FAILED',flush=True); time.sleep(60)"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", code],
        cwd=Path.cwd(), stdout=subprocess.PIPE, text=True,
    )
    try:
        assert process.stdout.readline().strip() == "READY"
        with FileLockManager(directory).acquire("shared") as acquired:
            assert not acquired
    finally:
        process.terminate()
        process.wait(timeout=10)
    deadline = time.monotonic() + 2
    acquired = False
    while not acquired and time.monotonic() < deadline:
        with FileLockManager(directory).acquire("shared") as acquired:
            if not acquired:
                time.sleep(0.05)
    assert acquired
