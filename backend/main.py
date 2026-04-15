# backend/main.py
"""
F1 Strateji Duvarı — FastAPI Ana Uygulama
Başlatma: uvicorn backend.main:app --reload --port 8000
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.live import router as live_router
from backend.api.predictions import router as pred_router
from backend.data.fastf1_loader import loader

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Uygulama başlarken FastF1 session'ı yüklemeyi dene."""
    logger.info("FastF1 session yükleniyor...")
    loaded = loader.load_session()
    if loaded:
        logger.info("Gerçek FastF1 verisi aktif.")
    else:
        logger.warning("Simülasyon modu aktif — gerçek FastF1 verisi yok.")
    yield
    logger.info("Uygulama kapanıyor.")


app = FastAPI(
    title="F1 Strategy Wall API",
    description="Canlı F1 yarış telemetrisi, tahminler ve şampiyona projeksiyonu.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — Streamlit'in 8501 portuna izin ver
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://127.0.0.1:8501"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Router'ları bağla
app.include_router(live_router)
app.include_router(pred_router)


@app.get("/", tags=["Health"])
def root():
    return {
        "service": "F1 Strategy Wall API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health", tags=["Health"])
def health():
    session = loader.get_session_status()
    return {
        "status": "healthy",
        "simulated": session.get("simulated", True),
        "gp": session.get("gp"),
        "current_lap": session.get("current_lap"),
    }
