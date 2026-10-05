"""The User-Agent sefaria-mcp sends to the Sefaria API.

No network: outbound calls are captured by a transport adapter mounted on the
module-level session.
"""
import asyncio
import json

import pytest
import requests
from requests.adapters import BaseAdapter

from sefaria_mcp import logic


class CaptureAdapter(BaseAdapter):
    """Records every PreparedRequest and answers with an empty JSON object."""

    def __init__(self):
        super().__init__()
        self.requests = []

    def send(self, request, **kwargs):
        self.requests.append(request)
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps({}).encode()
        response.headers["Content-Type"] = "application/json"
        response.request = request
        response.url = request.url
        return response

    def close(self):
        pass


@pytest.fixture
def captured(monkeypatch):
    adapter = CaptureAdapter()
    monkeypatch.setattr(logic.http_session, "adapters", {})
    logic.http_session.mount("https://", adapter)
    logic.http_session.mount("http://", adapter)
    return adapter


def test_get_sends_user_agent(captured):
    logic.get_request_json_data("api/texts/", "Genesis 1:1")
    (req,) = captured.requests
    assert req.method == "GET"
    assert req.headers["User-Agent"] == logic.USER_AGENT


def test_post_sends_user_agent_alongside_per_call_headers(captured):
    asyncio.run(logic._search(None, "shabbat"))
    (req,) = captured.requests
    assert req.method == "POST"
    assert req.headers["User-Agent"] == logic.USER_AGENT
    # The per-call header must merge over the session default, not replace it.
    assert req.headers["Content-Type"] == "application/json"


@pytest.mark.parametrize("value, expected", [
    (None, "sefaria-mcp"),
    ("", "sefaria-mcp"),
    ("   ", "sefaria-mcp"),
    ("prod", "Sefaria/sefaria-mcp (prod)"),
    (" dev ", "Sefaria/sefaria-mcp (dev)"),
    ("x(y)\n", "Sefaria/sefaria-mcp (xy)"),
])
def test_user_agent_from_deployment_env(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv("SEFARIA_MCP_DEPLOYMENT", raising=False)
    else:
        monkeypatch.setenv("SEFARIA_MCP_DEPLOYMENT", value)
    assert logic._user_agent() == expected
