"""The User-Agent sefaria-mcp presents to the Sefaria API.

The default names only the software, because this project is open source and
self-hosted by third parties. Sefaria's own deployment opts into the first-party
marker with SEFARIA_MCP_FIRST_PARTY=1. No network: outbound calls are captured
by a transport adapter mounted on the module-level session.
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


# ---- the header actually goes out, on GET and on POST ----

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


# ---- what the header says ----

def test_default_names_only_the_software(monkeypatch):
    monkeypatch.delenv("SEFARIA_MCP_FIRST_PARTY", raising=False)
    assert logic.configured_user_agent() == "sefaria-mcp"


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", " Yes "])
def test_first_party_marker_is_opt_in(monkeypatch, value):
    monkeypatch.setenv("SEFARIA_MCP_FIRST_PARTY", value)
    assert logic.configured_user_agent() == "Sefaria/sefaria-mcp"


@pytest.mark.parametrize("value", ["", "0", "false", "no", "junk"])
def test_first_party_marker_needs_a_truthy_value(monkeypatch, value):
    monkeypatch.setenv("SEFARIA_MCP_FIRST_PARTY", value)
    assert logic.configured_user_agent() == "sefaria-mcp"


def test_version_is_included_only_when_known():
    assert logic.build_user_agent(False, "1.8.0") == "sefaria-mcp/1.8.0"
    assert logic.build_user_agent(True, "1.8.0") == "Sefaria/sefaria-mcp (1.8.0)"
    assert logic.build_user_agent(False, None) == "sefaria-mcp"
    assert logic.build_user_agent(True, None) == "Sefaria/sefaria-mcp"


def test_no_stray_url_comment():
    for ua in (logic.build_user_agent(False), logic.build_user_agent(True)):
        assert "http" not in ua and "+" not in ua
