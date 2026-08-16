import json

from backend.cli import sync_calendars
from backend.services.room_calendar_sync_runner import AutomaticSyncCycleReport


def test_cli_reports_safe_summary_and_success(monkeypatch, capsys):
    class Runner:
        def run_cycle(self, _factory):
            return AutomaticSyncCycleReport(
                lock_acquired=True,
                selected=2,
                attempted=2,
                succeeded=1,
                failed=1,
            )

    monkeypatch.setattr(sync_calendars, "RoomCalendarSyncRunner", Runner)
    assert sync_calendars.main() == 0
    output = capsys.readouterr().out
    assert json.loads(output) == {
        "attempted": 2,
        "failed": 1,
        "lock_acquired": True,
        "selected": 2,
        "skipped_locked": 0,
        "succeeded": 1,
        "warnings": 0,
    }
    assert "http" not in output and "token" not in output


def test_cli_returns_distinct_code_when_cycle_is_already_running(
    monkeypatch, capsys
):
    class Runner:
        def run_cycle(self, _factory):
            return AutomaticSyncCycleReport(lock_acquired=False)

    monkeypatch.setattr(sync_calendars, "RoomCalendarSyncRunner", Runner)
    assert sync_calendars.main() == 2
    assert json.loads(capsys.readouterr().out)["lock_acquired"] is False


def test_cli_fatal_log_does_not_include_exception_message(
    monkeypatch, caplog
):
    class Runner:
        def run_cycle(self, _factory):
            raise RuntimeError(
                "https://calendar.example/private-token.ics secret body"
            )

    monkeypatch.setattr(sync_calendars, "RoomCalendarSyncRunner", Runner)
    assert sync_calendars.main() == 1
    assert "private-token" not in caplog.text
    assert "secret body" not in caplog.text
    assert "RuntimeError" in caplog.text
