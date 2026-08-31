import contextlib
import logging
import os
from collections.abc import AsyncIterator

import uvicorn
from fastmcp import FastMCP
from prometheus_client import start_http_server, Counter, Histogram, Gauge
from prometheus_fastapi_instrumentator import Instrumentator
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from .tools import register_tools, set_metrics


def _csv_env(name: str, default: list[str]) -> list[str]:
    """Read a comma-separated allowlist, falling back to a secure default."""
    value = os.getenv(name)
    if value is None:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


DEFAULT_ALLOWED_HOSTS = [
    "127.0.0.1",
    "127.0.0.1:*",
    "localhost",
    "localhost:*",
    "[::1]",
    "[::1]:*",
    "mcp.sefaria.org",
    "devmcp.sefaria.org",
]
DEFAULT_ALLOWED_ORIGINS = [
    "http://127.0.0.1",
    "http://127.0.0.1:*",
    "http://localhost",
    "http://localhost:*",
    "http://[::1]",
    "http://[::1]:*",
    "https://mcp.sefaria.org",
    "https://devmcp.sefaria.org",
]
HTTP_SECURITY = {
    "host_origin_protection": True,
    "allowed_hosts": _csv_env("SEFARIA_MCP_ALLOWED_HOSTS", DEFAULT_ALLOWED_HOSTS),
    "allowed_origins": _csv_env("SEFARIA_MCP_ALLOWED_ORIGINS", DEFAULT_ALLOWED_ORIGINS),
}


mcp = FastMCP("Sefaria MCP 📚")

# Initialize metrics dictionary to pass to tools
metrics_dict = {
    'calls': None,
    'duration': None,
    'payload_bytes': None,
    'errors': None,
}

register_tools(mcp)

# ---- WELL-KNOWN METADATA (no-auth stubs) ----
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


# Defensive variants for clients that append the configured MCP path.
@mcp.custom_route("/.well-known/oauth-protected-resource/sse", methods=["GET"])
async def protected_resource_endpoint_sse(request: Request) -> JSONResponse:
    return JSONResponse(PROTECTED_RESOURCE_DOC)

@mcp.custom_route("/.well-known/oauth-authorization-server/sse", methods=["GET"])
async def authorization_server_endpoint_sse(request: Request) -> JSONResponse:
    return JSONResponse({})

@mcp.custom_route("/.well-known/oauth-protected-resource/mcp", methods=["GET"])
async def protected_resource_endpoint_mcp(request: Request) -> JSONResponse:
    return JSONResponse(PROTECTED_RESOURCE_DOC)

@mcp.custom_route("/.well-known/oauth-authorization-server/mcp", methods=["GET"])
async def authorization_server_endpoint_mcp(request: Request) -> JSONResponse:
    return JSONResponse({})

@mcp.custom_route("/healthz", methods=["GET"])
async def healthz_endpoint(request: Request) -> JSONResponse:
    """Health check endpoint - returns 200 OK if server is responsive."""
    return JSONResponse({"status": "ok"})

# Keep each FastMCP transport as an intact ASGI app. This preserves its own
# middleware, app state, and transport context instead of copying internal routes.
streamable_app = mcp.http_app(
    transport="http",
    path="/mcp",
    **HTTP_SECURITY,
)
sse_app = mcp.http_app(transport="sse", path="/sse")
streamable_app.router.redirect_slashes = False
sse_app.router.redirect_slashes = False


@contextlib.asynccontextmanager
async def combined_lifespan(_: Starlette) -> AsyncIterator[None]:
    """Run both FastMCP transport lifespans for the shared server."""
    async with streamable_app.lifespan(streamable_app):
        async with sse_app.lifespan(sse_app):
            yield


# Match /mcp first, then delegate every legacy/custom route to the SSE app.
# Calling the child ASGI apps directly lets each child set scope["app"] to itself,
# which keeps FastMCP's Context.transport accurate for both transports.
app = Starlette(
    routes=[
        Route("/mcp", endpoint=streamable_app),
        Mount("/", app=sse_app),
    ],
    lifespan=combined_lifespan,
)
app.router.redirect_slashes = False

logger = logging.getLogger(__name__)

# Expose Prometheus metrics for MCP health and usage monitoring.
# Instrument the app that Uvicorn actually serves so both transports are observed.
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
    'Number of active MCP connections'
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
    metrics_port = int(os.getenv("SEFARIA_MCP_METRICS_PORT", "9090"))
    try:
        start_http_server(metrics_port)
    except OSError as exc:
        logger.warning("Skipping metrics server on port %s: %s", metrics_port, exc)


def main() -> None:  # pragma: no cover – simple wrapper for console_scripts
    start_metrics_server()
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("SEFARIA_MCP_PORT", "8088")),
        lifespan="on",
    )


if __name__ == "__main__":
    main()
