"""Private administration boundary. No public-site or iCal authentication changes."""
import asyncio
from dataclasses import dataclass
import ipaddress
import json
import os
import re
import time
from urllib.parse import urlsplit

import httpx
import jwt


@dataclass(frozen=True)
class AccessConfig:
    enabled: bool = False
    hostname: str = ''
    issuer: str = ''
    audience: str = ''
    identities: tuple[str, ...] = ()
    local_hosts: tuple[str, ...] = ('localhost', '127.0.0.1', '::1')
    ical_hosts: tuple[str, ...] = ('calendarios.hsi-rents.com',)

    def __post_init__(self):
        if not self.enabled:
            return
        if not re.fullmatch(r'[a-z0-9]+(?:[.-][a-z0-9]+)*\.[a-z]{2,}', self.hostname):
            raise ValueError('Invalid administrative hostname')
        if self.hostname in self.local_hosts + self.ical_hosts + ('hsi-rents.com', 'www.hsi-rents.com'):
            raise ValueError('Administrative hostname must be independent')
        if not re.fullmatch(r'https://[a-z0-9-]+\.cloudflareaccess\.com', self.issuer):
            raise ValueError('Invalid Access issuer')
        if not self.audience or not self.identities:
            raise ValueError('Access audience and explicit identities required')
        if any(not re.fullmatch(r'[^\s*@]+@[^\s*@]+\.[^\s*@]+', identity) for identity in self.identities):
            raise ValueError('Explicit email identities required; no wildcards')

    @classmethod
    def from_env(cls):
        # Values belong in the private launcher/environment, never in source control.
        if os.getenv('RM_ADMIN_REMOTE_ENABLED', '0') not in {'0', '1'}:
            raise ValueError('Invalid remote mode')
        if os.getenv('RM_ADMIN_REMOTE_MODE', 'read_only') != 'read_only':
            raise ValueError('Only read_only remote access is supported')
        return cls(enabled=os.getenv('RM_ADMIN_REMOTE_ENABLED') == '1',
                   hostname=os.getenv('RM_ADMIN_REMOTE_HOST', '').strip().lower(),
                   issuer=os.getenv('RM_ADMIN_ACCESS_ISSUER', '').rstrip('/'),
                   audience=os.getenv('RM_ADMIN_ACCESS_AUDIENCE', '').strip(),
                   identities=tuple(x.strip().casefold() for x in os.getenv('RM_ADMIN_ACCESS_IDENTITIES', '').split(',') if x.strip()))


class AccessDenied(Exception):
    pass


class AccessVerifier:
    """Bounded JWKS cache, fixed endpoint, no token-controlled URLs or algorithms."""
    def __init__(self, config, fetch=None, clock=time.monotonic):
        self.config, self.fetch, self.clock = config, fetch or self.fetch_keys, clock
        self.keys, self.expires, self.next_fetch = {}, 0, 0
        self.lock = asyncio.Lock()

    async def fetch_keys(self):
        async with httpx.AsyncClient(timeout=3, follow_redirects=False, trust_env=False) as client:
            async with client.stream('GET', self.config.issuer + '/cdn-cgi/access/certs') as response:
                response.raise_for_status()
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > 65536:
                        raise AccessDenied()
                return json.loads(data)

    async def verify(self, token):
        try:
            if not token or len(token) > 16384:
                raise AccessDenied()
            header = jwt.get_unverified_header(token)
            kid = header.get('kid')
            if header.get('alg') != 'RS256' or not isinstance(kid, str) or len(kid) > 128:
                raise AccessDenied()
            if header.get('crit') or header.get('jku') or header.get('x5u'):
                raise AccessDenied()
            async with self.lock:
                now = self.clock()
                if now >= self.expires or kid not in self.keys:
                    if now < self.next_fetch:
                        raise AccessDenied()
                    self.next_fetch = now + 30
                    jwks = await self.fetch()
                    keys = {}
                    for entry in jwks['keys']:
                        if entry.get('kty') != 'RSA' or entry.get('use', 'sig') != 'sig' or entry.get('alg', 'RS256') != 'RS256':
                            continue
                        key = jwt.PyJWK.from_dict(entry).key
                        if key.key_size < 2048 or entry['kid'] in keys:
                            raise AccessDenied()
                        keys[entry['kid']] = key
                    self.keys, self.expires = keys, now + 300
                key = self.keys.get(kid)
                if key is None or now >= self.expires:
                    raise AccessDenied()
            claims = jwt.decode(token, key, algorithms=['RS256'], issuer=self.config.issuer,
                                audience=self.config.audience,
                                options={'require': ['iss', 'aud', 'exp', 'iat', 'sub', 'email']})
            if not isinstance(claims['email'], str) or claims['email'].casefold() not in self.config.identities:
                raise AccessDenied()
            if claims.get('type') not in (None, 'app'):
                raise AccessDenied()
            return {'subject': claims['sub'], 'email': claims['email'], 'source': 'cloudflare_access'}
        except Exception:
            # Never propagate token, claims, key response, URL or exception details.
            raise AccessDenied() from None


def loopback(scope):
    try:
        return ipaddress.ip_address(scope['client'][0]).is_loopback
    except (ValueError, KeyError, TypeError):
        return False


def host_header(headers):
    values = headers.getlist('host')
    if len(values) != 1 or any(c in values[0] for c in '/\\@#? ,'):
        raise AccessDenied()
    parsed = urlsplit('//' + values[0])
    try:
        parsed.port
    except ValueError:
        raise AccessDenied() from None
    return parsed.hostname
