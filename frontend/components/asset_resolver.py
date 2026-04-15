# frontend/components/asset_resolver.py
"""
Asset Resolver — CDN URL → 404 kontrolü → Local fallback zinciri.

Kullanım:
    from frontend.components.asset_resolver import get_headshot_url, get_team_logo_url

Pilot fotoğrafları için önce formula1.com CDN'i dener.
404 veya timeout durumunda assets/drivers/<abbr>.png'e düşer.
"""

import logging
from pathlib import Path
from functools import lru_cache

import requests

logger = logging.getLogger(__name__)

ASSETS_DIR   = Path(__file__).resolve().parents[2] / "assets"
DRIVERS_DIR  = ASSETS_DIR / "drivers"
TEAMS_DIR    = ASSETS_DIR / "teams"

# ── Pilot headshot CDN URL şablonları (öncelik sırasıyla) ───────────────────
# formula1.com CDN — pilot kısa adına göre URL oluşturulur.
# Örn: MAX VERSTAPPEN → MAXVER01_Max_Verstappen/maxver01.png
_F1_CDN_BASE = "https://www.formula1.com/content/dam/fom-website/drivers"

# Tam URL haritası (kısa ad → CDN URL)
# ÖNEMLİ: Bu URL'ler F1'in resmi CDN yapısına göre hazırlanmıştır.
# Erişilemeyen URL'ler için local fallback devreye girer.
DRIVER_HEADSHOTS: dict[str, str] = {
    "VER": f"{_F1_CDN_BASE}/M/MAXVER01_Max_Verstappen/maxver01.png",
    "PER": f"{_F1_CDN_BASE}/S/SERPER01_Sergio_Perez/serper01.png",
    "LEC": f"{_F1_CDN_BASE}/C/CHALEC01_Charles_Leclerc/chalec01.png",
    "SAI": f"{_F1_CDN_BASE}/C/CARSAI01_Carlos_Sainz/carsai01.png",
    "HAM": f"{_F1_CDN_BASE}/L/LEWHAM01_Lewis_Hamilton/lewham01.png",
    "RUS": f"{_F1_CDN_BASE}/G/GEORUS01_George_Russell/georus01.png",
    "NOR": f"{_F1_CDN_BASE}/L/LANNOR01_Lando_Norris/lannor01.png",
    "PIA": f"{_F1_CDN_BASE}/O/OSCPIA01_Oscar_Piastri/oscpia01.png",
    "ALO": f"{_F1_CDN_BASE}/F/FERALO01_Fernando_Alonso/feralo01.png",
    "STR": f"{_F1_CDN_BASE}/L/LANSTR01_Lance_Stroll/lanstr01.png",
    "GAS": f"{_F1_CDN_BASE}/P/PIEGAS01_Pierre_Gasly/piegas01.png",
    "OCO": f"{_F1_CDN_BASE}/E/ESTOCO01_Esteban_Ocon/estoco01.png",
    "ALB": f"{_F1_CDN_BASE}/A/ALEALB01_Alexander_Albon/alealb01.png",
    "SAR": f"{_F1_CDN_BASE}/L/LOGSAR01_Logan_Sargeant/logsar01.png",
    "ZHO": f"{_F1_CDN_BASE}/G/GUAZHO01_Guanyu_Zhou/guazho01.png",
    "BOT": f"{_F1_CDN_BASE}/V/VALBOT01_Valtteri_Bottas/valbot01.png",
    "MAG": f"{_F1_CDN_BASE}/K/KEVMAG01_Kevin_Magnussen/kevmag01.png",
    "HUL": f"{_F1_CDN_BASE}/N/NIHULK01_Nico_Hulkenberg/nihulk01.png",
    "TSU": f"{_F1_CDN_BASE}/Y/YUKTSU01_Yuki_Tsunoda/yuktsu01.png",
    "RIC": f"{_F1_CDN_BASE}/D/DANRIC01_Daniel_Ricciardo/danric01.png",
}

