import json
import os
import time
import traceback
import urllib.error
import urllib.request
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import desidata
from desidata import client

TOKEN = 'dd_live_' + 'a' * 64
SIGNED = 'https://storage.example/file.csv?token=private-signature'


class Response:
    def __init__(self, data): self.data = data
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self): return self.data


@pytest.fixture(autouse=True)
def environment(monkeypatch, tmp_path):
    monkeypatch.setenv('DD_TOKEN', TOKEN)
    monkeypatch.setenv('DESIDATA_CACHE_DIR', str(tmp_path))
    monkeypatch.delenv('DESIDATA_BASE_URL', raising=False)


def mock_network(monkeypatch, api=None, storage=b'a,b\n1,2\n', failure=None):
    calls = []
    def open_(self, request, timeout=None):
        calls.append((request, timeout))
        is_api = request.has_header('Authorization')
        if failure and failure[0] == is_api:
            raise urllib.error.HTTPError(request.full_url, failure[1], SIGNED, {}, None)
        return Response((api if api is not None else json.dumps({'download_url': SIGNED}).encode()) if is_api else storage)
    monkeypatch.setattr(urllib.request.OpenerDirector, 'open', open_)
    return calls


def test_load_and_download_isolate_credentials(monkeypatch):
    calls = mock_network(monkeypatch)
    df = desidata.load('education', timeout=7)
    assert df.shape == (1, 2)
    api, storage = [x[0] for x in calls]
    assert api.full_url == 'https://www.desidata.in/api/datasets/education/download'
    assert api.get_header('Authorization') == 'Bearer ' + TOKEN
    assert api.get_header('Accept') == 'application/json'
    assert storage.full_url == SIGNED
    assert storage.get_header('Authorization') is None
    assert [x[1] for x in calls] == [7, 7]
    assert desidata.download('education') == b'a,b\n1,2\n'
    assert len(calls) == 2


@pytest.mark.parametrize('value', ['', 'invalid', TOKEN + '\nInjected: header'])
def test_missing_or_bad_token_never_connects(monkeypatch, value):
    monkeypatch.setenv('DD_TOKEN', value)
    calls = mock_network(monkeypatch)
    with pytest.raises(desidata.DesiDataAuthenticationError): desidata.download('education')
    assert not calls


@pytest.mark.parametrize('origin', ['https://evil.example', 'http://www.desidata.in', 'https://www.desidata.in@evil.example', 'https://www.desidata.in/evil'])
def test_override_never_receives_token(monkeypatch, origin):
    monkeypatch.setenv('DESIDATA_BASE_URL', origin)
    calls = mock_network(monkeypatch)
    with pytest.raises(desidata.DesiDataAuthenticationError): desidata.download('education')
    assert not calls


@pytest.mark.parametrize('payload', [b'not json', b'\xff', b'[]', b'null', b'{}', b'{"download_url":42}', b'{"download_url":"http://storage.example/x"}', b'{"download_url":"https://user:pass@storage.example/x"}', b'{"download_url":"https://storage.example:bad/x"}', b'{"download_url":"https://storage.example/ x"}'])
def test_malformed_response_does_not_download_or_cache(monkeypatch, tmp_path, payload):
    calls = mock_network(monkeypatch, api=payload)
    with pytest.raises(desidata.DesiDataResponseError): desidata.download('education')
    assert len(calls) == 1
    assert not list(tmp_path.glob('*.csv'))


@pytest.mark.parametrize('api,status,error', [(True,401,desidata.DesiDataAuthenticationError),(True,403,desidata.DesiDataPermissionError),(True,404,desidata.DesiDataNotFound),(True,503,desidata.DesiDataServerError),(False,403,desidata.DesiDataSignedUrlError),(False,400,desidata.DesiDataSignedUrlError),(False,410,desidata.DesiDataSignedUrlError),(False,500,desidata.DesiDataServerError),(True,302,desidata.DesiDataServerError)])
def test_safe_failures(monkeypatch, tmp_path, api, status, error):
    mock_network(monkeypatch, failure=(api,status))
    with pytest.raises(error) as exc: desidata.download('education')
    rendered = ''.join(traceback.format_exception(type(exc.value), exc.value, exc.value.__traceback__))
    assert TOKEN not in rendered and SIGNED not in rendered and 'private-signature' not in rendered
    assert not list(tmp_path.glob('*.csv'))


def test_cache_refresh_expiry_and_failed_refresh(monkeypatch, tmp_path):
    calls = mock_network(monkeypatch)
    destination = tmp_path / 'output' / 'data.csv'
    assert desidata.download('education', destination) == destination
    cache = tmp_path / 'education.csv'
    monkeypatch.delenv('DD_TOKEN')
    assert desidata.download('education') == destination.read_bytes()
    with pytest.raises(desidata.DesiDataAuthenticationError): desidata.download('education', refresh=True)
    assert cache.read_bytes() == destination.read_bytes()
    monkeypatch.setenv('DD_TOKEN', TOKEN)
    desidata.download('education', refresh=True)
    assert len(calls) == 4
    os.utime(cache, (0, 0))
    desidata.download('education')
    assert len(calls) == 6


@pytest.mark.parametrize('target', ['https://evil.example/steal','http://www.desidata.in/steal','https://www.desidata.in/other'])
def test_redirect_handler_refuses_all_targets(target):
    request = urllib.request.Request('https://www.desidata.in/api/datasets/x/download', headers={'Authorization':'Bearer '+TOKEN})
    assert client._NoRedirect().redirect_request(request, None, 302, 'Found', {}, target) is None


def test_transport_errors_are_sanitized(monkeypatch):
    def fail(*args, **kwargs): raise urllib.error.URLError(SIGNED + TOKEN)
    monkeypatch.setattr(urllib.request.OpenerDirector, 'open', fail)
    with pytest.raises(desidata.DesiDataConnectionError) as exc: desidata.download('education')
    assert SIGNED not in str(exc.value) and TOKEN not in str(exc.value)


def test_real_urllib_never_follows_bearer_redirect():
    seen = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self):
            seen.append((self.path, self.headers.get('Authorization')))
            self.send_response(302)
            self.send_header('Location', '/credential-trap')
            self.end_headers()
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pytest.raises(desidata.DesiDataServerError):
            client._download_request(f'http://127.0.0.1:{server.server_port}/start', 5, TOKEN)
        assert seen == [('/start', 'Bearer ' + TOKEN)]
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
