"""Page title and consultation status in the shared compact admin header."""
import html
import re
import pytest
from fastapi.testclient import TestClient
from tests.integration.test_mobile_remote_presentation import remote_app, config, key
from tests.integration.test_admin_remote_security import headers


@pytest.mark.parametrize('remote', [False, True])
@pytest.mark.parametrize('path', ['/', '/gantt/', '/persons', '/owners', '/expenses', '/settlements'])
def test_header_uses_page_title_and_server_consultation_state(remote_app, key, remote, path):
    with TestClient(remote_app, base_url='https://admin.example.test' if remote else 'http://127.0.0.1',
                    client=('127.0.0.1', 111), headers=headers(key) if remote else {}) as client:
        response = client.get(path)
        assert response.status_code == 200
        text = response.text
        title = html.unescape(re.search(r'<title>(.*?)</title>', text, re.S)[1]).strip().replace(' · RentalManager', '')
        label = html.unescape(re.search(r'class="rm-mobile-page-title"[^>]*>(.*?)</span>', text, re.S)[1])
        assert label == title
        assert text.count('aria-label="Abrir menú"') == 1
        assert ('class="badge rounded-pill text-bg-light border rm-consultation"' in text) == remote
        assert 'class="navbar-brand mb-0 h1"' in text  # Desktop branding remains present.
