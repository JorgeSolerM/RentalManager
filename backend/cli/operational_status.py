"""Read-only probes and private release manifests. Never restarts or migrates.

python -m backend.cli.operational_status --help
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time

import httpx


def release_manifest(service, commit, components):
    if service not in {'admin','public','ical'} or not re.fullmatch('[a-f0-9]{40}',commit):
        raise ValueError('Expected service and full reference commit')
    files = {}
    for logical, physical in components.items():
        if not re.fullmatch(r'(?:backend|docs)/[A-Za-z0-9_./-]+',logical) or '..' in Path(logical).parts:
            raise ValueError('Invalid component name')
        path = Path(physical).resolve(strict=True)
        if path.suffix not in {'.py','.html','.js','.css','.md'} or Path(logical).suffix != path.suffix:
            raise ValueError('Not a source component')
        files[logical] = {'source':str(path), 'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    if not files: raise ValueError('No installed components supplied')
    return {'service':service,'reference_commit':commit,'created_at':datetime.now(timezone.utc).isoformat(),
            'components':files}


def verify_manifest(manifest):
    changed=[]
    for name, item in manifest['components'].items():
        try: matches=hashlib.sha256(Path(item['source']).read_bytes()).hexdigest()==item['sha256']
        except OSError: matches=False
        if not matches: changed.append(name)
    return {'service':manifest['service'],'reference_commit':manifest['reference_commit'],
            'matches':not changed,'changed_components':changed}


def probe_services(client):
    # Fixed destinations: no private feed URL, arbitrary external URL or query string.
    targets={'admin_live':'http://127.0.0.1:8000/_ops/live',
             'admin_ready':'http://127.0.0.1:8000/_ops/ready',
             'public_live':'http://127.0.0.1:8001/_ops/live',
             'public_ready':'http://127.0.0.1:8001/_ops/ready',
             'public_local':'http://127.0.0.1:8001/',
             'public_https':'https://hsi-rents.com/'}
    results={}
    for key, url in targets.items():
        started=time.monotonic()
        try:
            response=client.get(url)
            results[key]={'http_status':response.status_code,'duration_ms':round((time.monotonic()-started)*1000,1)}
        except httpx.TimeoutException: results[key]={'error':'timeout'}
        except httpx.HTTPError: results[key]={'error':'connection_or_tls'}
    return {'utc':datetime.now(timezone.utc).isoformat(),'checks':results}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('probe',help='Fixed HTTP GET checks, no restart and no sync')
    create=sub.add_parser('manifest',help='Print private manifest JSON, without copying source contents')
    create.add_argument('--service',required=True,choices=['admin','public','ical'])
    create.add_argument('--commit',required=True)
    create.add_argument('--component',action='append',required=True,metavar='LOGICAL=INSTALLED_PATH')
    verify=sub.add_parser('verify-manifest');verify.add_argument('path')
    args=parser.parse_args()
    if args.command=='probe':
        with httpx.Client(timeout=3,follow_redirects=False,trust_env=False) as client:
            result=probe_services(client)
    elif args.command=='manifest':
        components=dict(item.split('=',1) for item in args.component)
        if len(components)!=len(args.component): parser.error('Duplicate component name')
        result=release_manifest(args.service,args.commit,components)
    else:
        result=verify_manifest(json.loads(Path(args.path).read_text(encoding='utf-8-sig')))
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
