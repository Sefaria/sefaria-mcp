import contextlib
import logging
import os

import uvicorn
from fastmcp import FastMCP
from prometheus_client import start_http_server, Counter, Histogram, Gauge
from prometheus_fastapi_instrumentator import Instrumentator
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from .tools import register_tools, set_metrics


logger = logging.getLogger(__name__)

mcp = FastMCP("Sefaria MCP 📚")

# Initialize metrics dictionary to pass to tools
metrics_dict = {
    'calls': None,
    'duration': None,
    'payload_bytes': None,
    'errors': None,
}

register_tools(mcp)


def _env_int(name: str, default: int) -> int:
    """Read an int from the environment, falling back if unset or unparseable."""
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("Ignoring invalid %s=%r; using %s", name, raw, default)
        return default


def _env_list(name: str, default: list[str]) -> list[str]:
    """Read a comma-separated list from the environment, falling back if unset or empty.

    An empty value must fall back rather than yield []: FastMCP treats an explicit
    allowlist as authoritative, so [] would make /mcp loopback-only and reject
    every real request with 421. A blank ConfigMap value is an easy way to get here.
    """
    raw = os.environ.get(name)
    items = [item.strip() for item in raw.split(",") if item.strip()] if raw else []
    if not items:
        if raw:
            logger.warning("Ignoring empty %s=%r; using %s", name, raw, default)
        return default
    return items


HOST = os.environ.get("SEFARIA_MCP_HOST", "0.0.0.0")
PORT = _env_int("SEFARIA_MCP_PORT", 8088)
METRICS_PORT = _env_int("SEFARIA_MCP_METRICS_PORT", 9090)

# Streamable HTTP requires Host/Origin validation to prevent DNS-rebinding attacks,
# where a malicious page resolves its own domain to 127.0.0.1 and talks to a local
# MCP server from the browser. FastMCP rejects an unlisted Host with 421 and an
# unlisted Origin with 403. Loopback hosts are always allowed by FastMCP itself.
#
# Origins need their own list because the pod is reached over plain HTTP behind the
# gateway: FastMCP's same-origin fallback would compare a browser's
# "https://mcp.sefaria.org" against a reconstructed "http://mcp.sefaria.org" and
# reject it. Listing the public https origins explicitly avoids that mismatch.
ALLOWED_HOSTS = _env_list(
    "SEFARIA_MCP_ALLOWED_HOSTS", ["mcp.sefaria.org", "devmcp.sefaria.org"]
)
ALLOWED_ORIGINS = _env_list(
    "SEFARIA_MCP_ALLOWED_ORIGINS",
    ["https://mcp.sefaria.org", "https://devmcp.sefaria.org"],
)
# Escape hatch: set SEFARIA_MCP_HOST_PROTECTION=off to disable the guard without a
# redeploy if an unanticipated Host header turns out to be legitimate in-cluster.
HOST_PROTECTION = os.environ.get("SEFARIA_MCP_HOST_PROTECTION", "on").lower() != "off"
if not HOST_PROTECTION:
    logger.warning("SEFARIA_MCP_HOST_PROTECTION=off: /mcp will accept any Host and Origin header")

# ---- WELL-KNOWN METADATA (no-auth stubs) ----
# These empty 200s are deliberate and load-bearing: claude.ai's connector broker
# treats an empty discovery document as a terminal "no auth needed" answer, while
# a 404 sends it on to a dynamic-registration attempt that fails. Removing them
# broke the settings Connect button and was reverted (PR #25 -> PR #28). Do not
# "fix" these to 404s without re-measuring the connector flow first.
PROTECTED_RESOURCE_DOC = {
    # Use your actual origin, no trailing slash:
    "resource": "https://devmcp.sefaria.org",
    "authorization_servers": []  # <- explicitly none
}

# Add well-known OAuth endpoints using FastMCP's custom route decorator
@mcp.custom_route("/.well-known/oauth-protected-resource", methods=["GET"])
async def protected_resource_endpoint(request: Request) -> JSONResponse:
    return JSONResponse(PROTECTED_RESOURCE_DOC)

@mcp.custom_route("/.well-known/oauth-authorization-server", methods=["GET"])
async def authorization_server_endpoint(request: Request) -> JSONResponse:
    return JSONResponse({})

# Defensive variants for clients that (incorrectly) append your path:
@mcp.custom_route("/.well-known/oauth-protected-resource/sse", methods=["GET"])
async def protected_resource_endpoint_sse(request: Request) -> JSONResponse:
    return JSONResponse(PROTECTED_RESOURCE_DOC)

@mcp.custom_route("/.well-known/oauth-authorization-server/sse", methods=["GET"])
async def authorization_server_endpoint_sse(request: Request) -> JSONResponse:
    return JSONResponse({})

