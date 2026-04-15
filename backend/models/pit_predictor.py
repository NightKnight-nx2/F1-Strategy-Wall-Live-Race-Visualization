# backend/models/pit_predictor.py
"""
Yüklü XGBoost modellerini kullanarak:
  - Lastik aşınma yüzdesi (TyreWearPct)
  - Pit stop tavsiyesi (PitRecommended) ve tahmini optimal pencere
döndürür.
Model dosyaları yoksa kural tabanlı fallback devreye girer.
"""

import logging
from pathlib import Path
from typing import Optional

import numpy as np
import joblib

logger = logging.getLogger(__name__)

MODEL_DIR = Path(__file__).resolve().parent
TIRE_MAX_LIFE = {"SOFT": 25, "MEDIUM": 35, "HARD": 45, "UNKNOWN": 30}

# Compound string → one-hot
def _compound_onehot(compound: str) -> tuple[int, int, int]:
    c = compound.upper()
    return int(c == "SOFT"), int(c == "MEDIUM"), int(c == "HARD")


class PitPredictor:
    def __init__(self):
        self._tire_model = None
        self._pit_model = None
        self._load_models()

    def _load_models(self):
        tire_path = MODEL_DIR / "tire_wear_model.joblib"
        pit_path = MODEL_DIR / "pit_model.joblib"

        if tire_path.exists():
            try:
                self._tire_model = joblib.load(tire_path)
                logger.info("Tire Wear modeli yüklendi.")
            except Exception as exc:
                logger.warning("Tire Wear modeli yüklenemedi: %s", exc)

        if pit_path.exists():
            try:
                self._pit_model = joblib.load(pit_path)
                logger.info("Pit Stop modeli yüklendi.")
            except Exception as exc:
                logger.warning("Pit Stop modeli yüklenemedi: %s", exc)

    def predict(
        self,
        driver_number: str,
        tire_compound: str,
        tire_age: int,
        lap_number: int,
        total_laps: int = 57,
        air_temp: float = 25.0,
        track_temp: float = 38.0,
        rainfall: float = 0.0,
    ) -> dict:
        """
        Tek sürücü için lastik aşınması ve pit tavsiyesi döner.

        Returns:
            {
                driver_number, tire_wear_pct, pit_recommended,
                pit_window_start, pit_window_end, laps_remaining_on_tire
            }
        """
        soft, medium, hard = _compound_onehot(tire_compound)
        features = [[
            tire_age, lap_number, total_laps,
            soft, medium, hard,
            air_temp, track_temp, rainfall,
        ]]

        # --- Lastik Aşınma ---
        if self._tire_model is not None:
            try:
                wear_pct = float(self._tire_model.predict(features)[0])
            except Exception as exc:
                logger.warning("Tire model predict hatası: %s", exc)
                wear_pct = self._fallback_wear(tire_compound, tire_age)
        else:
            wear_pct = self._fallback_wear(tire_compound, tire_age)

        wear_pct = float(np.clip(wear_pct, 0, 100))

        # --- Pit Tavsiyesi ---
        if self._pit_model is not None:
            try:
                pit_rec = bool(self._pit_model.predict(features)[0])
                pit_prob = float(self._pit_model.predict_proba(features)[0][1])
            except Exception as exc:
                logger.warning("Pit model predict hatası: %s", exc)
                pit_rec, pit_prob = self._fallback_pit(wear_pct)
        else:
            pit_rec, pit_prob = self._fallback_pit(wear_pct)

        # --- Pit Penceresi ---
        max_life = TIRE_MAX_LIFE.get(tire_compound.upper(), 30)
        laps_left_on_tire = max(0, max_life - tire_age)
        pit_window_start = lap_number + max(1, laps_left_on_tire - 5)
        pit_window_end = lap_number + laps_left_on_tire + 3
        pit_window_start = min(pit_window_start, total_laps)
        pit_window_end = min(pit_window_end, total_laps)

        return {
            "driver_number": driver_number,
            "tire_wear_pct": round(wear_pct, 1),
            "pit_probability": round(pit_prob * 100, 1),
            "pit_recommended": pit_rec,
            "pit_window_start": int(pit_window_start),
            "pit_window_end": int(pit_window_end),
            "laps_remaining_on_tire": int(laps_left_on_tire),
        }

    def predict_all(self, driver_states: list[dict]) -> list[dict]:
        """
        Tüm sürücüler için toplu tahmin.
        driver_states: get_positions() çıktısıyla uyumlu liste.
        """
        results = []
        for d in driver_states:
            result = self.predict(
                driver_number=d.get("driver_number", "0"),
                tire_compound=d.get("tire", "MEDIUM"),
                tire_age=d.get("tire_age", 1),
                lap_number=d.get("lap", 1),
            )
            results.append(result)
        return results

    @staticmethod
    def _fallback_wear(compound: str, tire_age: int) -> float:
        max_life = TIRE_MAX_LIFE.get(compound.upper(), 30)
        return min((tire_age / max_life) * 100, 100)

    @staticmethod
    def _fallback_pit(wear_pct: float) -> tuple[bool, float]:
        prob = wear_pct / 100
        return prob > 0.75, prob


# Singleton
pit_predictor = PitPredictor()
