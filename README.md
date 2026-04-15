# 🏎️ F1 Strategy Wall

> **Formula 1 Canlı Yarış Tahminleme ve Stratejik Dashboard**  
> Red Bull Racing pit duvarı estetiğiyle tasarlanmış, gerçek telemetri verisi üzerinde çalışan mikroservis tabanlı bir F1 strateji aracı.

---

## ✨ Özellikler

| Özellik | Açıklama |
|---------|----------|
| 🗺️ **İnteraktif Pist Haritası** | D3.js + SVG ile pilotların gerçek zamanlı hareketi |
| 🔍 **Hover Tooltip** | Pilot fotoğrafı, lastik türü/yaşı, anlık sıra, projected standings delta |
| 🔧 **Lastik Tahminleri** | XGBoost ile aşınma yüzdesi ve optimal pit penceresi |
| ⚠️ **Safety Car Riski** | RandomForest ile 0–100 arası SC olasılığı |
| 🏆 **Projected Standings** | Anlık sıraya göre yarış sonu şampiyona puan tahmini (25–18–15… algoritması) |
| 🔄 **Canlı Polling** | Her 5 saniyede bir FastAPI'ye non-blocking sorgu |
| 🎨 **Red Bull Teması** | `#0600EF` / `#FF0000` / `#FFCC00` renk paleti, koyu pit duvarı UI |
| 🔌 **Simülasyon Modu** | FastF1 erişimi yoksa 20 pilotla otomatik simüle edilmiş veri |

---

## 🏗️ Mimari

```
┌─────────────────────────────────────────────────────┐
│                   FRONTEND (Streamlit)               │
│   app.py  ←──── polling (5s) ────→  FastAPI :8000   │
│   D3.js Track Map                                    │
│   Red Bull CSS Theme                                 │
└─────────────────────────────────────────────────────┘
                          │
┌─────────────────────────────────────────────────────┐
│                   BACKEND (FastAPI)                  │
│  /live/*        → FastF1 veri hattı                  │
│  /predict/*     → XGBoost + RandomForest modelleri   │
│  /standings/*   → Projected Standings algoritması    │
└─────────────────────────────────────────────────────┘
                          │
┌─────────────────────────────────────────────────────┐
│                   VERİ KAYNAĞI                       │
│  FastF1  →  Gerçek telemetri (internet gerekir)      │
│  Simülatör  →  Sentetik 20-sürücü verisi (offline)   │
└─────────────────────────────────────────────────────┘
```

---

## 🛠️ Tech Stack

