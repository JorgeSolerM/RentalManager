import socket
import time

import httpx
import httpcore
import pytest

from backend.integrations.ical_http_client import (
    IcalDownloadError,
    MAX_RESPONSE_BYTES,
    SafeIcalHttpClient,
)


ICAL = b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n"


def resolver_for(*addresses):
    def resolver(_host, port, type=socket.SOCK_STREAM):
        return [
            (socket.AF_INET6 if ":" in address else socket.AF_INET, type, 6, "", (address, port))
            for address in addresses
        ]
    return resolver


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1", "10.0.0.1", "172.16.0.1", "192.168.1.1",
        "169.254.1.1", "100.64.0.1", "224.0.0.1", "192.0.2.1",
        "::1", "fd00::1", "fe80::1", "ff02::1", "::ffff:127.0.0.1",
    ],
)
def test_rejects_non_global_ipv4_and_ipv6(address):
    client = SafeIcalHttpClient(resolver=resolver_for(address))
    with pytest.raises(IcalDownloadError, match="room_calendar_sync_unsafe_url"):
        client.validate_target("https://calendar.example/feed.ics")


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/feed.ics",
        "ftp://calendar.example/feed.ics",
        "https://user:secret@calendar.example/feed.ics",
        "https://calendar.example:8443/feed.ics",
    ],
)
def test_rejects_unsafe_url_forms(url):
    client = SafeIcalHttpClient(resolver=resolver_for("93.184.216.34"))
    with pytest.raises(IcalDownloadError, match="room_calendar_sync_unsafe_url"):
        client.validate_target(url)


def test_rejects_host_when_any_dns_answer_is_private():
    client = SafeIcalHttpClient(
        resolver=resolver_for("93.184.216.34", "127.0.0.1")
    )
    with pytest.raises(IcalDownloadError, match="room_calendar_sync_unsafe_url"):
        client.validate_target("https://calendar.example/feed.ics")


def test_pins_validated_ip_while_request_keeps_original_host():
    observed = {}

    def factory(hostname, ip_address):
        observed["hostname"] = hostname
        observed["ip_address"] = ip_address

        def handler(request):
            observed["request_host"] = request.url.host
            return httpx.Response(200, content=ICAL, headers={"content-type": "text/calendar"})
        return httpx.MockTransport(handler)

    client = SafeIcalHttpClient(
        resolver=resolver_for("93.184.216.34"), transport_factory=factory
    )
    assert client.download("https://calendar.example/feed.ics") == ICAL
    assert observed == {
        "hostname": "calendar.example",
        "ip_address": "93.184.216.34",
        "request_host": "calendar.example",
    }


def test_pinned_backend_connects_to_validated_ip_not_a_second_dns_result(monkeypatch):
    from backend.integrations.ical_http_client import _PinnedNetworkBackend

    observed = {}

    def connect(_self, host, port, **kwargs):
        observed.update(host=host, port=port)
        return object()

    monkeypatch.setattr(httpcore.SyncBackend, "connect_tcp", connect)
    backend = _PinnedNetworkBackend("calendar.example", "93.184.216.34")
    backend.connect_tcp("calendar.example", 443)

    assert observed == {"host": "93.184.216.34", "port": 443}
    with pytest.raises(httpcore.ConnectError):
        backend.connect_tcp("rebound.example", 443)


def test_redirect_target_is_resolved_and_revalidated():
    resolutions = []

    def resolver(host, port, type=socket.SOCK_STREAM):
        resolutions.append(host)
        address = "93.184.216.34" if host == "first.example" else "127.0.0.1"
        return resolver_for(address)(host, port, type=type)

    def factory(_hostname, _ip_address):
        return httpx.MockTransport(
            lambda _request: httpx.Response(
                302, headers={"location": "http://private.example/feed.ics"}
            )
        )

    client = SafeIcalHttpClient(resolver=resolver, transport_factory=factory)
    with pytest.raises(IcalDownloadError, match="room_calendar_sync_unsafe_url"):
        client.download("https://first.example/feed.ics")
    assert resolutions == ["first.example", "private.example"]


def test_safe_redirect_is_followed_with_a_new_pinned_target():
    requested_hosts = []

    def factory(hostname, _ip_address):
        def handler(_request):
            requested_hosts.append(hostname)
            if hostname == "first.example":
                return httpx.Response(
                    302, headers={"location": "https://second.example/feed.ics"}
                )
            return httpx.Response(
                200, content=ICAL, headers={"content-type": "text/calendar"}
            )
        return httpx.MockTransport(handler)

    client = SafeIcalHttpClient(
        resolver=resolver_for("93.184.216.34"), transport_factory=factory
    )
    assert client.download("https://first.example/feed.ics") == ICAL
    assert requested_hosts == ["first.example", "second.example"]


def test_more_than_five_redirects_are_rejected():
    transport = lambda *_: httpx.MockTransport(
        lambda request: httpx.Response(
            302, headers={"location": f"https://calendar.example{request.url.path}x"}
        )
    )
    client = SafeIcalHttpClient(
        resolver=resolver_for("93.184.216.34"), transport_factory=transport
    )
    with pytest.raises(IcalDownloadError, match="too_many_redirects"):
        client.download("https://calendar.example/feed")


def test_deadline_stream_preserves_original_hostname_for_tls_sni():
    from backend.integrations.ical_http_client import _DeadlineNetworkStream

    observed = {}

    class Stream:
        def start_tls(self, _context, server_hostname=None, timeout=None):
            observed.update(server_hostname=server_hostname, timeout=timeout)
            return self

        def get_extra_info(self, _info):
            return None

    wrapped = _DeadlineNetworkStream(Stream(), time.monotonic() + 15)
    wrapped.start_tls(object(), server_hostname="calendar.example", timeout=5)
    assert observed["server_hostname"] == "calendar.example"
    assert 0 < observed["timeout"] <= 5


def test_timeout_is_translated():
    transport = lambda *_: httpx.MockTransport(
        lambda request: (_ for _ in ()).throw(httpx.ReadTimeout("late", request=request))
    )
    client = SafeIcalHttpClient(
        resolver=resolver_for("93.184.216.34"), transport_factory=transport
    )
    with pytest.raises(IcalDownloadError, match="room_calendar_sync_timeout"):
        client.download("https://calendar.example/feed.ics")


def test_size_limit_applies_without_content_length():
    transport = lambda *_: httpx.MockTransport(
        lambda _request: httpx.Response(
            200,
            content=b"BEGIN:VCALENDAR\r\n" + b"X" * MAX_RESPONSE_BYTES,
            headers={"content-type": "text/calendar"},
        )
    )
    client = SafeIcalHttpClient(
        resolver=resolver_for("93.184.216.34"), transport_factory=transport
    )
    with pytest.raises(IcalDownloadError, match="room_calendar_sync_too_large"):
        client.download("https://calendar.example/feed.ics")


@pytest.mark.parametrize(
    ("content_type", "content"),
    [("text/html", ICAL), ("text/calendar", b"<html>not a calendar</html>")],
)
def test_rejects_invalid_mime_or_content(content_type, content):
    transport = lambda *_: httpx.MockTransport(
        lambda _request: httpx.Response(
            200, content=content, headers={"content-type": content_type}
        )
    )
    client = SafeIcalHttpClient(
        resolver=resolver_for("93.184.216.34"), transport_factory=transport
    )
    with pytest.raises(IcalDownloadError, match="room_calendar_sync_invalid_feed"):
        client.download("https://calendar.example/feed.ics")
