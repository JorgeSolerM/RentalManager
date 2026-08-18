from dataclasses import dataclass
from datetime import datetime, timedelta


MASTER_CALENDAR_RECURRENCE_MIN_GAP = timedelta(minutes=10)
MASTER_CALENDAR_RECENCY_WINDOW = timedelta(hours=48)


@dataclass(frozen=True)
class MasterCalendarEvidence:
    state: str
    recurrent: bool
    recent: bool


def master_calendar_evidence(calendar, now: datetime) -> MasterCalendarEvidence:
    first = calendar.master_calendar_first_request_at
    last = calendar.last_master_calendar_request_at
    count = calendar.master_calendar_request_count or 0
    if last is None or count == 0:
        return MasterCalendarEvidence("never", False, False)
    recurrent = bool(
        count >= 2
        and first is not None
        and last - first >= MASTER_CALENDAR_RECURRENCE_MIN_GAP
    )
    if not recurrent:
        return MasterCalendarEvidence("isolated", False, True)
    recent = now - last <= MASTER_CALENDAR_RECENCY_WINDOW
    return MasterCalendarEvidence(
        "recurrent_recent" if recent else "recurrent_stale",
        True,
        recent,
    )


def master_calendar_evidence_label(evidence: MasterCalendarEvidence) -> str:
    labels = {
        "never": "Aún no se han observado consultas externas",
        "isolated": "Aún no se ha observado consumo recurrente del calendario maestro",
        "recurrent_recent": "Calendario maestro consultado recientemente",
        "recurrent_stale": "El calendario maestro dejó de consultarse recientemente",
    }
    return labels[evidence.state]
