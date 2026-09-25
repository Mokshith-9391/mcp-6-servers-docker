# =============================================================
#  ec2 MCP server — AWS EC2 via boto3 (IAM role)
#  Build:  docker build -t mcp-ec2 mcp-servers/ec2
#  Run:    docker run --rm -p 127.0.0.1:8003:8003 --env-file .env mcp-ec2
# =============================================================
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MCP_HOST=0.0.0.0

WORKDIR /app

# Dependencies first -> cached layer
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY server.py .

# Non-root user
RUN useradd --create-home --uid 1000 appuser
USER appuser

EXPOSE 8003

# Healthy = the port accepts connections
HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=5 \
  CMD python -c "import socket; socket.create_connection(('127.0.0.1', 8003), 2)"

CMD ["python", "server.py"]
