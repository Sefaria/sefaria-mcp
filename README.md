# Sefaria MCP Server

A modern [MCP (Model Context Protocol)](https://github.com/ai21labs/model-context-protocol) server for accessing the Jewish library via the Sefaria API.

## What does this server do?

This server exposes the Sefaria Jewish library as a set of MCP tools, allowing LLMs and other MCP clients to:

- Retrieve Jewish texts by reference (e.g., "Genesis 1:1")
- Retrieve all available English translations for a text
- Get bibliographic and structural information (index) for a work
- Find cross-references and connections (links)
- Autocomplete and validate text names, book titles, and topics
- Explore the hierarchical structure of texts and categories
- Retrieve detailed information about topics in Jewish thought
- Access historical manuscript metadata and images
- Search the Sefaria library and dictionaries
- Get situational Jewish calendar information

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
    The server will be available at `http://127.0.0.1:8088/sse` by default.

### Docker

1. **Build the image:**
    ```bash
    docker build -t sefaria-mcp .
    ```
2. **Run the container:**
    ```bash
    docker run -d --name sefaria-mcp -p 8089:8088 sefaria-mcp
    ```
    The server will be available at `http://localhost:8089/sse`.

### Usage
- Connect your MCP-compatible client to the `/sse` endpoint.
- All tool endpoints are available via the MCP protocol.

## Acknowledgments

Special thanks to [@Sivan22](https://github.com/Sivan22) for pioneering the first Sefaria MCP server ([mcp-sefaria-server](https://github.com/Sivan22/mcp-sefaria-server)), which inspired this project and the broader effort to make Jewish texts accessible to LLMs and modern AI tools.

## License
MIT
