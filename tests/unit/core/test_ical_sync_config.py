from backend.core.ical_sync_config import sync_interval_minutes


def test_default_and_future_per_platform_frequency(monkeypatch):
    monkeypatch.delenv("ICAL_SYNC_INTERVAL_MINUTES", raising=False)
    monkeypatch.delenv(
        "ICAL_SYNC_INTERVAL_HOUSING_ANYWHERE_MINUTES", raising=False
    )
    assert sync_interval_minutes("housing-anywhere") == 10

    monkeypatch.setenv("ICAL_SYNC_INTERVAL_MINUTES", "15")
    assert sync_interval_minutes("spotahome") == 15

    monkeypatch.setenv("ICAL_SYNC_INTERVAL_HOUSING_ANYWHERE_MINUTES", "20")
    assert sync_interval_minutes("housing-anywhere") == 20


def test_invalid_frequency_falls_back_to_ten_minutes(monkeypatch):
    monkeypatch.setenv("ICAL_SYNC_INTERVAL_MINUTES", "invalid")
    assert sync_interval_minutes("spotahome") == 10
