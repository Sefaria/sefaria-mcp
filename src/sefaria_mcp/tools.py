from typing import List, Optional
import json

from fastmcp import FastMCP, Context

from .logic import (
    get_text as _get_text,
    search_texts as _search_texts,
    get_situational_info as _get_situational_info,
    knn_search as _knn_search,
    get_english_translations as _get_english_translations,
    get_links as _get_links,
    get_name as _get_name,
    get_shape as _get_text_or_category_shape,
    get_topics as _get_topics,
    get_available_manuscripts as _get_available_manuscripts,
    search_in_book as _search_in_book,
    search_dictionaries as _search_in_dictionaries,
    get_search_path_filter as _get_search_path_filter,
    get_manuscript_image as _get_manuscript_image,
    get_index as _get_index,
)

def register_tools(mcp: FastMCP) -> None:
    """Register all tool functions with the provided :pyclass:`FastMCP` instance."""

    # ---------------------------------------------------------------------------
    # Utility
    # ---------------------------------------------------------------------------

    def _payload_size(payload):  # type: ignore[ann-return-type]
        """Return the length in bytes of *payload* once serialised for transport."""
        if isinstance(payload, (bytes, bytearray)):
            return len(payload)
        if isinstance(payload, str):
            return len(payload.encode())
        try:
            return len(json.dumps(payload, ensure_ascii=False).encode())
        except Exception:
            return len(str(payload).encode())

    # -----------------------------
    # Primary Tools (Top 4)
    # -----------------------------

    @mcp.tool
    async def get_text(ctx: Context, reference: str, version_language: str | None = None) -> str:
        """
        Retrieves the actual text content from a specific reference in the Jewish library.
        
        Args:
            reference: Specific text reference (e.g. 'Genesis 1:1', 'Berakhot 2a').
            version_language: Which language version to retrieve - 'source', 'english', 'both', or omit for all.
        
        Returns:
            JSON string with the text content.
        """
        ctx.log(f"[get_text] called with reference={reference!r}, version_language={version_language!r}")
        result = await _get_text(ctx.log, reference, version_language)
        ctx.log(f"[get_text] response size: {_payload_size(result)} bytes")
        return result

    @mcp.tool
    async def text_search(
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
        ctx.log(f"[text_search] called with query={query!r}, filters={filters!r}, size={size!r}")
        result = await _search_texts(ctx.log, query, filters, size)
        ctx.log(f"[text_search] response size: {_payload_size(result)} bytes")
        # Ensure we always return a string for MCP transport
        return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)

    @mcp.tool
    async def get_current_calendar(ctx: Context) -> str:
        """Provides current Jewish calendar information including Hebrew date, parasha, holidays, etc."""
        ctx.log("[get_current_calendar] called")
        result = await _get_situational_info(ctx.log)
        ctx.log(f"[get_current_calendar] response size: {_payload_size(result)} bytes")
        return result

    @mcp.tool
    async def english_semantic_search(ctx: Context, query: str, filters: Optional[dict] = None) -> str:
        """
        Performs semantic similarity search on English embeddings of texts from Sefaria.
        
        This tool uses semantic similarity to find text chunks that are conceptually 
        related to your query, even if they don't contain the exact same words.  Through this 
        you can discover texts that traditional keyword search or link search might miss
        
        SEARCH TIPS:
        - This database is encoded from English.  Works well only with English queries
        - Search for phrases and sentences close to what you want to find.  Query for something close to the answer, not the question.

        Args:
            query: The search query to find semantically similar text chunks.
            filters: Optional metadata filters to apply to the search. Can include:
                - document_categories: List of document types (e.g., ["Mishnah", "Talmud"]). Use get_name to validate category names.
                - authors: List of author names (e.g., ["Rashi", "Rambam"]). Use get_name to validate author names.
                - eras: List of historical periods. Valid values: "Tannaim", "Amoraim", "Geonim", "Rishonim", "Acharonim", "Contemporary"
                - topics: List of topics (e.g., ["halakhah", "aggadah"]). Use get_name to validate topic names.
                - places: List of composition places (e.g., ["Jerusalem", "Babylon"])
            
        Returns:
            JSON string containing the nearest chunks with their original content and metadata.
        """
        ctx.log(f"[english_semantic_search] called with query={query!r}, filters={filters!r}")
        result = await _knn_search(ctx.log, query, filters)
        ctx.log(f"[english_semantic_search] response size: {_payload_size(result)} bytes")
        return result

    @mcp.tool
    async def get_links_between_texts(ctx: Context, reference: str, with_text: str = "0") -> str:
        """
        Finds all cross-references and connections to a specific text passage.

        Args:
            reference: Specific text reference (e.g. 'Genesis 1:1', 'Berakhot 2a').
            with_text: Whether to include the actual text content ('0' or '1').

        Returns:
            JSON string with the links data.
        """
        ctx.log(f"[get_links_between_texts] called with reference={reference!r}, with_text={with_text!r}")
        result = await _get_links(ctx.log, reference, with_text)
        ctx.log(f"[get_links_between_texts] response size: {_payload_size(result)} bytes")
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
        # Ensure we always return a string for MCP transport
        return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)

    @mcp.tool
    async def search_in_dictionaries(ctx: Context, query: str) -> str:
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
        ctx.log(f"[search_in_dictionaries] called with query={query!r}")
        result = await _search_in_dictionaries(ctx.log, query)
        ctx.log(f"[search_in_dictionaries] response size: {_payload_size(result)} bytes")
        # Ensure we always return a string for MCP transport
        return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)

    # -----------------------------
    # English translations
    # -----------------------------

    @mcp.tool
    async def get_english_translations(ctx: Context, reference: str) -> str:
        """
        Retrieves all available English translations for a specific text reference.

        Args:
            reference: Specific text reference (e.g. 'Genesis 1:1', 'Berakhot 2a').

        Returns:
            JSON string with all English translations.
        """
        ctx.log(f"[get_english_translations] called with reference={reference!r}")
        result = await _get_english_translations(ctx.log, reference)
        ctx.log(f"[get_english_translations] response size: {_payload_size(result)} bytes")
        return result




    # -----------------------------
    # Topics
    # -----------------------------

    @mcp.tool
    async def get_topic_details(
        ctx: Context,
        topic_slug: str,
        with_links: bool = False,
        with_refs: bool = False,
    ) -> str:
        """
        Retrieves detailed information about specific topics in Jewish thought and texts.

        Args:
            topic_slug: Topic identifier slug (e.g. 'moses', 'sabbath').
            with_links: Include links to related topics.
            with_refs: Include text references tagged with this topic.

        Returns:
            JSON string with topic data.
        """
        ctx.log(f"[get_topic_details] called with topic_slug={topic_slug!r}, with_links={with_links!r}, with_refs={with_refs!r}")
        result = await _get_topics(ctx.log, topic_slug, with_links, with_refs)
        ctx.log(f"[get_topic_details] response size: {_payload_size(result)} bytes")
        return result

    @mcp.tool
    async def clarify_name_argument(
        ctx: Context,
        name: str,
        limit: int | None = None,
        type_filter: str | None = None,
    ) -> str:
        """
        Validates and autocompletes text names, book titles, references, topic slugs, author names, and categories.

        Args:
            name: Partial or complete name to validate/complete.
            limit: Maximum number of suggestions to return.
            type_filter: Filter results by type (e.g., 'ref', 'Topic', 'Collection').

        Returns:
            JSON string with name suggestions including authors, topics, and categories.
        """
        ctx.log(f"[clarify_name_argument] called with name={name!r}, limit={limit!r}, type_filter={type_filter!r}")
        result = await _get_name(ctx.log, name, limit, type_filter)
        ctx.log(f"[clarify_name_argument] response size: {_payload_size(result)} bytes")
        return result

    @mcp.tool
    async def clarify_search_path_filter(ctx: Context, book_name: str) -> str:
        """
        Converts a book name into a proper search filter path.

        Args:
            book_name: Name of the book to convert.

        Returns:
            The search filter path string.
        """
        ctx.log(f"[clarify_search_path_filter] called with book_name={book_name!r}")
        result = await _get_search_path_filter(ctx.log, book_name)
        ctx.log(f"[clarify_search_path_filter] response size: {_payload_size(result)} bytes")
        # Ensure we always return a string for MCP transport
        return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)


    @mcp.tool
    async def get_text_or_category_shape(ctx: Context, name: str) -> str:
        """
        Retrieves the hierarchical structure and organization of texts or categories.

        Args:
            name: Text title or category name.

        Returns:
            JSON string with the shape data.
        """
        ctx.log(f"[get_text_or_category_shape] called with name={name!r}")
        result = await _get_text_or_category_shape(ctx.log, name)
        ctx.log(f"[get_text_or_category_shape] response size: {_payload_size(result)} bytes")
        return result

    # -----------------------------
    # Text Structure (moved to bottom)
    # -----------------------------

    @mcp.tool
    async def get_text_catalogue_info(ctx: Context, title: str) -> str:
        """
        Retrieves the bibliographic and structural information (index) for a text or work.

        Args:
            title: Title of the text or work (e.g. 'Genesis', 'Mishnah Berakhot').

        Returns:
            JSON string with the index data.
        """
        ctx.log(f"[get_text_catalogue_info] called with title={title!r}")
        result = await _get_index(ctx.log, title)
        ctx.log(f"[get_text_catalogue_info] response size: {_payload_size(result)} bytes")
        return result

    # -----------------------------
    # Manuscript tools
    # -----------------------------

    @mcp.tool
    async def get_available_manuscripts(ctx: Context, reference: str) -> str:
        """
        Retrieves historical manuscript metadata and image URLs for text passages.

        Args:
            reference: Specific text reference to find manuscripts for.

        Returns:
            JSON string with manuscript metadata.
        """
        ctx.log(f"[get_available_manuscripts] called with reference={reference!r}")
        result = await _get_available_manuscripts(ctx.log, reference)
        ctx.log(f"[get_available_manuscripts] response size: {_payload_size(result)} bytes")
        return result

    @mcp.tool
    async def get_manuscript_image(
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
        ctx.log(f"[get_manuscript_image] called with image_url={image_url!r}, manuscript_title={manuscript_title!r}")
        result = await _get_manuscript_image(ctx.log, image_url, manuscript_title)
        ctx.log(f"[get_manuscript_image] response size: {_payload_size(result)} bytes")
        return json.dumps(result, ensure_ascii=False)

