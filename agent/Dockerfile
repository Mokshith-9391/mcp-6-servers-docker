# =============================================================
#  LangChain agent — connects to all 6 MCP servers
#  Usually run through compose:  docker compose run --rm agent
# =============================================================
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY agent.py test_servers.py ./

RUN useradd --create-home --uid 1000 appuser
USER appuser

CMD ["python", "agent.py"]
