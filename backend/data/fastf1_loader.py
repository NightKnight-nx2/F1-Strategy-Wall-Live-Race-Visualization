# backend/data/fastf1_loader.py
"""
FastF1 session yükleme, cache yönetimi ve simülasyon fallback.
Gerçek veri yoksa ya da API zaman aşımına uğrarsa simüle edilmiş veri döner.
"""

import os
import time
import logging
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Optional

import fastf1
from fastf1.core import Session

logger = logging.getLogger(__name__)

# Cache dizini proje kökünden itibaren
CACHE_DIR = Path(__file__).resolve().parents[2] / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
fastf1.Cache.enable_cache(str(CACHE_DIR))

# 2024 grid — sürücü numarası → (kısa ad, takım, renk)
DRIVER_INFO: dict[str, dict] = {
    "1":  {"abbr": "VER", "team": "Red Bull Racing",    "color": "#3671C6"},
    "11": {"abbr": "PER", "team": "Red Bull Racing",    "color": "#3671C6"},
    "16": {"abbr": "LEC", "team": "Ferrari",            "color": "#E8002D"},
    "55": {"abbr": "SAI", "team": "Ferrari",            "color": "#E8002D"},
    "44": {"abbr": "HAM", "team": "Mercedes",           "color": "#27F4D2"},
    "63": {"abbr": "RUS", "team": "Mercedes",           "color": "#27F4D2"},
    "4":  {"abbr": "NOR", "team": "McLaren",            "color": "#FF8000"},
    "81": {"abbr": "PIA", "team": "McLaren",            "color": "#FF8000"},
    "14": {"abbr": "ALO", "team": "Aston Martin",       "color": "#229971"},
    "18": {"abbr": "STR", "team": "Aston Martin",       "color": "#229971"},
    "10": {"abbr": "GAS", "team": "Alpine",             "color": "#0093CC"},
    "31": {"abbr": "OCO", "team": "Alpine",             "color": "#0093CC"},
    "23": {"abbr": "ALB", "team": "Williams",           "color": "#64C4FF"},
    "2":  {"abbr": "SAR", "team": "Williams",           "color": "#64C4FF"},
    "24": {"abbr": "ZHO", "team": "Kick Sauber",        "color": "#52E252"},
    "77": {"abbr": "BOT", "team": "Kick Sauber",        "color": "#52E252"},
    "20": {"abbr": "MAG", "team": "Haas",               "color": "#B6BABD"},
    "27": {"abbr": "HUL", "team": "Haas",               "color": "#B6BABD"},
    "22": {"abbr": "TSU", "team": "RB",                 "color": "#6692FF"},
    "3":  {"abbr": "RIC", "team": "RB",                 "color": "#6692FF"},
}

# 2024 şampiyona puan durumu (Abu Dhabi öncesi tahmini sıralama)
CHAMPIONSHIP_POINTS_2024: dict[str, int] = {
    "VER": 393, "NOR": 331, "LEC": 307, "PIA": 268,
    "SAI": 259, "RUS": 235, "HAM": 211, "TSU": 92,
    "ALO": 70,  "HUL": 37,  "STR": 24,  "GAS": 26,
    "RIC": 12,  "ALB": 12,  "MAG": 16,  "OCO": 23,
    "BOT": 5,   "ZHO": 6,   "COL": 5,   "BEA": 7,
}


