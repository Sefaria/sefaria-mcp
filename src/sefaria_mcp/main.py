import logging
import os
import sys

from fastmcp import FastMCP
from prometheus_client import start_http_server, Counter, Histogram, Gauge
from prometheus_fastapi_instrumentator import Instrumentator
from starlette.requests import Request
from starlette.responses import JSONResponse

from .tools import register_tools, set_metrics


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

# Defensive variants for clients that (incorrectly) append your path:
@mcp.custom_route("/.well-known/oauth-protected-resource/sse", methods=["GET"])
async def protected_resource_endpoint_sse(request: Request) -> JSONResponse:
    return JSONResponse(PROTECTED_RESOURCE_DOC)

@mcp.custom_route("/.well-known/oauth-authorization-server/sse", methods=["GET"])
async def authorization_server_endpoint_sse(request: Request) -> JSONResponse:
    return JSONResponse({})

# Get the FastMCP app - no need for custom wrapper
app = mcp.http_app(transport="sse")
app.router.redirect_slashes = False

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    """Configure logging for MCP usage. Structured JSON logs go to stdout for Prometheus/Loki correlation."""
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.INFO)
        # Timestamp + level; message contains JSON for mcp_tool_usage
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        root.addHandler(handler)
    # Reduce noise from third-party loggers
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


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
    ['tool_name'],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5]  # Enables accurate p95/p99
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
    # SEFARIA_MCP_PORT = app (SSE) port; SEFARIA_MCP_METRICS_PORT = metrics scrape port
    metrics_port = int(os.environ.get("SEFARIA_MCP_METRICS_PORT", "9090"))
    try:
        start_http_server(metrics_port)
    except OSError as exc:
        logger.warning("Skipping metrics server on port %s: %s", metrics_port, exc)


def main() -> None:  # pragma: no cover – simple wrapper for console_scripts
    _configure_logging()
    start_metrics_server()
    mcp.run(transport="sse", path="/sse", host="0.0.0.0", port=int(os.environ.get("SEFARIA_MCP_PORT", "8088")))

if __name__ == "__main__":
    main()
