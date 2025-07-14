from typing import List, Optional
import json

from fastmcp import FastMCP, Context

from .logic import (
    search_texts as _search_texts,
    search_in_book as _search_in_book,
    search_dictionaries as _search_dictionaries,
    get_search_path_filter as _get_search_path_filter,
    get_manuscript as _get_manuscript,
    get_situational_info as _get_situational_info,
    knn_search as _knn_search,
)

def register_tools(mcp: FastMCP) -> None:
    """Register all tool functions with the provided :pyclass:`FastMCP` instance."""

    @mcp.tool
    async def search_texts(
        ctx: Context,
        query: str,
        filters: Optional[List[str]] = None,
        size: int = 10,
    ) -> str:
        """
        Searches across the entire Jewish library for passages containing specific terms.
        
        SEARCH TIPS:
        - Hebrew/Aramaic searches are more reliable than English translations
        - English searches can be hit-and-miss due to translation variations
        - If no results found, try searching with fewer words
        - Use specific Hebrew terms when possible for better accuracy
        
        Args:
            query: Search terms (Hebrew/Aramaic preferred for best results).
            filters: Category paths to limit search scope.
            size: Maximum number of results to return.
            
        Returns:
            JSON string with search results.
        """
        ctx.log(f"[search_texts] called with query={query!r}, filters={filters!r}, size={size!r}")
        result = await _search_texts(ctx.log, query, filters, size)
        ctx.log(f"[search_texts] response size: {_payload_size(result)} bytes")
        return result

    @mcp.tool
    async def search_in_book(
        ctx: Context,
        query: str,
        book_name: str,
        size: int = 10,
    ) -> str:
        """
        Searches for content within one specific book or text work.

        SEARCH TIPS:
        - Hebrew/Aramaic searches are more reliable than English translations
        - English searches can be hit-and-miss due to translation variations
        - If no results found, try searching with fewer words
        - Use specific Hebrew terms when possible for better accuracy

        Args:
            query: Search terms to find within the specified book (Hebrew/Aramaic preferred).
            book_name: Exact name of the book to search within.
            size: Maximum number of results to return.

        Returns:
            JSON string with search results.
        """
        ctx.log(f"[search_in_book] called with query={query!r}, book_name={book_name!r}, size={size!r}")
        result = await _search_in_book(ctx.log, query, book_name, size)
        ctx.log(f"[search_in_book] response size: {_payload_size(result)} bytes")
        return result

    @mcp.tool
    async def search_dictionaries(ctx: Context, query: str) -> str:
        """
        Searches specifically within Jewish reference dictionaries.

        SEARCH TIPS:
        - Hebrew/Aramaic searches are more reliable than English translations
        - English searches can be hit-and-miss due to translation variations
        - If no results found, try searching with fewer words
        - Use specific Hebrew terms when possible for better accuracy

        Args:
            query: Hebrew, Aramaic, or English term to look up (Hebrew/Aramaic preferred).

        Returns:
            JSON string with dictionary entries.
        """
        ctx.log(f"[search_dictionaries] called with query={query!r}")
        result = await _search_dictionaries(ctx.log, query)
        ctx.log(f"[search_dictionaries] response size: {_payload_size(result)} bytes")
        return result

    @mcp.tool
    async def get_search_path_filter(ctx: Context, book_name: str) -> str:
        """
        Converts a book name into a proper search filter path.

        Args:
            book_name: Name of the book to convert.

        Returns:
            The search filter path string.
        """
        ctx.log(f"[get_search_path_filter] called with book_name={book_name!r}")
        result = await _get_search_path_filter(ctx.log, book_name)
        ctx.log(f"[get_search_path_filter] response size: {_payload_size(result)} bytes")
        return result

    @mcp.tool
    async def get_manuscript(
        ctx: Context,
        image_url: str,
        manuscript_title: Optional[str] = None,
    ) -> str:
        """
        Downloads and returns a specific manuscript image from a given image URL.

        Args:
            image_url: The URL of the manuscript image to download.
            manuscript_title: Title or description for the manuscript.

        Returns:
            JSON string containing the image data and metadata.
        """
        ctx.log(f"[get_manuscript] called with image_url={image_url!r}, manuscript_title={manuscript_title!r}")
        result = await _get_manuscript(ctx.log, image_url, manuscript_title)
        ctx.log(f"[get_manuscript] response size: {_payload_size(result)} bytes")
        return json.dumps(result, ensure_ascii=False)

    @mcp.tool
    async def knn_search(ctx: Context, query: str) -> str:
        """
        Performs KNN (K-Nearest Neighbors) search on embeddings of texts from Sefaria.
        
        This tool uses semantic similarity to find text chunks that are conceptually 
        related to your query, even if they don't contain the exact same words.  Through this 
        you can discover texts that traditional keyword search or link search might miss
        
        SEARCH TIPS:
        - This database is encoded from English.  Works well only with English queries
        - Search for phrases and sentences close to what you want to find.  Query for something close to the answer, not the question.

        Args:
            query: The search query to find semantically similar text chunks.
            
        Returns:
            JSON string containing the nearest chunks with their original content and metadata.
        """
        ctx.log(f"[knn_search] called with query={query!r}")
        result = await _knn_search(ctx.log, query)
        ctx.log(f"[knn_search] response size: {_payload_size(result)} bytes")
        return result

    @mcp.tool
    async def get_situational_info(ctx: Context) -> str:
        """Provides current Jewish calendar information including Hebrew date, parasha, holidays, etc."""
        ctx.log("[get_situational_info] called")
        result = await _get_situational_info(ctx.log)
        ctx.log(f"[get_situational_info] response size: {_payload_size(result)} bytes")
        return result

# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _payload_size(payload):  # type: ignore[ann-return-type]
    if isinstance(payload, (bytes, bytearray)):
        return len(payload)
    if isinstance(payload, str):
        return len(payload.encode())
    try:
        return len(json.dumps(payload, ensure_ascii=False).encode())
    except Exception:
        return len(str(payload).encode()) 