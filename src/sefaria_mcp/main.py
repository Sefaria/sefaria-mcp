from fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.responses import JSONResponse, Response
from starlette.routing import Route, Mount
from .tools import register_tools


mcp = FastMCP("Sefaria MCP 📚")
register_tools(mcp)

# Create the FastMCP app
fastmcp_app = mcp.http_app(transport="sse")
fastmcp_app.router.redirect_slashes = False

# ---- WELL-KNOWN METADATA (no-auth stubs) ----
PROTECTED_RESOURCE_DOC = {
    # Use your actual origin, no trailing slash:
    "resource": "https://devmcp.sefaria.org",
    "authorization_servers": []  # <- explicitly none
}

def protected_resource_endpoint(request):
    return JSONResponse(PROTECTED_RESOURCE_DOC)

def authorization_server_endpoint(request):
    # Empty JSON is fine; some clients just want a 200 JSON.
    return JSONResponse({})

# Create a parent Starlette app with well-known endpoints
app = Starlette()
app.router.routes.extend([
    Route("/.well-known/oauth-protected-resource", protected_resource_endpoint, methods=["GET"]),
    Route("/.well-known/oauth-authorization-server", authorization_server_endpoint, methods=["GET"]),
    # Defensive variants for clients that (incorrectly) append your path:
    Route("/.well-known/oauth-protected-resource/sse", protected_resource_endpoint, methods=["GET"]),
    Route("/.well-known/oauth-authorization-server/sse", authorization_server_endpoint, methods=["GET"]),
    # Mount FastMCP app to handle all other routes
    Mount("/", fastmcp_app)
])


def main() -> None:  # pragma: no cover – simple wrapper for console_scripts
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8088)

if __name__ == "__main__":
    main() 
