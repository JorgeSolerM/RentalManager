import json
import logging

from backend.database.session import SessionLocal
from backend.services.room_calendar_sync_runner import RoomCalendarSyncRunner


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        report = RoomCalendarSyncRunner().run_cycle(SessionLocal)
    except Exception as error:
        logging.error(
            "Automatic iCal cycle failed type=%s", type(error).__name__
        )
        return 1
    print(json.dumps(report.to_dict(), sort_keys=True))
    return 0 if report.lock_acquired else 2


if __name__ == "__main__":
    raise SystemExit(main())
