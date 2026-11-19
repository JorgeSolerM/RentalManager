"""Opt-in, bounded, privacy-by-construction operational events.

Never persist LogRecord messages/arguments, HTTP payloads or exception values.
One writer thread owns each rotating file. No file I/O on a request thread.
"""
import atexit
from datetime import datetime, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
from queue import Queue, Empty, Full
import re
import threading
import uuid

MAX_BYTES = 10 * 1024 * 1024
BACKUPS = 5
ICAL_CODES = {'room_calendar_sync_'+suffix for suffix in (
    'completed','completed_with_warnings','failed','overlap','database_error','database_locked',
    'download_failed','http_access_error','http_error','http_server_error','in_progress',
    'incompatible_stay','invalid_feed','rate_limited','recurrence_not_supported','timeout',
    'too_large','too_many_events','too_many_redirects','unexpected_error','unsafe_url')}
EVENTS = {'service_started', 'service_stopped', 'request_started', 'request_finished',
          'request_failed', 'runtime_error', 'dependency_check', 'ical_result'}
COUNTS = {'calendar_id', 'received', 'created', 'updated', 'unchanged', 'cancelled',
          'disappeared', 'ignored_echoes', 'early_termination_conflicts'}
PREFIXES = {'properties', 'persons', 'owners', 'rooms', 'bookings', 'gantt', 'settings',
            'expenses', 'settlements', 'providers', 'collections', 'sepa', 'reconciliation',
            'habitaciones', 'contacto', 'aviso-legal', 'privacidad', 'cookies', 'static',
            'media', 'ical', 'colaboradores', 'robots.txt', 'sitemap.xml', '_ops'}


def normalized_route(scope):
    # Only literal route templates from the application, never actual path values.
    route = getattr(scope.get('route'), 'path', None)
    if route and re.fullmatch(r'/[A-Za-z0-9_/{\}:.-]*', route):
        return route[:180]
    path = scope.get('path', '/')
    if path == '/': return '/'
    prefix = path.split('/')[1]
    return '/'+prefix+'/{redacted}' if prefix in PREFIXES else '/{unmatched}'


def safe_fields(values):
    result = {}
    for key, value in values.items():
        if key in COUNTS | {'status'} and type(value) is int and 0 <= value <= 10**12:
            result[key] = value
        elif key == 'duration_ms' and isinstance(value, (int, float)) and 0 <= value < 10**12:
            result[key] = round(value, 2)
        elif key == 'request_id' and isinstance(value, str) and re.fullmatch(r'[a-f0-9]{32}', value):
            result[key] = value
        elif key == 'method':
            result[key] = value if value in {'GET','POST','PUT','PATCH','DELETE','HEAD','OPTIONS'} else 'OTHER'
        elif key == 'route' and isinstance(value, str) and re.fullmatch(r'/[A-Za-z0-9_/{\}:.-]*', value):
            result[key] = value[:180]
        elif key in {'success', 'ready'} and type(value) is bool:
            result[key] = value
        elif key == 'result_code':
            result[key] = value if value in ICAL_CODES else 'unknown'
        elif key == 'error_type':
            # Closed taxonomy, never an arbitrary provider exception or message.
            result[key] = value if value in {'timeout','database','network','permission','unexpected'} else 'unexpected'
    return result


def error_kind(error):
    import sqlite3
    import httpx
    if isinstance(error, httpx.TimeoutException): return 'timeout'
    if isinstance(error, httpx.TransportError): return 'network'
    if isinstance(error, (TimeoutError,)): return 'timeout'
    if isinstance(error, sqlite3.Error): return 'database'
    if isinstance(error, PermissionError): return 'permission'
    if isinstance(error, ConnectionError): return 'network'
    return 'unexpected'


class QuietRotatingHandler(RotatingFileHandler):
    def handleError(self, record):
        # Default logging prints the failed message/traceback to stderr.
        raise OSError('operational_log_write_failed') from None


