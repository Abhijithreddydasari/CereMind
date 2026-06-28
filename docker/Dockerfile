# syntax=docker/dockerfile:1

# ---------- Stage 1: build the React frontend ----------
FROM node:22-slim AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
# Vite's outDir is env-driven; build into a local dir this stage can copy from.
ENV BUILD_OUT_DIR=dist
RUN npm run build

# ---------- Stage 2: python runtime ----------
FROM python:3.11-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080

WORKDIR /app

# System deps for matplotlib font rendering.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libfreetype6 libpng16-16 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

# Optional: bake EmbeddingGemma weights at build time to avoid cold-start
# downloads. Pass --build-arg BAKE_EMBEDDINGS=1 and HF_TOKEN to enable.
ARG BAKE_EMBEDDINGS=0
ARG HF_TOKEN=""
ARG EMBEDDING_GEMMA_MODEL="google/embeddinggemma-300m"
RUN if [ "$BAKE_EMBEDDINGS" = "1" ]; then \
        pip install sentence-transformers torch --extra-index-url https://download.pytorch.org/whl/cpu && \
        python -c "import os; from sentence_transformers import SentenceTransformer; \
SentenceTransformer('${EMBEDDING_GEMMA_MODEL}', token=os.environ.get('HF_TOKEN') or None)"; \
    fi

COPY backend/ ./backend/
COPY --from=frontend /fe/dist ./backend/app/static

# Pre-generate the DAG snapshot so the first request is instant.
RUN cd backend && python -c "from app.pipeline.gen_snapshot import generate_snapshot; \
from app.pipeline.seed import SNAPSHOT_PATH; generate_snapshot(SNAPSHOT_PATH)" || true

WORKDIR /app/backend
EXPOSE 8080
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
