# Hugging Face Space image (§8): the FastAPI app with the e5 weights baked in, CPU only.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.9 /uv /usr/local/bin/uv
RUN useradd -m -u 1000 user
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy HF_HOME=/app/.hf PATH="/app/.venv/bin:$PATH"

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --group embed --no-install-project

# Bake the embedding model into the image so a cold start doesn't download it.
COPY config.yaml ./
RUN python -c "import yaml; from sentence_transformers import SentenceTransformer; \
SentenceTransformer(yaml.safe_load(open('config.yaml'))['embedding']['model'])"
ENV HF_HUB_OFFLINE=1

COPY backend backend
COPY prompts prompts
COPY corpus/aliases.yaml corpus/aliases.yaml
RUN mkdir -p data && chown -R user /app
USER user

# Secrets come from the Space settings: DATABASE_URL, SUPABASE_URL, LLM_API_KEY, IP_HASH_SALT (+ LANGFUSE_* later).
# Never SUPABASE_SERVICE_KEY: crops are public-read and the Space only builds their URLs.
EXPOSE 7860
CMD ["uvicorn", "backend.api:app", "--host", "0.0.0.0", "--port", "7860"]
