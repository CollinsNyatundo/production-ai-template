# Stage 1: Build virtual environment dependencies
FROM python:3.11-slim as builder

WORKDIR /build

RUN pip install --no-cache-dir poetry

COPY pyproject.toml poetry.lock* /build/

# Do not install the root package, only dependencies
RUN poetry config virtualenvs.create false \
    && poetry install --no-root --no-interaction --no-ansi --only main \
    && pip install --no-cache-dir python-multipart httpx

# Pre-download tiktoken's BPE encoding files at build time. Without this, the
# first token-count call in a running container fetches them from
# openaipublic.blob.core.windows.net on demand - which fails hard in any
# environment with locked-down egress (common for production containers,
# and tiktoken has no built-in offline fallback for a missing file).
ENV TIKTOKEN_CACHE_DIR=/build/.tiktoken_cache
RUN python -c "import tiktoken; tiktoken.get_encoding('cl100k_base'); tiktoken.get_encoding('o200k_base')"

# Stage 2: Production image
FROM python:3.11-slim as runner

WORKDIR /workspace

# Copy installed dependencies from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /build/.tiktoken_cache /workspace/.tiktoken_cache
ENV TIKTOKEN_CACHE_DIR=/workspace/.tiktoken_cache

COPY app /workspace/app
COPY evaluation /workspace/evaluation
COPY observability /workspace/observability
COPY README.md /workspace/

ENV PORT=8000
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
