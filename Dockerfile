# Use Python 3.11 slim image as base
FROM python:3.11-slim

WORKDIR /app

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
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app
USER app

EXPOSE 8088

CMD ["python", "-m", "sefaria_mcp.main"] 