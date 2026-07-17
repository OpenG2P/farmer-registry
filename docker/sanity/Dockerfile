FROM python:3.12-slim-bookworm

RUN pip install --no-cache-dir \
    "pytest>=8" "httpx>=0.27" "cryptography>=42" "pyjwt>=2.8" "orjson>=3.9" \
    "psycopg2-binary>=2.9"

WORKDIR /app
# Build context = repo root.
COPY test/sanity/ /app/
COPY docker/sanity/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["/app/entrypoint.sh"]