@mcp.custom_route("/healthz", methods=["GET"])
async def healthz_endpoint(request: Request) -> JSONResponse:
    """Health check endpoint - returns 200 OK if server is responsive."""
    return JSONResponse({"status": "ok"})


# ---- TRANSPORTS ----
# One ASGI app per transport, composed under a single parent Starlette app.
#
# /mcp  - Streamable HTTP, the transport current MCP clients expect.
# /sse  - the legacy HTTP+SSE transport, kept for backward compatibility while
#         existing clients migrate. Both serve the same tools.
#
# stateless_http=True matters operationally: the deployment is a single replica
# holding session state in pod memory, so a stateful transport loses every live
# session on each rollout. Stateless mode builds a fresh transport per request.
# It also means /mcp serves POST and DELETE only - FastMCP drops the GET
# notification stream, which has nothing to deliver when no session is retained.
sse_app = mcp.http_app(transport="sse", path="/sse")
streamable_app = mcp.http_app(
    transport="http",
    path="/mcp",
    stateless_http=True,
    host_origin_protection=HOST_PROTECTION,
    allowed_hosts=ALLOWED_HOSTS if HOST_PROTECTION else None,
    allowed_origins=ALLOWED_ORIGINS if HOST_PROTECTION else None,
)


@contextlib.asynccontextmanager
async def _lifespan(app: Starlette):
    """Run both transports' lifespans.

    Starlette does not propagate its lifespan to sub-applications, and the
    streamable HTTP app needs its own lifespan to build the session manager -
    without this it raises "Task group is not initialized" on the first request.
    """
    async with contextlib.AsyncExitStack() as stack:
        await stack.enter_async_context(streamable_app.lifespan(app))
        await stack.enter_async_context(sse_app.lifespan(app))
        yield


# Route, not Mount: Mount strips its prefix, so "/mcp" would reach the sub-app as
# an empty path and 404 - only "/mcp/" would work. Route passes the path through
# intact. It also declares no method list, because restricting methods here would
# make a GET of "/mcp" a partial match, letting the "/" Mount answer 404 and tell
# a probing client there is no streamable endpoint at all; passing every method
# through lets the sub-app return the 405 the spec calls for. The sub-app keeps
# its own middleware stack, which scopes the Host/Origin guard to this endpoint.
#
# sse_app is mounted at "/" last so it catches /sse, /messages/ and the shared
# custom routes (/healthz, the well-known documents).
app = Starlette(
    routes=[
        Route("/mcp", endpoint=streamable_app),
        Mount("/", app=sse_app),
    ],
    lifespan=_lifespan,
)
app.router.redirect_slashes = False

# Expose Prometheus metrics for MCP health and usage monitoring
instrumentator = Instrumentator(
    should_group_status_codes=True,
    should_ignore_untemplated=True,
    should_instrument_requests_inprogress=True,
)
instrumentator.instrument(app)

# MCP-specific metrics
mcp_tool_calls_total = Counter(
    'mcp_tool_calls_total',
    'Total number of MCP tool calls',
    ['tool_name', 'status']
)

mcp_tool_duration_seconds = Histogram(
    'mcp_tool_duration_seconds',
    'Duration of MCP tool calls in seconds',
    ['tool_name']
)

mcp_tool_payload_bytes = Histogram(
    'mcp_tool_payload_bytes',
    'Size of MCP tool response payloads in bytes',
    ['tool_name'],
    buckets=[100, 1000, 10000, 100000, 1000000, 10000000]
)

mcp_active_connections = Gauge(
    'mcp_active_connections',
    'Number of active MCP SSE connections'
)

mcp_errors_total = Counter(
    'mcp_errors_total',
    'Total number of MCP errors',
    ['tool_name', 'error_type']
)

# Update metrics dictionary with actual metric objects
metrics_dict['calls'] = mcp_tool_calls_total
metrics_dict['duration'] = mcp_tool_duration_seconds
metrics_dict['payload_bytes'] = mcp_tool_payload_bytes
metrics_dict['errors'] = mcp_errors_total

# Pass metrics to tools module
set_metrics(metrics_dict)


def start_metrics_server() -> None:
    """Start the Prometheus metrics endpoint without crashing if the port is busy."""
    try:
        start_http_server(METRICS_PORT)
    except OSError as exc:
        logger.warning("Skipping metrics server on port %s: %s", METRICS_PORT, exc)


def main() -> None:  # pragma: no cover – simple wrapper for console_scripts
    start_metrics_server()
    # Serve the composed app directly. mcp.run() builds its own single-transport
    # app internally, which would drop /mcp and the instrumentation attached here.
    uvicorn.run(app, host=HOST, port=PORT)

if __name__ == "__main__":
    main()
