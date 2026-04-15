# backend/api/predictions.py
"""
Tahmin endpoint'leri.

GET /predict/tire/{driver_number}  → Tek pilot lastik tahmini
GET /predict/tires/all             → Tüm grid lastik tahminleri
GET /predict/pit-window            → Tüm grid pit penceresi
GET /predict/safety-car            → SC olasılığı
GET /standings/projected           → Tahmini şampiyona sırası + delta
"""

from fastapi import APIRouter, HTTPException, Query
from backend.data.fastf1_loader import loader
from backend.models.pit_predictor import pit_predictor
from backend.models.safety_car import sc_predictor
from backend.models.projected_standings import calculate_projected_standings, get_standings_summary

router = APIRouter(tags=["Predictions"])


# ------------------------------------------------------------------
# Lastik & Pit
# ------------------------------------------------------------------
@router.get("/predict/tire/{driver_number}")
def predict_tire(driver_number: str):
    """Tek pilot için lastik aşınması ve pit tavsiyesi."""
    try:
        positions = loader.get_positions()
        driver_data = next((d for d in positions if d["driver_number"] == driver_number), None)
        if driver_data is None:
            raise HTTPException(status_code=404, detail=f"Sürücü bulunamadı: {driver_number}")

        result = pit_predictor.predict(
            driver_number=driver_number,
            tire_compound=driver_data.get("tire", "MEDIUM"),
            tire_age=driver_data.get("tire_age", 1),
            lap_number=driver_data.get("lap", 1),
        )
        return {"status": "ok", "data": result}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/predict/tires/all")
def predict_all_tires():
    """Tüm grid için lastik tahminleri."""
    try:
        positions = loader.get_positions()
        results = pit_predictor.predict_all(positions)
        return {"status": "ok", "data": results}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/predict/pit-window")
def predict_pit_window():
    """
    Pit penceresi tavsiyesi: her sürücü için önerilen tur aralığı.
    Ayrıca 'urgent' (acil) bayrağını içerir.
    """
    try:
        positions = loader.get_positions()
        raw = pit_predictor.predict_all(positions)

        # Abbr bilgisini ekle (harita ile eşleşmesi için)
        pos_map = {d["driver_number"]: d for d in positions}
        for item in raw:
            drv = item["driver_number"]
            if drv in pos_map:
                item["abbr"] = pos_map[drv].get("abbr", drv)
                item["color"] = pos_map[drv].get("color", "#FFFFFF")
                item["team"] = pos_map[drv].get("team", "")
            item["urgent"] = item["pit_probability"] >= 70

        return {"status": "ok", "data": raw}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ------------------------------------------------------------------
# Safety Car
# ------------------------------------------------------------------
@router.get("/predict/safety-car")
def predict_safety_car(
    incident_count: int = Query(default=0, ge=0),
    rainfall: float = Query(default=0.0, ge=0.0, le=1.0),
):
    """
    SC olasılığı. incident_count ve rainfall parametrelerini query string'den alır.
    """
    try:
        session = loader.get_session_status()

        # Ortalama lastik aşınması hesapla
        positions = loader.get_positions()
        tire_preds = pit_predictor.predict_all(positions)
        avg_wear = sum(p["tire_wear_pct"] for p in tire_preds) / max(len(tire_preds), 1)

        result = sc_predictor.predict(
            lap_number=session.get("current_lap", 1),
            total_laps=session.get("total_laps", 57),
            rainfall=rainfall,
            incident_count=incident_count,
            tire_wear_avg=avg_wear,
        )
        return {"status": "ok", "data": result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ------------------------------------------------------------------
# Projected Standings
# ------------------------------------------------------------------
@router.get("/standings/projected")
def get_projected_standings(
    fastest_lap_driver: str = Query(default="", description="En hızlı tur pilotu kısa adı (örn: VER)")
):
    """
    Anlık yarış sıralamasına göre tahmini şampiyona puan durumu ve delta.
    """
    try:
        positions = loader.get_positions()
        projected = calculate_projected_standings(
            current_race_positions=positions,
            fastest_lap_driver=fastest_lap_driver or None,
        )
        summary = get_standings_summary(projected)
        return {
            "status": "ok",
            "summary": summary,
            "data": projected,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/standings/current")
def get_current_standings():
    """2024 şampiyona puan tablosunu döner."""
    from backend.data.fastf1_loader import CHAMPIONSHIP_POINTS_2024, DRIVER_INFO
    try:
        standings = []
        for abbr, pts in CHAMPIONSHIP_POINTS_2024.items():
            # Sürücü numarasını abbr'den bul
            drv_num = next(
                (num for num, info in DRIVER_INFO.items() if info["abbr"] == abbr),
                "0"
            )
            standings.append({
                "abbr": abbr,
                "driver_number": drv_num,
                "team": DRIVER_INFO.get(drv_num, {}).get("team", ""),
                "points": pts,
            })
        standings.sort(key=lambda x: x["points"], reverse=True)
        for rank, item in enumerate(standings, start=1):
            item["position"] = rank
        return {"status": "ok", "data": standings}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
