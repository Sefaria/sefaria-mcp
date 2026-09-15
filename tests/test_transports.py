"""Transport-level tests for the composed /mcp + /sse app.

These drive the real ASGI app in-process, so they cover the routing decisions in
main.py (Route vs Mount, method handling) and the Host/Origin guard on /mcp,
without needing a network or a running server.
"""
import pytest
from starlette.testclient import TestClient

from sefaria_mcp import main

INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "1"},
    },
}
MCP_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


@pytest.fixture(scope="module")
def client():
    # Entering the context runs the combined lifespan, which the streamable
    # transport needs before it can serve its first request.
    with TestClient(main.app) as c:
        yield c


def post_mcp(client, **headers):
    return client.post("/mcp", json=INIT, headers={**MCP_HEADERS, **headers})


# ---- /mcp serves and the guard admits what it should ----

def test_mcp_initialize_with_allowed_host(client):
    r = post_mcp(client, Host="mcp.sefaria.org")
    assert r.status_code == 200
    assert '"protocolVersion"' in r.text


@pytest.mark.parametrize("host", ["devmcp.sefaria.org", "localhost", "127.0.0.1"])
def test_mcp_accepts_each_default_host(client, host):
    assert post_mcp(client, Host=host).status_code == 200


def test_mcp_accepts_allowlisted_origin(client):
    r = post_mcp(client, Host="mcp.sefaria.org", Origin="https://mcp.sefaria.org")
    assert r.status_code == 200


# ---- the guard rejects what it should ----

def test_mcp_rejects_unlisted_host(client):
    r = post_mcp(client, Host="evil.example.com")
    assert r.status_code == 421


def test_mcp_rejects_unlisted_origin(client):
    r = post_mcp(client, Host="mcp.sefaria.org", Origin="https://evil.example.com")
    assert r.status_code == 403


# ---- method handling: GET must be 405, never 404 ----
# A 404 on GET /mcp tells a probing client there is no streamable endpoint at
# all. This is the case the parent Route's missing method list exists for.

@pytest.mark.parametrize("method", ["GET", "PUT", "PATCH"])
def test_mcp_unsupported_methods_are_405_not_404(client, method):
    r = client.request(method, "/mcp", headers={"Host": "mcp.sefaria.org"})
    assert r.status_code == 405


# ---- the guard is scoped to /mcp only ----

@pytest.mark.parametrize(
    "path",
    ["/healthz", "/.well-known/oauth-protected-resource", "/.well-known/oauth-authorization-server"],
)
def test_guard_does_not_apply_outside_mcp(client, path):
    r = client.get(path, headers={"Host": "evil.example.com"})
    assert r.status_code == 200


def test_healthz_body(client):
    assert client.get("/healthz").json() == {"status": "ok"}


# ---- env parsing ----

def test_env_list_unset_uses_default(monkeypatch):
    monkeypatch.delenv("X_LIST", raising=False)
    assert main._env_list("X_LIST", ["a"]) == ["a"]


def test_env_list_blank_uses_default(monkeypatch):
    # Regression: a blank ConfigMap value used to yield [], which FastMCP treats
    # as an authoritative empty allowlist, making /mcp reject every real Host.
    monkeypatch.setenv("X_LIST", "")
    assert main._env_list("X_LIST", ["a"]) == ["a"]


def test_env_list_junk_only_uses_default(monkeypatch):
    monkeypatch.setenv("X_LIST", " , , ")
    assert main._env_list("X_LIST", ["a"]) == ["a"]


def test_env_list_parses_and_strips(monkeypatch):
    monkeypatch.setenv("X_LIST", " a.test ,b.test,, ")
    assert main._env_list("X_LIST", ["zzz"]) == ["a.test", "b.test"]


def test_env_int_invalid_uses_default(monkeypatch):
    monkeypatch.setenv("X_INT", "notanumber")
    assert main._env_int("X_INT", 8088) == 8088


def test_env_int_valid(monkeypatch):
    monkeypatch.setenv("X_INT", "8899")
    assert main._env_int("X_INT", 8088) == 8899