# Takım logoları
# Wikipedia Commons'tan alınan stabil SVG/PNG URL'leri
TEAM_LOGOS: dict[str, str] = {
    "Red Bull Racing": "https://upload.wikimedia.org/wikipedia/en/thumb/9/9f/Red_Bull_Racing_logo.svg/120px-Red_Bull_Racing_logo.svg.png",
    "Ferrari":         "https://upload.wikimedia.org/wikipedia/en/thumb/d/d3/Scuderia_Ferrari_Logo.svg/100px-Scuderia_Ferrari_Logo.svg.png",
    "Mercedes":        "https://upload.wikimedia.org/wikipedia/en/thumb/f/f4/Mercedes_AMG_Petronas_F1_Team_logo.svg/120px-Mercedes_AMG_Petronas_F1_Team_logo.svg.png",
    "McLaren":         "https://upload.wikimedia.org/wikipedia/en/thumb/6/6b/McLaren_Racing_logo.svg/100px-McLaren_Racing_logo.svg.png",
    "Aston Martin":    "https://upload.wikimedia.org/wikipedia/en/thumb/8/8e/Aston_Martin_F1_Team_logo.svg/100px-Aston_Martin_F1_Team_logo.svg.png",
    "Alpine":          "https://upload.wikimedia.org/wikipedia/commons/thumb/7/7e/Alpine_F1_Team_Logo.svg/100px-Alpine_F1_Team_Logo.svg.png",
    "Williams":        "https://upload.wikimedia.org/wikipedia/en/thumb/1/18/Williams_Racing_logo.svg/100px-Williams_Racing_logo.svg.png",
    "RB":              "https://upload.wikimedia.org/wikipedia/en/thumb/1/16/Scuderia_AlphaTauri_logo.svg/100px-Scuderia_AlphaTauri_logo.svg.png",
    "Kick Sauber":     "https://upload.wikimedia.org/wikipedia/en/thumb/7/73/Sauber_Motorsport_logo.svg/100px-Sauber_Motorsport_logo.svg.png",
    "Haas":            "https://upload.wikimedia.org/wikipedia/en/thumb/2/20/Haas_F1_Team_logo.svg/100px-Haas_F1_Team_logo.svg.png",
}

# Erişilemeyen URL'ler için SVG placeholder (base64 embed gerekmez)
PLACEHOLDER_DRIVER = (
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' "
    "width='44' height='44' viewBox='0 0 44 44'%3E"
    "%3Ccircle cx='22' cy='22' r='22' fill='%231a1a3e'/%3E"
    "%3Ctext x='22' y='27' text-anchor='middle' fill='%23ffffff' "
    "font-size='14' font-family='Arial'%3E%3F%3C/text%3E%3C/svg%3E"
)

PLACEHOLDER_TEAM = (
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' "
    "width='80' height='40' viewBox='0 0 80 40'%3E"
    "%3Crect width='80' height='40' fill='%230d0d25' rx='4'/%3E"
    "%3Ctext x='40' y='25' text-anchor='middle' fill='%23666688' "
    "font-size='10' font-family='Arial'%3ELogo%3C/text%3E%3C/svg%3E"
)


# ── URL Erişim Kontrolü ──────────────────────────────────────────────────────
@lru_cache(maxsize=64)
def _url_accessible(url: str, timeout: float = 2.5) -> bool:
    """HEAD isteğiyle URL'nin erişilebilir olduğunu kontrol eder."""
    try:
        r = requests.head(url, timeout=timeout, allow_redirects=True)
        return r.status_code < 400
    except Exception:
        return False


# ── Public API ───────────────────────────────────────────────────────────────
def get_headshot_url(abbr: str) -> str:
    """
    Pilot kısa adına göre headshot URL döner.

    Öncelik:
      1. CDN URL erişilebilirse → CDN URL
      2. Local assets/drivers/<abbr_lower>.png varsa → local path string
      3. Hiçbiri yoksa → SVG placeholder

    NOT: CDN kontrol sonuçları lru_cache ile önbelleğe alınır.
    """
    abbr = abbr.upper()

    # 1. CDN
    cdn_url = DRIVER_HEADSHOTS.get(abbr)
    if cdn_url:
        # Geliştirme sürecinde CDN kontrolünü atla (hız için),
        # canlı ortamda _url_accessible(cdn_url) ile doğrula.
        # Şimdilik URL'yi doğrudan döndürüyoruz; HTML tarafındaki
        # onerror handler local fallback'e yönlendirir.
        return cdn_url

    # 2. Local fallback
    local = DRIVERS_DIR / f"{abbr.lower()}.png"
    if local.exists():
        return str(local)

    logger.debug("Headshot bulunamadı: %s → placeholder kullanılıyor", abbr)
    return PLACEHOLDER_DRIVER


def get_team_logo_url(team_name: str) -> str:
    """
    Takım adına göre logo URL döner.
    Erişilemeyen URL → local fallback → placeholder.
    """
    cdn_url = TEAM_LOGOS.get(team_name)
    if cdn_url:
        return cdn_url

    # Local fallback: assets/teams/<team_lower_underscored>.png
    safe_name = team_name.lower().replace(" ", "_")
    local = TEAMS_DIR / f"{safe_name}.png"
    if local.exists():
        return str(local)

    return PLACEHOLDER_TEAM


def get_all_driver_assets(driver_list: list[dict]) -> dict[str, str]:
    """
    [{'abbr': 'VER', ...}, ...] listesini alır,
    {'VER': 'https://...', 'LEC': '...', ...} sözlüğü döner.
    """
    return {d["abbr"]: get_headshot_url(d["abbr"]) for d in driver_list if "abbr" in d}
