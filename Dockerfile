# Use Python 3.11 slim image as base
FROM python:3.11-slim

WORKDIR /app

ENV SEFARIA_MCP_PORT=8088
ENV SEFARIA_MCP_METRICS_PORT=9090

RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy project configuration files
COPY pyproject.toml ./
COPY LICENSE ./
COPY README.md ./
COPY src/ ./src/
RUN pip install --no-cache-dir -e .

# Create a non-root user for security
RUN useradd --create-home --shell /bin/bash --uid 1001 app \
    && chown -R app:app /app
USER 1001

EXPOSE 8088 9090

CMD ["python", "-m", "sefaria_mcp.main"] 
