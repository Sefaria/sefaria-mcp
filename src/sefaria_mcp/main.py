from fastmcp import FastMCP

# Local imports
from .tools import register_tools

# ---------------------------------------------------------------------------
# Create the FastMCP server instance. Giving the server a descriptive name is
# recommended for easier discovery when multiple MCP servers are running.
# ---------------------------------------------------------------------------

mcp = FastMCP("Sefaria MCP 📚")

# Register all tools defined in the tools module. This keeps the
# top-level file small while still using the recommended `@mcp.tool` 
# decorators inside the tools module.
register_tools(mcp)

# Create a Starlette-compatible ASGI app for use with Uvicorn/Hypercorn.
# This exposes the MCP endpoint at `/sse` and keeps FastMCP's session manager intact.
app = mcp.http_app(transport="sse")
app.router.redirect_slashes = False

# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------


def main() -> None:  # pragma: no cover – simple wrapper for console_scripts
    mcp.run(transport="sse", path="/sse", host="0.0.0.0", port=8088)

if __name__ == "__main__":
    main() 
