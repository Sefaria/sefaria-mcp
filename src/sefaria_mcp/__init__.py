"""Top-level package for the Sefaria FastMCP server."""

from importlib import import_module
from typing import TYPE_CHECKING

__all__: list[str] = ["mcp", "main"]

# Import lazily to avoid double-import issues when running as a module
if TYPE_CHECKING:  # pragma: no cover - for static analyzers only
    from .main import mcp, main  # noqa: F401


def __getattr__(name: str):
    if name in __all__:
        module = import_module(".main", __name__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name}")
