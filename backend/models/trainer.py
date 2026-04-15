# backend/models/trainer.py
"""
Offline model eğitim scripti.
FastF1'den 2023-2024 yarış verileri çekilerek XGBoost (pit/tire) ve
RandomForest (safety car) modelleri eğitilir ve joblib ile kaydedilir.

Kullanım:
    python backend/models/trainer.py
"""

import logging
import numpy as np
import pandas as pd
import joblib
from pathlib import Path

import fastf1
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report
from xgboost import XGBRegressor, XGBClassifier

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

CACHE_DIR = Path(__file__).resolve().parents[2] / "cache"
MODEL_DIR = Path(__file__).resolve().parent
CACHE_DIR.mkdir(parents=True, exist_ok=True)
fastf1.Cache.enable_cache(str(CACHE_DIR))

# Eğitim için kullanılacak yarışlar
TRAINING_RACES = [
    (2023, "Bahrain"),
    (2023, "Saudi Arabia"),
    (2023, "Australia"),
    (2023, "Monaco"),
    (2023, "Spain"),
    (2023, "Canada"),
    (2023, "Abu Dhabi"),
    (2024, "Bahrain"),
    (2024, "Saudi Arabia"),
    (2024, "Australia"),
    (2024, "Monaco"),
]


def collect_lap_data() -> pd.DataFrame:
    """Tüm eğitim yarışlarından tur verisini toplar."""
    frames = []
    for year, gp in TRAINING_RACES:
        try:
            session = fastf1.get_session(year, gp, "R")
            session.load(telemetry=False, laps=True, weather=True)
            laps = session.laps.copy()
            weather = session.weather_data

            # Ortalama hava sıcaklığı ekle
            if weather is not None and not weather.empty:
                avg_air = weather["AirTemp"].mean()
                avg_track = weather["TrackTemp"].mean()
                avg_rain = weather["Rainfall"].mean()
            else:
                avg_air, avg_track, avg_rain = 25.0, 38.0, 0.0

            laps["AirTemp"] = avg_air
            laps["TrackTemp"] = avg_track
            laps["Rainfall"] = avg_rain
            laps["Year"] = year
            laps["GP"] = gp
            frames.append(laps)
            logger.info("Yüklendi: %s %s — %d tur", year, gp, len(laps))
        except Exception as exc:
            logger.warning("Atlandı: %s %s — %s", year, gp, exc)

    if not frames:
        logger.warning("Gerçek veri yok — sentetik veri üretiliyor")
        return _generate_synthetic_data()

    return pd.concat(frames, ignore_index=True)


def _generate_synthetic_data(n: int = 8000) -> pd.DataFrame:
    """
    FastF1 erişimi yoksa sentetik eğitim verisi.
    Gerçek veriyle aynı feature sütunlarını üretir.
    """
    rng = np.random.default_rng(42)
    compounds = rng.choice(["SOFT", "MEDIUM", "HARD"], size=n, p=[0.4, 0.4, 0.2])
    tyre_life = rng.integers(1, 45, size=n)
    lap_number = rng.integers(1, 58, size=n)
    total_laps = 57

    tyre_wear_pct = np.clip(
        (tyre_life / np.where(compounds == "SOFT", 25, np.where(compounds == "MEDIUM", 35, 45))) * 100,
        0, 100,
    )

    pit_stop = (
        (tyre_wear_pct > 75)
        | ((compounds == "SOFT") & (tyre_life > 20))
        | ((compounds == "MEDIUM") & (tyre_life > 30))
    ).astype(int)

    sc_prob = rng.integers(0, 2, size=n)

    return pd.DataFrame({
        "TyreLife": tyre_life,
        "LapNumber": lap_number,
        "TotalLaps": total_laps,
        "Compound_SOFT": (compounds == "SOFT").astype(int),
        "Compound_MEDIUM": (compounds == "MEDIUM").astype(int),
        "Compound_HARD": (compounds == "HARD").astype(int),
        "AirTemp": rng.uniform(20, 40, size=n),
        "TrackTemp": rng.uniform(30, 55, size=n),
        "Rainfall": rng.choice([0, 1], size=n, p=[0.9, 0.1]),
        "TyreWearPct": tyre_wear_pct,
        "PitStop": pit_stop,
        "SafetyCar": sc_prob,
    })


