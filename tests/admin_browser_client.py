"""Legacy local HTTP tests act like the browser CSRF transport, not a bypass."""
import re
from fastapi.testclient import TestClient


class AdminBrowserClient(TestClient):
    def __init__(self, app, **kwargs):
        kwargs.setdefault('base_url', 'http://127.0.0.1')
        kwargs.setdefault('client', ('127.0.0.1', 12345))
        super().__init__(app, **kwargs)

    def request(self, method, url, **kwargs):
        if method.upper() not in {'GET', 'HEAD', 'OPTIONS'}:
            page = super().request('GET', '/')
            token = re.search(r'name="rm-admin-csrf" content="([^"]+)"', page.text)
            if token:
                headers = dict(kwargs.get('headers') or {})
                headers.setdefault('X-RM-CSRF', token[1])
                kwargs['headers'] = headers
        return super().request(method, url, **kwargs)
