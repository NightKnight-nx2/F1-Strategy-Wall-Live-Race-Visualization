# backend/models/safety_car.py
"""
Safety Car olasılık tahmini.
Yüklü RandomForest modeli yoksa kural tabanlı fallback.
Çıktı: 0–100 arası SC probability + tetikleyici faktörler listesi.
"""

import logging
from pathlib import Path

import numpy as np
import joblib

logger = logging.getLogger(__name__)
MODEL_DIR = Path(__file__).resolve().parent


class SafetyCarPredictor:
    def __init__(self):
        self._model = None
        self._load_model()

    def _load_model(self):
        path = MODEL_DIR / "safety_car_model.joblib"
        if path.exists():
            try:
                self._model = joblib.load(path)
                logger.info("Safety Car modeli yüklendi.")
            except Exception as exc:
                logger.warning("SC modeli yüklenemedi: %s", exc)

    def predict(
        self,
        lap_number: int,
        total_laps: int = 57,
        rainfall: float = 0.0,
        air_temp: float = 25.0,
        track_temp: float = 38.0,
        incident_count: int = 0,          # o yarışta yaşanan olay sayısı
        tire_wear_avg: float = 50.0,      # grid genelinde ortalama aşınma
    ) -> dict:
        """
        Returns:
            {
                sc_probability,      # 0–100
                sc_active,           # bool
                triggers             # tetikleyici faktörler listesi
            }
        """
        features = [[
            lap_number, total_laps, 0, 0, 0,   # tire dummies (neutral)
            air_temp, track_temp, rainfall
        ]]

        if self._model is not None:
            try:
                prob = float(self._model.predict_proba(features)[0][1])
            except Exception as exc:
                logger.warning("SC model predict hatası: %s", exc)
                prob = self._fallback_prob(lap_number, total_laps, rainfall, incident_count)
        else:
            prob = self._fallback_prob(lap_number, total_laps, rainfall, incident_count)

        # Ek faktörlerden prob artışı
        if rainfall > 0.5:
            prob = min(prob + 0.25, 1.0)
        if incident_count > 0:
            prob = min(prob + 0.15 * incident_count, 1.0)
        if tire_wear_avg > 80:
            prob = min(prob + 0.10, 1.0)

        prob_pct = round(prob * 100, 1)
        triggers = self._get_triggers(rainfall, incident_count, tire_wear_avg, lap_number)

        return {
            "sc_probability": prob_pct,
            "sc_active": prob_pct >= 40.0,
            "triggers": triggers,
        }

    @staticmethod
    def _fallback_prob(lap: int, total: int, rainfall: float, incidents: int) -> float:
        """
        Kural tabanlı SC olasılığı.
        - İlk 5 tur ve son 5 tur risk yüksek.
        - Yağmurda belirgin artış.
        """
        base = 0.08
        if lap <= 5 or lap >= (total - 5):
            base += 0.12
        base += rainfall * 0.30
        base += incidents * 0.10
        return min(base, 1.0)

    @staticmethod
    def _get_triggers(rainfall: float, incidents: int,
                      tire_wear_avg: float, lap: int) -> list[str]:
        triggers = []
        if rainfall > 0.5:
            triggers.append("Yağmur / Islak pist")
        if incidents > 0:
            triggers.append(f"{incidents} pist olayı")
        if tire_wear_avg > 80:
            triggers.append("Yüksek ortalama lastik aşınması")
        if lap <= 5:
            triggers.append("Yarışın ilk turları (yüksek risk)")
        return triggers if triggers else ["Nominal koşullar"]


# Singleton
sc_predictor = SafetyCarPredictor()
