# backend/api/live.py
"""
Canlı yarış verisi endpoint'leri.

GET /live/positions   → Tüm pilotların X,Y + sıra + lastik bilgisi
GET /live/timing      → Lap times, gap'ler, sektörler
GET /live/session     → Yarış durumu (tur, flag, SC)
"""

from fastapi import APIRouter, HTTPException
from backend.data.fastf1_loader import loader

router = APIRouter(prefix="/live", tags=["Live Data"])


@router.get("/positions")
def get_positions():
    """
    Her pilot için normalize pist koordinatları (0–1000 arası SVG koordinat alanı),
    lastik bilgisi ve anlık sıra döner.
    """
    try:
        return {"status": "ok", "data": loader.get_positions()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/timing")
def get_timing():
    """
    Tur zamanları, gap'ler ve sektör süreleri.
    """
    try:
        return {"status": "ok", "data": loader.get_timing()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/session")
def get_session():
    """
    Yarış meta bilgisi: GP adı, mevcut tur, toplam tur, flag durumu.
    """
    try:
        return {"status": "ok", "data": loader.get_session_status()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