**Backend**
- [FastAPI](https://fastapi.tiangolo.com/) — REST API sunucusu
- [FastF1](https://docs.fastf1.dev/) — F1 telemetri verisi
- [XGBoost](https://xgboost.readthedocs.io/) — Lastik aşınma & pit stop tahmini
- [scikit-learn](https://scikit-learn.org/) — Safety car olasılık modeli
- [Pandas](https://pandas.pydata.org/) + [NumPy](https://numpy.org/) — Veri işleme

**Frontend**
- [Streamlit](https://streamlit.io/) — Ana uygulama iskeleti
- [D3.js v7](https://d3js.org/) — İnteraktif pist haritası (SVG animasyonu)
- Custom CSS — Red Bull Racing pit duvarı teması

---

## 📁 Proje Yapısı

```
f1-strategy-wall/
├── backend/
│   ├── main.py                      # FastAPI uygulaması, router mount
│   ├── data/
│   │   └── fastf1_loader.py         # FastF1 session + simülasyon fallback
│   ├── models/
│   │   ├── trainer.py               # Offline model eğitim scripti
│   │   ├── pit_predictor.py         # XGBoost: tire wear + pit window
│   │   ├── safety_car.py            # RandomForest: SC probability
│   │   └── projected_standings.py   # 25-18-15 puan algoritması + delta
│   └── api/
│       ├── live.py                  # /live/* endpoint'leri
│       └── predictions.py           # /predict/* + /standings/* endpoint'leri
├── frontend/
│   ├── app.py                       # Ana Streamlit uygulaması
│   ├── components/
│   │   ├── track_map.html           # D3.js harita + hover tooltip
│   │   └── asset_resolver.py        # CDN URL → local fallback zinciri
│   └── styles/
│       └── theme.css                # Red Bull CSS tema
├── assets/
│   ├── drivers/                     # Pilot headshot fallback görselleri
│   ├── teams/                       # Takım logosu fallback görselleri
│   └── tracks/                      # Pist SVG fallback dosyaları
├── .gitignore
├── requirements.txt
├── start_backend.bat                # Backend başlatma scripti
├── start_frontend.bat               # Frontend başlatma scripti
└── train_models.bat                 # Model eğitim scripti
```

---

## 🚀 Kurulum

### Gereksinimler
- Python **3.11+**
- Windows (`.bat` scriptleri) veya herhangi bir işletim sistemi (manuel komutlar)

### 1. Repoyu Klonla
```bash
git clone https://github.com/NightKnight-nx2/f1-strategy-wall.git
cd f1-strategy-wall
```

### 2. Sanal Ortam Oluştur
```bash
python -m venv .venv
```

### 3. Bağımlılıkları Kur
```bash
# Windows
.venv\Scripts\pip install -r requirements.txt

# macOS / Linux
.venv/bin/pip install -r requirements.txt
```

### 4. ML Modellerini Eğit *(opsiyonel — internet gerektirir)*
```bash
# Windows
.\train_models.bat

# macOS / Linux
.venv/bin/python -m backend.models.trainer
```
> Model dosyaları yoksa uygulama **kural tabanlı fallback** ile çalışır, hata vermez.

---

## ▶️ Çalıştırma

İki ayrı terminal aç:

**Terminal 1 — Backend**
```bash
# Windows
.\start_backend.bat

# macOS / Linux
.venv/bin/uvicorn backend.main:app --reload --port 8000
```

**Terminal 2 — Frontend**
```bash
# Windows
.\start_frontend.bat

# macOS / Linux
.venv/bin/streamlit run frontend/app.py --server.port 8501
```

| Servis | URL |
|--------|-----|
| Dashboard | http://localhost:8501 |
| API | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |

> **Backend olmadan da çalışır.** Frontend, API'ye ulaşamazsa otomatik olarak simülasyon moduna geçer — 20 pilotla animasyonlu demo görünümü sunar.

---

## 📡 API Endpoint'leri

| Method | Endpoint | Açıklama |
|--------|----------|----------|
| `GET` | `/live/positions` | Tüm pilotların X,Y koordinatları + lastik bilgisi |
| `GET` | `/live/timing` | Tur zamanları, gap'ler, sektör süreleri |
| `GET` | `/live/session` | Yarış durumu (tur no, flag, SC aktif mi) |
| `GET` | `/predict/tires/all` | Grid geneli lastik aşınma tahminleri |
| `GET` | `/predict/tire/{driver}` | Tek pilot lastik tahmini |
| `GET` | `/predict/pit-window` | Önerilen pit penceresi (tüm grid) |
| `GET` | `/predict/safety-car` | SC olasılığı + tetikleyici faktörler |
| `GET` | `/standings/projected` | Tahmini şampiyona sırası + live delta |
| `GET` | `/standings/current` | Mevcut şampiyona puan tablosu |

---

## ⚙️ Yapılandırma

### Yarış / Sezon Değiştirme

[backend/data/fastf1_loader.py](backend/data/fastf1_loader.py) — en alttaki `loader` singleton'ını güncelle:
```python
loader = F1DataLoader(year=2024, gp="Abu Dhabi", session_type="R")
```

### Polling Aralığı

[frontend/app.py](frontend/app.py):
```python
POLL_SECS = 5  # saniye
```

---

## 🔧 Geliştirme Notları

- **Model dosyaları** (`.joblib`) `.gitignore`'da — `train_models.bat` ile her ortamda yeniden üretilir.
- **FastF1 cache** (`cache/` klasörü) `.gitignore`'da — ilk çalıştırmada otomatik indirilir.
- **Asset fallback zinciri:** `formula1.com CDN → assets/<klasör>/<dosya>.png → SVG placeholder`
- **Simülasyon modu:** FastF1 erişimi olmadan pist üzerinde 20 sürücü hareket eder, tüm tahminler kural tabanlı fallback ile üretilir.

---

## 📄 Lisans

[MIT License](LICENSE)

---

## 🙏 Kaynaklar

- [FastF1](https://github.com/theOehrly/Fast-F1) — F1 telemetri verisi
- [Formula 1 Media](https://www.formula1.com) — Pilot görselleri (CDN)
- [D3.js](https://d3js.org) — Veri görselleştirme kütüphanesi
- [Ergast API](http://ergast.com/mrd/) — Tarihsel F1 verisi
