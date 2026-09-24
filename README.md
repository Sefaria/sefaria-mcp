# Sefaria MCP Server

A modern [MCP (Model Context Protocol)](https://github.com/ai21labs/model-context-protocol) server for accessing the Jewish library via the Sefaria API.

## What does this server do?

This server exposes the Sefaria Jewish library as a set of 14 MCP tools, allowing LLMs and other MCP clients to:

**Primary Tools:**
- **get_text** - Retrieve Jewish texts by reference (e.g., "Genesis 1:1")
- **text_search** - Search across the entire Jewish library
- **get_current_calendar** - Get situational Jewish calendar information. Accepts `diaspora` (`true` for Diaspora, `false` for Israel) for weeks when Torah reading schedules diverge.

**Core Tools:**
- **get_links_between_texts** - Find cross-references and connections between texts
- **search_in_book** - Search within a specific book or text work
- **search_in_dictionaries** - Search Jewish reference dictionaries

**Support Tools:**
- **get_english_translations** - Retrieve all available English translations for a text
- **get_topic_details** - Retrieve detailed information about topics in Jewish thought
- **clarify_name_argument** - Autocomplete and validate text names, book titles, and topics
- **clarify_search_path_filter** - Convert book names to proper search filter paths

**Structure Tools:**
- **get_text_or_category_shape** - Explore the hierarchical structure of texts and categories
- **get_text_catalogue_info** - Get bibliographic and structural information (index) for a work

**Manuscript Tools:**
- **get_available_manuscripts** - Access historical manuscript metadata and image URLs
- **get_manuscript_image** - Download and process specific manuscript images

All endpoints are optimized for LLM consumption (compact, relevant, and structured responses).

## What is MCP?

MCP (Model Context Protocol) is an open protocol for connecting Large Language Models (LLMs) to external tools, APIs, and knowledge sources. It enables LLMs to retrieve, reference, and interact with structured data and external services in a standardized way. Learn more in the [MCP documentation](https://modelcontextprotocol.io/).

## How to Run

### Prerequisites
- Python 3.10+
- Docker (optional, for containerized deployment)

### Local Development

1. **Install dependencies:**
    ```bash
    pip install -e .
    ```
2. **Run the server:**
    ```bash
    python -m sefaria_mcp.main
    ```
    The server will be available at `http://127.0.0.1:8088/mcp` by default, with the
    legacy SSE endpoint at `http://127.0.0.1:8088/sse`.
    Set `SEFARIA_MCP_PORT` to override the HTTP port (e.g., `SEFARIA_MCP_PORT=8089 python -m sefaria_mcp.main`).
    Prometheus metrics bind separately on `SEFARIA_MCP_METRICS_PORT` (default `9090`).

### Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `SEFARIA_MCP_HOST` | `0.0.0.0` | Interface the HTTP server binds to |
| `SEFARIA_MCP_PORT` | `8088` | Port serving both `/mcp` and `/sse` |
| `SEFARIA_MCP_METRICS_PORT` | `9090` | Port for the Prometheus metrics server |
| `SEFARIA_MCP_MANUSCRIPT_IMAGE_HOSTS` | `manuscripts.sefaria.org` | Comma-separated hosts `get_manuscript_image` may fetch from (https only) |
| `SEFARIA_MCP_ALLOWED_HOSTS` | `mcp.sefaria.org,devmcp.sefaria.org` | Comma-separated `Host` values accepted on `/mcp` |
| `SEFARIA_MCP_ALLOWED_ORIGINS` | `https://mcp.sefaria.org,https://devmcp.sefaria.org` | Comma-separated browser `Origin` values accepted on `/mcp` |
| `SEFARIA_MCP_HOST_PROTECTION` | `on` | Set to `off` to disable Host/Origin validation |

Loopback hosts (`127.0.0.1`, `localhost`, `::1`) are always accepted, so local
development needs no extra configuration.

### Docker

1. **Build the image:**
    ```bash
    docker build -t sefaria-mcp .
    ```
2. **Run the container:**
    ```bash
    docker run -d --name sefaria-mcp \
        -e SEFARIA_MCP_PORT=8089 \
        -e SEFARIA_MCP_METRICS_PORT=9090 \
        -p 8089:8089 \
        -p 9090:9090 \
        sefaria-mcp
    ```
    The server will be available at `http://localhost:8089/mcp` (and `http://localhost:8089/sse`), with metrics at `http://localhost:9090/` (adjust the port mappings as needed).

### Transports

The server speaks two MCP transports on the same port. Both expose the identical
set of tools.

| Path | Transport | Status |
|------|-----------|--------|
| `/mcp` | Streamable HTTP | **Primary.** Use this for new clients. |
| `/sse` | HTTP+SSE | Legacy. Kept for backward compatibility; prefer `/mcp`. |

Point your MCP-compatible client at `https://mcp.sefaria.org/mcp`. Clients that
only speak the older SSE transport can continue to use `https://mcp.sefaria.org/sse`,
but new integrations should not depend on it.

`/mcp` runs in stateless mode: every request carries its own transport, so no
session state is held between calls. It therefore accepts `POST` and `DELETE`
only, and returns `405` for `GET` (there is no server-initiated notification
stream to open). Requests to `/mcp` are checked against `SEFARIA_MCP_ALLOWED_HOSTS`
and `SEFARIA_MCP_ALLOWED_ORIGINS`, as the Streamable HTTP spec requires for
DNS-rebinding protection; a mismatched `Host` gets `421` and a mismatched
`Origin` gets `403`. The legacy `/sse` endpoint is not host-checked.

### Monitoring
- Prometheus metrics are exposed via the standalone HTTP server started on `SEFARIA_MCP_METRICS_PORT` (defaults to `9090`).
- Scrape `http://localhost:9090/` (or your configured host/port). Metrics include:
  - `mcp_tool_calls_total{tool_name,status}` – call counts per tool and status.
  - `mcp_tool_duration_seconds{tool_name}` – histogram of per-call durations.
  - `mcp_tool_payload_bytes{tool_name}` – histogram of response payload sizes.
  - `mcp_errors_total{tool_name,error_type}` – per-tool error counts.
  - `mcp_active_connections` – current SSE connection gauge (legacy `/sse` transport only).
  - Standard FastAPI instrumentation (request rate, latency, status codes, in-progress requests, etc.) from `prometheus_fastapi_instrumentator`.

## Commit Hygiene

This repo uses semantic commits with the `fix`, `feat`, and `chore` keywords.
## Acknowledgments

Special thanks to [@Sivan22](https://github.com/Sivan22) for pioneering the first Sefaria MCP server ([mcp-sefaria-server](https://github.com/Sivan22/mcp-sefaria-server)), which inspired this project and the broader effort to make Jewish texts accessible to LLMs and modern AI tools.

## License
MIT
