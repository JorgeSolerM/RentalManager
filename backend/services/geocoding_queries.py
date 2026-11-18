"""Progressive, auditable server geocoding. No business DB writes."""
from dataclasses import asdict
import json
import os
from pathlib import Path
import sqlite3
import time

import httpx

from backend.public.map_locations import Address, city_key, street_key, normalize, geocoder_url, verified_result


def aliases():
    """Operator-reviewed equivalences, never a general proper-name translator."""
    path = os.getenv('PUBLIC_GEOCODING_ALIASES', '')
    if not path:
        return []
    rows = json.loads(Path(path).read_text(encoding='utf-8'))
    return [r for r in rows if all(isinstance(r.get(k), str) and r[k].strip()
            for k in ('city', 'original', 'translated', 'evidence'))]


def variants(address):
    key = street_key(address.street)
    prefix = normalize(address.street).split(' ')[0]
    es, va = ('Avenida', 'Avinguda') if prefix in {'avenida', 'avinguda', 'av'} else (
        ('Plaza', 'Plaça') if prefix in {'plaza', 'placa', 'pl'} else ('Calle', 'Carrer'))
    # Preserve proper-name spelling; strip only the already supported road type.
    import re
    name = re.sub(r'^(?:calle|carrer|c[./]?|avenida|avinguda|av[.]?|plaza|plaça|pl[.]?)\s+', '', address.street, flags=re.I)
    result = [(address, 'original', True),
              (Address(f'{es} {name}', address.number, address.city), 'castellano', True),
              (Address(f'{va} {name}', address.number, 'Elx' if city_key(address.city) == 'elche' else address.city), 'valenciano', True)]
    found = False
    for row in aliases():
        if city_key(row['city']) == city_key(address.city) and street_key(row['original']) == key:
            result.append((Address(f"{va} {row['translated']}", address.number, 'Elx' if city_key(address.city) == 'elche' else address.city), 'equivalencia_documentada', True))
            found = True
    # A requested candidate is NOT proof of equivalence (Gerona and Girona may coexist).
    if key == 'gerona' and city_key(address.city) == 'elche' and not found:
        result.append((Address('Carrer Girona', address.number, 'Elx'), 'equivalencia_no_verificada', False))
    seen = set()
    return [(a, label, trusted) for a, label, trusted in result
            if not (a.key in seen or seen.add(a.key))]


def initialize(db):
    # Companion tables keep the deployed eight-column locations schema compatible.
    db.execute('CREATE TABLE IF NOT EXISTS geocoding_queries (query_key TEXT PRIMARY KEY, address_key TEXT NOT NULL, variant TEXT NOT NULL, label TEXT NOT NULL, trusted INTEGER NOT NULL, status TEXT NOT NULL, reason TEXT NOT NULL, http_status INTEGER, latitude REAL, longitude REAL, checked_at REAL NOT NULL, attempts INTEGER NOT NULL, retry_at REAL NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS geocoding_attempts (id INTEGER PRIMARY KEY, address_key TEXT NOT NULL, variant TEXT NOT NULL, label TEXT NOT NULL, status TEXT NOT NULL, reason TEXT NOT NULL, http_status INTEGER, checked_at REAL NOT NULL)')
    db.execute('CREATE INDEX IF NOT EXISTS ix_geocoding_attempt_address ON geocoding_attempts(address_key, id)')


def diagnostics(cache, address):
    """Read-only, including compatibility with caches predating progressive queries."""
    entry = cache.read_many([address.key]).get(address.key)
    attempts, next_request = [], 0
    if cache.path.exists():
        with sqlite3.connect(cache.path.as_uri()+'?mode=ro', uri=True, timeout=2) as db:
            db.row_factory = sqlite3.Row
            row = db.execute('SELECT next_request FROM throttle WHERE id=1').fetchone()
            next_request = row[0] if row else 0
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='geocoding_attempts'").fetchone():
                attempts = [dict(r) for r in db.execute('SELECT * FROM geocoding_attempts WHERE address_key=? ORDER BY id DESC LIMIT 20', (address.key,))]
    for row in attempts:
        a = json.loads(row['variant'])
        row['address'] = f"{a['street']} {a['number']}, {a['city']}"
    return {'entry': entry, 'attempts': attempts, 'next_request': next_request}


