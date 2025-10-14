from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse
from .tools import register_tools


mcp = FastMCP("Sefaria MCP 📚")
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


def main() -> None:  # pragma: no cover – simple wrapper for console_scripts
    mcp.run(transport="sse", path="/sse", host="0.0.0.0", port=7860)

if __name__ == "__main__":
    main() 
