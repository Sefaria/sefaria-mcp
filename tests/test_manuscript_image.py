"""get_manuscript_image only fetches images from Sefaria's manuscript hosts.

No network: every outbound request is answered by a fake transport patched onto
requests' HTTPAdapter, keyed by URL.
"""
import asyncio
import base64

import pytest
import requests
from requests.adapters import HTTPAdapter

from sefaria_mcp import logic

ALLOWED_URL = "https://manuscripts.sefaria.org/bomberg/masekhet_22_0008.jpg"
IMAGE_BYTES = b"\xff\xd8\xff\xe0fake-jpeg"


def make_response(request, status=200, body=b"", headers=None):
    response = requests.Response()
    response.status_code = status
    response.headers.update(headers or {})
    response.raw = _BytesRaw(body)
    response.request = request
    response.url = request.url
    return response


class _BytesRaw:
    """Minimal stand-in for urllib3's response, enough for iter_content."""

    def __init__(self, body):
        self._body = body

    def stream(self, chunk_size, decode_content=True):
        for start in range(0, len(self._body), chunk_size):
            yield self._body[start:start + chunk_size]

    def close(self):
        pass

    def release_conn(self):
        pass


@pytest.fixture
def fake_web(monkeypatch):
    """Map URL -> (status, body, headers); records every URL requested."""
    routes = {}
    requested = []

    def send(self, request, **kwargs):
        requested.append(request.url)
        status, body, headers = routes.get(request.url, (404, b"", {}))
        return make_response(request, status, body, headers)

    monkeypatch.setattr(HTTPAdapter, "send", send)
    return routes, requested


def fetch(url):
    return asyncio.run(logic.get_manuscript_image(None, url))


def test_allowed_host_returns_image(fake_web):
    routes, requested = fake_web
    routes[ALLOWED_URL] = (200, IMAGE_BYTES, {"Content-Type": "image/jpeg"})

    result = fetch(ALLOWED_URL)

    assert result["success"] is True
    assert base64.b64decode(result["image_data"]) == IMAGE_BYTES
    assert result["mime_type"] == "image/jpeg"
    assert requested == [ALLOWED_URL]


@pytest.mark.parametrize("url", [
    "http://manuscripts.sefaria.org/bomberg/masekhet_22_0008.jpg",
    "https://evil.example.com/image.jpg",
    "https://manuscripts.sefaria.org.evil.example.com/image.jpg",
    "https://localhost/image.jpg",
    "https://127.0.0.1/image.jpg",
    "https://169.254.169.254/computeMetadata/v1/",
    "http://169.254.169.254/latest/meta-data/",
    "https://[::1]/image.jpg",
    "https://manuscripts.sefaria.org:8443/image.jpg",
    "https://user@manuscripts.sefaria.org/image.jpg",
    "file:///etc/passwd",
    "not a url",
])
def test_disallowed_urls_are_rejected_without_a_request(fake_web, url):
    _, requested = fake_web

    result = fetch(url)

    assert result["success"] is False
    assert "rejected" in result["error"]
    assert requested == []


def test_redirect_within_allowlist_is_followed(fake_web):
    routes, requested = fake_web
    moved_url = "https://manuscripts.sefaria.org/moved.jpg"
    routes[ALLOWED_URL] = (302, b"", {"Location": "/moved.jpg"})
    routes[moved_url] = (200, IMAGE_BYTES, {"Content-Type": "image/jpeg"})

    result = fetch(ALLOWED_URL)

    assert result["success"] is True
    assert requested == [ALLOWED_URL, moved_url]


@pytest.mark.parametrize("location", [
    "http://169.254.169.254/latest/meta-data/",
    "https://internal.cluster.local/secret",
    "http://manuscripts.sefaria.org/downgraded.jpg",
])
def test_redirect_to_disallowed_target_is_rejected(fake_web, location):
    routes, requested = fake_web
    routes[ALLOWED_URL] = (302, b"", {"Location": location})

    result = fetch(ALLOWED_URL)

    assert result["success"] is False
    assert "rejected" in result["error"]
    assert requested == [ALLOWED_URL]


def test_redirect_loop_is_capped(fake_web):
    routes, requested = fake_web
    routes[ALLOWED_URL] = (302, b"", {"Location": ALLOWED_URL})

    result = fetch(ALLOWED_URL)

    assert result["success"] is False
    assert "too many redirects" in result["error"]
    assert len(requested) == logic.MAX_MANUSCRIPT_REDIRECTS + 1


@pytest.mark.parametrize("content_type", ["text/html", "application/json", ""])
def test_non_image_content_type_is_rejected(fake_web, content_type):
    routes, _ = fake_web
    headers = {"Content-Type": content_type} if content_type else {}
    routes[ALLOWED_URL] = (200, b"<html>not an image</html>", headers)

    result = fetch(ALLOWED_URL)

    assert result["success"] is False
    assert "expected an image" in result["error"]


def test_oversize_declared_length_is_rejected(fake_web, monkeypatch):
    monkeypatch.setattr(logic, "MAX_MANUSCRIPT_DOWNLOAD_SIZE", 10)
    routes, _ = fake_web
    routes[ALLOWED_URL] = (200, IMAGE_BYTES, {"Content-Type": "image/jpeg", "Content-Length": "999999"})

    result = fetch(ALLOWED_URL)

    assert result["success"] is False
    assert "download limit" in result["error"]


def test_oversize_streamed_body_is_rejected(fake_web, monkeypatch):
    monkeypatch.setattr(logic, "MAX_MANUSCRIPT_DOWNLOAD_SIZE", 10)
    routes, _ = fake_web
    routes[ALLOWED_URL] = (200, b"x" * 1000, {"Content-Type": "image/jpeg"})

    result = fetch(ALLOWED_URL)

    assert result["success"] is False
    assert "download limit" in result["error"]


def test_allowlist_is_configurable(fake_web, monkeypatch):
    monkeypatch.setattr(logic, "MANUSCRIPT_IMAGE_HOSTS", frozenset({"images.example.org"}))
    routes, _ = fake_web
    other_url = "https://images.example.org/page.png"
    routes[other_url] = (200, IMAGE_BYTES, {"Content-Type": "image/png"})

    assert fetch(other_url)["success"] is True
    assert fetch(ALLOWED_URL)["success"] is False
