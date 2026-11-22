FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/home/icici

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir . "mcpo==0.0.20" "fastapi==0.115.12" \
    && useradd --create-home --uid 10001 icici \
    && mkdir -p /app/logs \
    && chown -R icici:icici /app /home/icici

USER icici
EXPOSE 8000
ENTRYPOINT ["sh", "-c", "if [ -z \"$MCPO_API_KEY\" ]; then echo 'MCPO_API_KEY is required.' >&2; exit 1; fi; exec mcpo --host 0.0.0.0 --port 8000 --strict-auth true --api-key \"$MCPO_API_KEY\" -- icici-mcp"]
