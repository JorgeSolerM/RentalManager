import json
import logging
import threading
import time

from backend.core.operational_logging import EventSink, SafeErrorBridge, MAX_BYTES, BACKUPS


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]


def test_private_data_never_serialized(tmp_path):
    sink=EventSink(tmp_path,'admin','a'*40)
    secret='synthetic-password ES9121000418450200051332 guest@example.test private-ical-token'
    sink.emit('runtime_error',password=secret,body=secret,headers=secret,query=secret,error_type=secret)
    record=logging.LogRecord('httpx',logging.ERROR,'',1,secret,(secret,),None)
    try: raise ValueError(secret)
    except ValueError:
        import sys
        record.exc_info=sys.exc_info()
    SafeErrorBridge(sink).emit(record)
    assert sink.flush();sink.close()
    text=(tmp_path/'admin.jsonl').read_text()
    assert not any(value in text for value in secret.split())
    assert all(row['service']=='admin' and row['version']=='a'*40 and row['pid']>0 for row in rows(tmp_path/'admin.jsonl'))
    assert MAX_BYTES==10*1024*1024 and BACKUPS==5


def test_rotation_and_independent_services(tmp_path):
    sink=EventSink(tmp_path/'admin','admin',max_bytes=500,backups=5)
    for _ in range(100): sink.emit('request_finished',status=200)
    assert sink.flush();sink.close()
    files=list((tmp_path/'admin').glob('admin.jsonl*'))
    assert len(files)==6
    assert all(path.stat().st_size<500 for path in files)
    public=EventSink(tmp_path/'public','public');public.emit('service_started');public.close()
    assert (tmp_path/'public/public.jsonl').exists()


def test_permission_or_disk_error_is_contained_and_retries(tmp_path,monkeypatch):
    sink=EventSink(tmp_path,'admin');original=sink._write
    def denied(row): raise PermissionError('PRIVATE path and credentials')
    monkeypatch.setattr(sink,'_write',denied)
    sink.emit('service_started');assert sink.flush()
    assert sink.write_failures==1
    monkeypatch.setattr(sink,'_write',original)
    sink.emit('service_started');assert sink.flush();sink.close()
    assert (tmp_path/'admin.jsonl').exists()


def test_queue_overflow_never_blocks_caller(tmp_path,monkeypatch):
    sink=EventSink(tmp_path,'admin',capacity=1)
    entered=threading.Event();release=threading.Event()
    def slow(row): entered.set();release.wait(2)
    monkeypatch.setattr(sink,'_write',slow)
    sink.emit('service_started');assert entered.wait(1)
    started=time.monotonic()
    for _ in range(100):sink.emit('service_started')
    assert time.monotonic()-started<.5 and sink.dropped>0
    release.set();sink.close()


def test_missing_directory_permissions_do_not_break_emit(tmp_path):
    blocked=tmp_path/'file';blocked.write_text('not a directory')
    sink=EventSink(blocked/'child','public')
    sink.emit('service_started');assert sink.flush()
    assert sink.write_failures==1
    sink.close()


def test_ical_diagnostics_keep_causes_without_provider_payload(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from backend.core import operational_logging as ops
    from backend.core.operation_result import OperationResult
    sink=EventSink(tmp_path,'ical')
    monkeypatch.setattr(ops,'_sinks',{'test':sink})
    report=SimpleNamespace(cancelled=1,disappeared=2,early_termination_conflicts=3,
                           private_url='https://private.test/token')
    ops.ical_event(OperationResult(True,'room_calendar_sync_completed_with_warnings',report),7)
    ops.ical_event(OperationResult(False,'private-provider-error'),7)
    assert sink.flush();sink.close()
    raw=(tmp_path/'ical.jsonl').read_text()
    rows=[json.loads(line) for line in raw.splitlines() if 'ical_result' in line]
    assert rows[0]['cancelled']==1 and rows[0]['disappeared']==2
    assert rows[0]['early_termination_conflicts']==3
    assert rows[1]['result_code']=='unknown'
    assert 'private' not in raw
