"""CereMind FastAPI app: serves the API and the built React frontend."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import routes_actions, routes_incident, routes_speed
from app.config import get_settings

app = FastAPI(title="CereMind", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_incident.router)
app.include_router(routes_actions.router)
app.include_router(routes_speed.router)


@app.get("/api/health")
async def health():
    s = get_settings()
    return JSONResponse({
        "status": "ok",
        "cerebras": {"model": s.cerebras_model, "simulated": not s.has_cerebras},
        "pipeline_backend": s.pipeline_backend,
    })


@app.get("/api/config")
async def config():
    s = get_settings()
    from app.rag.embeddings import get_embedder
    from app.rag.ingest import get_vector_store

    return {
        "cerebras_model": s.cerebras_model,
        "cerebras_simulated": not s.has_cerebras,
        "baseline_label": s.baseline_label,
        "baseline_simulated": not s.has_baseline,
        "embedding_backend": get_embedder().backend,
        "vector_backend": get_vector_store().backend,
        "pipeline_backend": s.pipeline_backend,
    }


# --- Static frontend (built React app), if present -------------------------
_STATIC_DIR = Path(__file__).resolve().parent / "static"
if _STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=_STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def spa(full_path: str):
        # Serve the SPA index for any non-API route.
        candidate = _STATIC_DIR / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_STATIC_DIR / "index.html")