class EventSink:
    def __init__(self, directory, service, version='unknown', *, capacity=1024,
                 max_bytes=MAX_BYTES, backups=BACKUPS):
        if service not in {'admin','public','ical'}: raise ValueError('Unknown operational service')
        self.directory = Path(directory)
        self.service = service
        self.version = version if re.fullmatch(r'[a-f0-9]{7,40}', version) else 'unknown'
        self.instance = uuid.uuid4().hex
        self.queue = Queue(maxsize=capacity)
        self.dropped = 0
        self.write_failures = 0
        self.closed = False
        self.handler = None
        self.max_bytes, self.backups = max_bytes, backups
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, name='ops-'+service, daemon=True)
        self.thread.start()

    def emit(self, event, **fields):
        if event not in EVENTS or self.closed: return
        row = {'utc': datetime.now(timezone.utc).isoformat(), 'service': self.service,
               'pid': os.getpid(), 'version': self.version, 'instance': self.instance,
               'event': event, **safe_fields(fields)}
        try: self.queue.put_nowait(row)
        except Full: self.dropped += 1

    def _write(self, row):
        if self.handler is None:
            self.directory.mkdir(parents=True, exist_ok=True)
            self.handler = QuietRotatingHandler(self.directory/(self.service+'.jsonl'),
                maxBytes=self.max_bytes, backupCount=self.backups, encoding='utf-8', delay=True)
            self.handler.setFormatter(logging.Formatter('%(message)s'))
        record = logging.LogRecord('operational', logging.INFO, '', 0,
            json.dumps(row, ensure_ascii=False, allow_nan=False), (), None)
        self.handler.emit(record)

    def _run(self):
        while not self.stop.is_set() or not self.queue.empty():
            try: row = self.queue.get(timeout=.1)
            except Empty: continue
            try:
                if isinstance(row, threading.Event): row.set()
                else: self._write(row)
            except Exception:
                self.write_failures += 1  # No recursion, raw exceptions or blocking stderr writes.
            finally: self.queue.task_done()
        if self.handler: self.handler.close()

    def flush(self, timeout=2):
        barrier = threading.Event()
        try: self.queue.put_nowait(barrier)
        except Full: return False
        return barrier.wait(timeout)

    def close(self):
        if self.closed: return
        self.emit('service_stopped')
        self.closed = True
        self.stop.set()
        self.thread.join(timeout=2)


class SafeErrorBridge(logging.Handler):
    def __init__(self, sink):
        super().__init__(logging.WARNING)
        self.sink = sink

    def emit(self, record):
        # Discard message, args, SQL params, stack_info, and exception text entirely.
        seen = getattr(record, '_operational_instances', set())
        if self.sink.instance in seen: return
        record._operational_instances = seen | {self.sink.instance}
        error = record.exc_info[1] if record.exc_info else None
        self.sink.emit('runtime_error', error_type=error_kind(error))


_sinks = {}
_lock = threading.Lock()


def configured_sink(service):
    if os.getenv('RM_DIAGNOSTICS_ENABLED', '0') != '1': return None
    directory = Path(os.getenv('RM_DIAGNOSTICS_LOG_DIR', ''))
    # Explicit private absolute path, never a default under a publicly mounted directory.
    if not directory.is_absolute() or any(p.lower() in {'static','media','templates'} for p in directory.parts):
        return None
    with _lock:
        key = (service, str(directory))
        if key not in _sinks:
            try:
                sink = EventSink(directory, service, os.getenv('RM_RELEASE_COMMIT','unknown'))
            except Exception:
                return None  # Diagnostics must never prevent the application starting.
            _sinks[key] = sink
            # CLI/server process should enable just one service identity.
            bridge = SafeErrorBridge(sink)
            logging.getLogger().addHandler(bridge)
            for name in ('uvicorn.error',):
                logging.getLogger(name).addHandler(bridge)
            atexit.register(sink.close)
            sink.emit('service_started')
        return _sinks[key]


def ical_event(result, calendar_id):
    """Only fixed counters; no URL, guest identity, event summary or provider text."""
    # Admin manual sync uses its existing sink; CLI can explicitly configure ical.
    for sink in list(_sinks.values()):
        fields = {'calendar_id':calendar_id, 'success':bool(result.success), 'result_code':result.message}
        report = result.data
        for key in COUNTS - {'calendar_id'}:
            value = getattr(report, key, None)
            if type(value) is int: fields[key] = value
        sink.emit('ical_result', **fields)
