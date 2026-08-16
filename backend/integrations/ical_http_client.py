from __future__ import annotations

import ipaddress
import socket
import ssl
import time
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpcore
import httpx


MAX_RESPONSE_BYTES = 5 * 1024 * 1024
MAX_REDIRECTS = 5
ALLOWED_PORTS = {80, 443}
ALLOWED_CONTENT_TYPES = {
    "text/calendar",
    "text/plain",
    "application/octet-stream",
}


class IcalDownloadError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ValidatedTarget:
    url: str
    hostname: str
    ip_address: str


class _PinnedNetworkBackend(httpcore.SyncBackend):
    def __init__(self, hostname: str, ip_address: str, deadline: float | None = None):
        self._hostname = hostname.lower()
        self._ip_address = ip_address
        self._deadline = deadline or (time.monotonic() + 15.0)

    def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        requested_host = host.decode("ascii") if isinstance(host, bytes) else host
        if requested_host.lower() != self._hostname:
            raise httpcore.ConnectError("Unvalidated connection target")
        remaining = self._deadline - time.monotonic()
        if remaining <= 0:
            raise httpcore.ConnectTimeout("iCal download deadline exceeded")
        stream = super().connect_tcp(
            self._ip_address,
            port,
            timeout=min(timeout or remaining, remaining),
            local_address=local_address,
            socket_options=socket_options,
        )
        return _DeadlineNetworkStream(stream, self._deadline)


class _DeadlineNetworkStream(httpcore.NetworkStream):
    def __init__(self, stream, deadline: float):
        self._stream = stream
        self._deadline = deadline

    def _timeout(self, timeout):
        remaining = self._deadline - time.monotonic()
        if remaining <= 0:
            raise httpcore.ReadTimeout("iCal download deadline exceeded")
        return min(timeout or remaining, remaining)

    def read(self, max_bytes, timeout=None):
        return self._stream.read(max_bytes, self._timeout(timeout))

    def write(self, buffer, timeout=None):
        return self._stream.write(buffer, self._timeout(timeout))

    def close(self):
        return self._stream.close()

    def start_tls(self, ssl_context, server_hostname=None, timeout=None):
        stream = self._stream.start_tls(
            ssl_context,
            server_hostname=server_hostname,
            timeout=self._timeout(timeout),
        )
        return _DeadlineNetworkStream(stream, self._deadline)

    def get_extra_info(self, info):
        return self._stream.get_extra_info(info)


class _PinnedHTTPTransport(httpx.HTTPTransport):
    def __init__(self, hostname: str, ip_address: str, deadline: float):
        super().__init__(verify=True, trust_env=False, retries=0)
        self._pool.close()
        self._pool = httpcore.ConnectionPool(
            ssl_context=ssl.create_default_context(),
            network_backend=_PinnedNetworkBackend(hostname, ip_address, deadline),
            max_connections=1,
            max_keepalive_connections=0,
            retries=0,
        )


class SafeIcalHttpClient:
    def __init__(self, resolver=None, transport_factory=None):
        self._resolver = resolver or socket.getaddrinfo
        self._transport_factory = transport_factory

    @staticmethod
    def _is_global(address: str) -> bool:
        ip = ipaddress.ip_address(address)
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        return (
            ip.is_global
            and not ip.is_multicast
            and not ip.is_reserved
            and not ip.is_unspecified
            and not ip.is_loopback
            and not ip.is_link_local
            and not ip.is_private
        )

    def validate_target(self, url: str) -> ValidatedTarget:
        try:
            parsed = urlsplit(url)
            port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
        except ValueError as error:
            raise IcalDownloadError("room_calendar_sync_unsafe_url") from error

        hostname = parsed.hostname
        if (
            parsed.scheme.lower() not in {"http", "https"}
            or hostname is None
            or parsed.username is not None
            or parsed.password is not None
            or port not in ALLOWED_PORTS
            or hostname.rstrip(".").lower() == "localhost"
        ):
            raise IcalDownloadError("room_calendar_sync_unsafe_url")

        try:
            hostname = hostname.rstrip(".").encode("idna").decode("ascii")
        except UnicodeError as error:
            raise IcalDownloadError("room_calendar_sync_unsafe_url") from error

        try:
            records = self._resolver(hostname, port, type=socket.SOCK_STREAM)
            addresses = list(dict.fromkeys(record[4][0] for record in records))
        except (OSError, UnicodeError) as error:
            raise IcalDownloadError("room_calendar_sync_download_failed") from error

        try:
            safe = addresses and all(self._is_global(address) for address in addresses)
        except ValueError as error:
            raise IcalDownloadError("room_calendar_sync_unsafe_url") from error
        if not safe:
            raise IcalDownloadError("room_calendar_sync_unsafe_url")

        return ValidatedTarget(url=url, hostname=hostname, ip_address=addresses[0])

    def download(self, url: str) -> bytes:
        current_url = url
        deadline = time.monotonic() + 15.0

        for redirect_count in range(MAX_REDIRECTS + 1):
            target = self.validate_target(current_url)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise IcalDownloadError("room_calendar_sync_timeout")
            transport = (
                self._transport_factory(target.hostname, target.ip_address)
                if self._transport_factory
                else _PinnedHTTPTransport(target.hostname, target.ip_address, deadline)
            )
            timeout = httpx.Timeout(
                connect=min(5.0, remaining),
                read=remaining,
                write=min(5.0, remaining),
                pool=min(5.0, remaining),
            )
            try:
                with httpx.Client(
                    transport=transport,
                    timeout=timeout,
                    follow_redirects=False,
                    trust_env=False,
                    headers={"User-Agent": "RentalManager-iCal/1.0"},
                ) as client:
                    with client.stream("GET", target.url) as response:
                        if response.status_code in {301, 302, 303, 307, 308}:
                            location = response.headers.get("location")
                            if not location or redirect_count == MAX_REDIRECTS:
                                raise IcalDownloadError("room_calendar_sync_too_many_redirects")
                            current_url = urljoin(target.url, location)
                            continue
                        response.raise_for_status()
                        content_length = response.headers.get("content-length")
                        if content_length:
                            try:
                                too_large = int(content_length) > MAX_RESPONSE_BYTES
                            except ValueError as error:
                                raise IcalDownloadError("room_calendar_sync_invalid_feed") from error
                            if too_large:
                                raise IcalDownloadError("room_calendar_sync_too_large")

                        content = bytearray()
                        for chunk in response.iter_bytes():
                            if time.monotonic() > deadline:
                                raise IcalDownloadError("room_calendar_sync_timeout")
                            content.extend(chunk)
                            if len(content) > MAX_RESPONSE_BYTES:
                                raise IcalDownloadError("room_calendar_sync_too_large")

                        media_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                        looks_like_ical = bytes(content).lstrip().upper().startswith(b"BEGIN:VCALENDAR")
                        if (media_type and media_type not in ALLOWED_CONTENT_TYPES) or not looks_like_ical:
                            raise IcalDownloadError("room_calendar_sync_invalid_feed")
                        return bytes(content)
            except IcalDownloadError:
                raise
            except httpx.TimeoutException as error:
                raise IcalDownloadError("room_calendar_sync_timeout") from error
            except httpx.HTTPError as error:
                raise IcalDownloadError("room_calendar_sync_download_failed") from error

        raise IcalDownloadError("room_calendar_sync_too_many_redirects")
