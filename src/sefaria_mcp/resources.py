import json
from fastmcp import FastMCP, Context

from .logic import (
    get_text as _get_text,
    get_english_translations as _get_english_translations,
    get_index as _get_index,
    get_links as _get_links,
    get_name as _get_name,
    get_shape as _get_shape,
    get_topics as _get_topics,
    get_manuscript_info as _get_manuscript_info,
)

def register_resources(mcp: FastMCP) -> None:
    """
    Register all resource endpoints **as tools** on the provided :pyclass:`FastMCP` instance.
    Some clients don't yet support resources.
    """

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
    # Text retrieval
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
    # Index
    # -----------------------------

    @mcp.tool
    async def get_index(ctx: Context, title: str) -> str:
        """
        Retrieves the bibliographic and structural information (index) for a text or work.

        Args:
            title: Title of the text or work (e.g. 'Genesis', 'Mishnah Berakhot').

        Returns:
            JSON string with the index data.
        """
        ctx.log(f"[get_index] called with title={title!r}")
        result = await _get_index(ctx.log, title)
        ctx.log(f"[get_index] response size: {_payload_size(result)} bytes")
        return result

    # -----------------------------
    # Links
    # -----------------------------

    @mcp.tool
    async def get_links(ctx: Context, reference: str, with_text: str = "0") -> str:
        """
        Finds all cross-references and connections to a specific text passage.

        Args:
            reference: Specific text reference (e.g. 'Genesis 1:1', 'Berakhot 2a').
            with_text: Whether to include the actual text content ('0' or '1').

        Returns:
            JSON string with the links data.
        """
        ctx.log(f"[get_links] called with reference={reference!r}, with_text={with_text!r}")
        result = await _get_links(ctx.log, reference, with_text)
        ctx.log(f"[get_links] response size: {_payload_size(result)} bytes")
        return result

    # -----------------------------
    # Name autocomplete
    # -----------------------------

    @mcp.tool
    async def get_name(
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
        ctx.log(f"[get_name] called with name={name!r}, limit={limit!r}, type_filter={type_filter!r}")
        result = await _get_name(ctx.log, name, limit, type_filter)
        ctx.log(f"[get_name] response size: {_payload_size(result)} bytes")
        return result

    # -----------------------------
    # Shape
    # -----------------------------

    @mcp.tool
    async def get_shape(ctx: Context, name: str) -> str:
        """
        Retrieves the hierarchical structure and organization of texts or categories.

        Args:
            name: Text title or category name.

        Returns:
            JSON string with the shape data.
        """
        ctx.log(f"[get_shape] called with name={name!r}")
        result = await _get_shape(ctx.log, name)
        ctx.log(f"[get_shape] response size: {_payload_size(result)} bytes")
        return result

    # -----------------------------
    # Topics
    # -----------------------------

    @mcp.tool
    async def get_topics(
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
        ctx.log(f"[get_topics] called with topic_slug={topic_slug!r}, with_links={with_links!r}, with_refs={with_refs!r}")
        result = await _get_topics(ctx.log, topic_slug, with_links, with_refs)
        ctx.log(f"[get_topics] response size: {_payload_size(result)} bytes")
        return result

    # -----------------------------
    # Manuscript info
    # -----------------------------

    @mcp.tool
    async def get_manuscript_info(ctx: Context, reference: str) -> str:
        """
        Retrieves historical manuscript metadata and image URLs for text passages.

        Args:
            reference: Specific text reference to find manuscripts for.

        Returns:
            JSON string with manuscript metadata.
        """
        ctx.log(f"[get_manuscript_info] called with reference={reference!r}")
        result = await _get_manuscript_info(ctx.log, reference)
        ctx.log(f"[get_manuscript_info] response size: {_payload_size(result)} bytes")
        return result 