def _prepare_features(df: pd.DataFrame) -> pd.DataFrame:
    """Ham tur verisinden model feature'larını çıkar."""
    # Compound one-hot encode
    for c in ["SOFT", "MEDIUM", "HARD"]:
        df[f"Compound_{c}"] = (df.get("Compound", "") == c).astype(int)

    df["TyreLife"] = pd.to_numeric(df.get("TyreLife", 0), errors="coerce").fillna(0)
    df["LapNumber"] = pd.to_numeric(df.get("LapNumber", 0), errors="coerce").fillna(0)
    df["TotalLaps"] = 57
    df["AirTemp"] = pd.to_numeric(df.get("AirTemp", 25), errors="coerce").fillna(25)
    df["TrackTemp"] = pd.to_numeric(df.get("TrackTemp", 38), errors="coerce").fillna(38)
    df["Rainfall"] = pd.to_numeric(df.get("Rainfall", 0), errors="coerce").fillna(0)

    # Hedef: lastik aşınma yüzdesi (regresyon)
    max_life = np.where(
        df["Compound_SOFT"] == 1, 25,
        np.where(df["Compound_MEDIUM"] == 1, 35, 45),
    )
    df["TyreWearPct"] = np.clip((df["TyreLife"] / max_life) * 100, 0, 100)

    # Hedef: pit stop mu? (sınıflandırma)
    df["PitStop"] = (df["TyreWearPct"] > 75).astype(int)

    # Safety car: basit kural — daha sonra model ile genişletilebilir
    df["SafetyCar"] = 0

    return df


FEATURE_COLS = [
    "TyreLife", "LapNumber", "TotalLaps",
    "Compound_SOFT", "Compound_MEDIUM", "Compound_HARD",
    "AirTemp", "TrackTemp", "Rainfall",
]


def train_tire_wear_model(df: pd.DataFrame) -> XGBRegressor:
    X = df[FEATURE_COLS]
    y = df["TyreWearPct"]
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    model = XGBRegressor(n_estimators=200, max_depth=6, learning_rate=0.05, random_state=42)
    model.fit(X_train, y_train)
    score = model.score(X_test, y_test)
    logger.info("Tire Wear modeli R² = %.4f", score)
    return model


def train_pit_model(df: pd.DataFrame) -> XGBClassifier:
    X = df[FEATURE_COLS]
    y = df["PitStop"]
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    model = XGBClassifier(n_estimators=200, max_depth=5, learning_rate=0.05,
                          use_label_encoder=False, eval_metric="logloss", random_state=42)
    model.fit(X_train, y_train)
    preds = model.predict(X_test)
    logger.info("Pit Stop modeli:\n%s", classification_report(y_test, preds))
    return model


def train_safety_car_model(df: pd.DataFrame) -> RandomForestClassifier:
    X = df[FEATURE_COLS]
    y = df["SafetyCar"]
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    model = RandomForestClassifier(n_estimators=150, max_depth=8, random_state=42)
    model.fit(X_train, y_train)
    preds = model.predict(X_test)
    logger.info("Safety Car modeli:\n%s", classification_report(y_test, preds))
    return model


def main():
    logger.info("Veri toplanıyor...")
    raw = collect_lap_data()

    if "TyreWearPct" not in raw.columns:
        df = _prepare_features(raw)
    else:
        df = raw

    df = df.dropna(subset=FEATURE_COLS)
    logger.info("Toplam örnek: %d", len(df))

    logger.info("Tire Wear modeli eğitiliyor...")
    tire_model = train_tire_wear_model(df)
    joblib.dump(tire_model, MODEL_DIR / "tire_wear_model.joblib")

    logger.info("Pit Stop modeli eğitiliyor...")
    pit_model = train_pit_model(df)
    joblib.dump(pit_model, MODEL_DIR / "pit_model.joblib")

    logger.info("Safety Car modeli eğitiliyor...")
    sc_model = train_safety_car_model(df)
    joblib.dump(sc_model, MODEL_DIR / "safety_car_model.joblib")

    logger.info("Tüm modeller kaydedildi: %s", MODEL_DIR)


if __name__ == "__main__":
    main()