def resolve(cache, address, *, client, manual=False, clock=time.time, sleep=time.sleep):
    """One process/one SQLite lock; all variants share the provider throttle."""
    cache.initialize()
    with sqlite3.connect(cache.path, timeout=2) as db:
        db.row_factory = sqlite3.Row
        db.execute('BEGIN IMMEDIATE')
        initialize(db)
        current = db.execute('SELECT * FROM locations WHERE address_key=?', (address.key,)).fetchone()
        if current and current['status'] == 'verified':
            return 'verified'
        if current and current['status'] == 'error' and current['retry_at'] > clock():
            return 'paused'
        if current and current['status'] == 'error' and current['attempts'] >= 3 and not db.execute(
                'SELECT 1 FROM geocoding_queries WHERE address_key=?', (address.key,)).fetchone():
            return 'exhausted'  # Preserve the limit of pre-upgrade provider errors.
        if not all((address.street, address.number, address.city)):
            db.execute('INSERT OR REPLACE INTO locations VALUES (?,?,?,?,?,?,?,?)',
                (address.key,'review',None,None,'incomplete_address',clock(),0,0))
            return 'incomplete'
        if db.execute('SELECT next_request FROM throttle WHERE id=1').fetchone()[0] > clock()+16.1:
            return 'paused'
        final, reason, point = 'review', 'no_exact_street_number_city', None
        performed = False
        for candidate, label, trusted in variants(address):
            old = db.execute('SELECT * FROM geocoding_queries WHERE query_key=?', (candidate.key,)).fetchone()
            if old and old['status'] == 'verified' and trusted:
                db.execute('INSERT OR REPLACE INTO locations VALUES (?,?,?,?,?,?,?,?)',
                    (address.key,'verified',old['latitude'],old['longitude'],old['reason'],old['checked_at'],old['attempts'],0))
                return 'verified'
            can_retry = old and old['attempts'] < 3 and old['checked_at']+86400 <= clock() and (manual or old['status']=='error')
            if old and not can_retry:
                if old['status'] == 'error':
                    return 'paused' if old['retry_at'] > clock() else 'exhausted'
                if old['reason'] in ('ambiguous', 'unverified_street_equivalence'):
                    reason = old['reason']
                    if reason == 'ambiguous': break
                continue
            # Do not repeat the original legacy review query when no audit table existed.
            if not old and label == 'original' and current and current['status'] == 'review':
                continue
            next_request = db.execute('SELECT next_request FROM throttle WHERE id=1').fetchone()[0]
            if next_request > clock()+16.1: return 'paused'
            if next_request > clock(): sleep(next_request-clock())
            attempts = (old['attempts'] if old else 0)+1
            # Durable reservation: if killed during HTTP, other processes observe
            # the conservative pause rather than immediately repeating the request.
            db.execute('UPDATE throttle SET next_request=? WHERE id=1', (clock()+86400,))
            db.commit()
            db.execute('BEGIN IMMEDIATE')
            http_status = None
            try:
                response = client.get(geocoder_url(), params={'street':f'{candidate.number} {candidate.street}', 'city':candidate.city,
                    'format':'jsonv2', 'addressdetails':1, 'limit':10, 'accept-language':'es'})
                http_status = response.status_code
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, list): raise ValueError('Invalid response shape')
                final, point, reason = verified_result(candidate, payload)
                if final == 'verified' and not trusted:
                    final, point, reason = 'review', None, 'unverified_street_equivalence'
            except (httpx.HTTPError, ValueError) as error:
                reason = (f'http_{error.response.status_code}' if isinstance(error,httpx.HTTPStatusError)
                          else 'timeout' if isinstance(error,httpx.TimeoutException)
                          else 'connection_error' if isinstance(error,httpx.NetworkError) else 'invalid_response')
                final, point = 'error', None
            now = clock(); retry = now+86400 if final == 'error' else 0
            db.execute('UPDATE throttle SET next_request=? WHERE id=1', (retry or now+16,))
            serialized = json.dumps(asdict(candidate), ensure_ascii=False)
            db.execute('INSERT OR REPLACE INTO geocoding_queries VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (candidate.key,address.key,serialized,label,int(trusted),final,reason,http_status,
                 point[0] if point else None,point[1] if point else None,now,attempts,retry))
            db.execute('INSERT INTO geocoding_attempts(address_key,variant,label,status,reason,http_status,checked_at) VALUES (?,?,?,?,?,?,?)',
                (address.key,serialized,label,final,reason,http_status,now))
            db.execute('INSERT OR REPLACE INTO locations VALUES (?,?,?,?,?,?,?,?)',
                (address.key,final,point[0] if point else None,point[1] if point else None,reason,now,
                 (current['attempts'] if current else 0)+1,retry))
            performed = True
            # Commit each attempt before the next, preserving errors/history on interruption.
            db.commit()
            if final in ('verified','error') or reason in ('ambiguous','unverified_street_equivalence'): return final
            db.execute('BEGIN IMMEDIATE')
            # Another worker may have resolved it while this process released its lock.
            current = db.execute('SELECT * FROM locations WHERE address_key=?',(address.key,)).fetchone()
            if current['status']=='verified': return 'verified'
        return final if performed else 'cached'