class F1DataLoader:
    """
    FastF1 üzerinden gerçek veri çeker.
    Hata durumunda veya simülasyon modunda sentetik veri üretir.
    """

    def __init__(self, year: int = 2024, gp: str = "Abu Dhabi", session_type: str = "R"):
        self.year = year
        self.gp = gp
        self.session_type = session_type
        self._session: Optional[Session] = None
        self._sim_lap = 1  # simülasyon için mevcut tur sayacı

    # ------------------------------------------------------------------
    # Oturum Yükleme
    # ------------------------------------------------------------------
    def load_session(self) -> bool:
        """Gerçek FastF1 session'ı yükle. Başarısızsa False döner."""
        try:
            self._session = fastf1.get_session(self.year, self.gp, self.session_type)
            self._session.load(telemetry=True, laps=True, weather=True)
            logger.info("FastF1 session yüklendi: %s %s %s", self.year, self.gp, self.session_type)
            return True
        except Exception as exc:
            logger.warning("FastF1 session yüklenemedi: %s — simülasyon modu aktif", exc)
            return False

    # ------------------------------------------------------------------
    # Canlı Pozisyonlar
    # ------------------------------------------------------------------
    def get_positions(self) -> list[dict]:
        """
        Tüm pilotların anlık pist üzerindeki normalize edilmiş X,Y
        koordinatlarını ve sıra bilgisini döner.
        Gerçek veri yoksa simüle eder.
        """
        if self._session is not None:
            return self._get_real_positions()
        return self._simulate_positions()

    def _get_real_positions(self) -> list[dict]:
        try:
            lap_data = self._session.laps
            latest = lap_data.groupby("DriverNumber").last().reset_index()
            results = []
            for _, row in latest.iterrows():
                drv = str(int(row["DriverNumber"]))
                info = DRIVER_INFO.get(drv, {"abbr": drv, "color": "#FFFFFF"})
                results.append({
                    "driver_number": drv,
                    "abbr": info["abbr"],
                    "color": info["color"],
                    "team": info.get("team", ""),
                    "position": int(row.get("Position", 0) or 0),
                    # Telemetri koordinatları mevcut değilse 0
                    "x": float(row.get("X", 0) or 0),
                    "y": float(row.get("Y", 0) or 0),
                    "lap": int(row.get("LapNumber", 0) or 0),
                    "tire": str(row.get("Compound", "UNKNOWN")),
                    "tire_age": int(row.get("TyreLife", 0) or 0),
                })
            return results
        except Exception as exc:
            logger.error("Gerçek pozisyon alınamadı: %s", exc)
            return self._simulate_positions()

    def _simulate_positions(self) -> list[dict]:
        """
        Pilotları pist üzerinde sabit bir elips üzerinde hareket ettirir.
        track_map.html ile uyumlu normalize koordinatlar (0–1000 arası).
        """
        drivers = list(DRIVER_INFO.items())
        total = len(drivers)
        positions = []
        t = time.time() * 0.05  # zaman bazlı hareket

        for idx, (number, info) in enumerate(drivers):
            phase = (idx / total) * 2 * np.pi + t
            # Oval pist simülasyonu (cx=500, cy=400, rx=380, ry=220)
            x = 500 + 380 * np.cos(phase)
            y = 400 + 220 * np.sin(phase)
            positions.append({
                "driver_number": number,
                "abbr": info["abbr"],
                "color": info["color"],
                "team": info["team"],
                "position": idx + 1,
                "x": round(x, 2),
                "y": round(y, 2),
                "lap": self._sim_lap,
                "tire": _random_tire(idx),
                "tire_age": (self._sim_lap % 20) + 1,
            })

        self._sim_lap = (self._sim_lap % 57) + 1
        return positions

    # ------------------------------------------------------------------
    # Lap Timing
    # ------------------------------------------------------------------
    def get_timing(self) -> list[dict]:
        """Son tur zamanları ve gap'ler."""
        if self._session is not None:
            return self._get_real_timing()
        return self._simulate_timing()

    def _get_real_timing(self) -> list[dict]:
        try:
            laps = self._session.laps
            latest = laps.groupby("DriverNumber").last().reset_index()
            timing = []
            for _, row in latest.iterrows():
                drv = str(int(row["DriverNumber"]))
                info = DRIVER_INFO.get(drv, {"abbr": drv})
                lap_time = row.get("LapTime")
                timing.append({
                    "driver_number": drv,
                    "abbr": info["abbr"],
                    "position": int(row.get("Position", 0) or 0),
                    "lap_time": str(lap_time) if pd.notna(lap_time) else "--:--.---",
                    "gap": str(row.get("GapToLeader", "")) or "+0.000",
                    "lap": int(row.get("LapNumber", 0) or 0),
                    "sector1": _fmt_sector(row.get("Sector1Time")),
                    "sector2": _fmt_sector(row.get("Sector2Time")),
                    "sector3": _fmt_sector(row.get("Sector3Time")),
                })
            return sorted(timing, key=lambda x: x["position"])
        except Exception as exc:
            logger.error("Gerçek timing alınamadı: %s", exc)
            return self._simulate_timing()

    def _simulate_timing(self) -> list[dict]:
        base_ms = 88000  # ~1:28.000
        result = []
        drivers = list(DRIVER_INFO.items())
        for idx, (number, info) in enumerate(drivers):
            gap_ms = idx * (np.random.uniform(0.2, 1.5) * 1000)
            lap_ms = base_ms + np.random.randint(-500, 500)
            result.append({
                "driver_number": number,
                "abbr": info["abbr"],
                "position": idx + 1,
                "lap_time": _ms_to_laptime(lap_ms),
                "gap": "+0.000" if idx == 0 else f"+{gap_ms/1000:.3f}",
                "lap": self._sim_lap,
                "sector1": _ms_to_laptime(lap_ms * 0.28),
                "sector2": _ms_to_laptime(lap_ms * 0.38),
                "sector3": _ms_to_laptime(lap_ms * 0.34),
            })
        return result

    # ------------------------------------------------------------------
    # Session Durumu
    # ------------------------------------------------------------------
    def get_session_status(self) -> dict:
        total_laps = 57
        if self._session is not None:
            try:
                total_laps = int(self._session.event.get("RaceLaps", 57) or 57)
            except Exception:
                pass
        return {
            "year": self.year,
            "gp": self.gp,
            "session_type": self.session_type,
            "current_lap": self._sim_lap,
            "total_laps": total_laps,
            "safety_car_active": False,  # model tarafından güncellenecek
            "flag": "GREEN",
            "simulated": self._session is None,
        }


# ------------------------------------------------------------------
# Yardımcı Fonksiyonlar
# ------------------------------------------------------------------
_TIRE_CYCLE = ["SOFT", "MEDIUM", "HARD", "MEDIUM", "SOFT"]

def _random_tire(seed: int) -> str:
    return _TIRE_CYCLE[seed % len(_TIRE_CYCLE)]

def _ms_to_laptime(ms: float) -> str:
    ms = int(ms)
    minutes = ms // 60000
    seconds = (ms % 60000) // 1000
    millis = ms % 1000
    return f"{minutes}:{seconds:02d}.{millis:03d}"

def _fmt_sector(val) -> str:
    if val is None or (hasattr(val, "__class__") and "NaT" in str(type(val))):
        return "---.---"
    try:
        total_ms = int(pd.Timedelta(val).total_seconds() * 1000)
        return f"{total_ms / 1000:.3f}"
    except Exception:
        return "---.---"


# ------------------------------------------------------------------
# Singleton instance (API katmanında import edilecek)
# ------------------------------------------------------------------
loader = F1DataLoader(year=2024, gp="Abu Dhabi", session_type="R")
