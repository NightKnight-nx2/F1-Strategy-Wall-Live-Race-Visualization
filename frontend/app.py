# frontend/app.py
"""
F1 Strateji Duvarı — Ana Streamlit Uygulaması

Layout:
  Sol  (55%) → D3.js İnteraktif Pist Haritası
  Sağ  (45%) → Driver Standings | Live Predictions | Safety Car Risk

Polling: @st.fragment(run_every=5) — sayfayı bloklamadan 5s'de bir güncellenir.
Başlatma: streamlit run frontend/app.py
"""

import sys
import json
import logging
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import requests
import streamlit as st
import streamlit.components.v1 as components

logger = logging.getLogger(__name__)

API_BASE       = "http://localhost:8000"
POLL_SECS      = 5
MAP_HEIGHT     = 560
TRACK_MAP_PATH = Path(__file__).parent / "components" / "track_map.html"

# ─── Sayfa Yapılandırması ────────────────────────────────────────────────────
st.set_page_config(
    page_title="F1 Strategy Wall",
    page_icon="🏎️",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ─── CSS ────────────────────────────────────────────────────────────────────
def inject_css():
    css_path = Path(__file__).parent / "styles" / "theme.css"
    base_css = css_path.read_text(encoding="utf-8") if css_path.exists() else ""
    extra = """
    .stApp { font-family: 'Arial Narrow', Arial, sans-serif !important; }
    .panel-header {
        background: linear-gradient(90deg, rgba(6,0,239,0.2) 0%, transparent 100%);
        border-left: 3px solid #0600EF;
        padding: 6px 12px; margin-bottom: 12px;
        border-radius: 0 4px 4px 0;
    }
    .panel-header span {
        color: #FFFFFF !important; font-size: 13px !important;
        font-weight: 700 !important; text-transform: uppercase; letter-spacing: 1.5px;
    }
    .live-dot {
        display:inline-block; width:8px; height:8px; background:#00FF88;
        border-radius:50%; margin-right:6px; animation: pulse 1.5s infinite;
    }
    @keyframes pulse {
        0%,100%{opacity:1;transform:scale(1)} 50%{opacity:0.4;transform:scale(0.8)}
    }
    """
    st.markdown(f"<style>{base_css}{extra}</style>", unsafe_allow_html=True)


# ─── API ────────────────────────────────────────────────────────────────────
def _get(endpoint: str, params: dict | None = None) -> dict | None:
    try:
        r = requests.get(f"{API_BASE}{endpoint}", params=params, timeout=3)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        return None
    except Exception as exc:
        logger.warning("API [%s]: %s", endpoint, exc)
        return None

# cache_data TTL = POLL_SECS — fragment yenilendiğinde taze veri gelir
@st.cache_data(ttl=POLL_SECS, show_spinner=False)
def fetch_positions():       return _get("/live/positions")

@st.cache_data(ttl=POLL_SECS, show_spinner=False)
def fetch_timing():          return _get("/live/timing")

@st.cache_data(ttl=POLL_SECS, show_spinner=False)
def fetch_session():         return _get("/live/session")

@st.cache_data(ttl=POLL_SECS, show_spinner=False)
def fetch_tire_predictions(): return _get("/predict/tires/all")

@st.cache_data(ttl=POLL_SECS, show_spinner=False)
def fetch_safety_car(rainfall: float = 0.0, incidents: int = 0):
    return _get("/predict/safety-car", {"rainfall": rainfall, "incident_count": incidents})

@st.cache_data(ttl=POLL_SECS, show_spinner=False)
def fetch_projected_standings(): return _get("/standings/projected")


# ─── Sidebar (bir kez render edilir, fragment dışında) ───────────────────────
def render_sidebar():
    with st.sidebar:
        st.markdown(
            """
            <div style="text-align:center;padding:16px 0 8px;">
              <div style="font-size:28px;">🏎️</div>
              <div style="color:#FFF;font-size:15px;font-weight:700;letter-spacing:2px;">
                F1 STRATEGY WALL
              </div>
              <div style="color:#8888bb;font-size:10px;margin-top:4px;">
                Red Bull Racing · Pit Wall
              </div>
            </div>
            <hr style="border-color:rgba(6,0,239,0.3);margin:8px 0;">
            """,
            unsafe_allow_html=True,
        )

        api_ok = _get("/health") is not None
        status_html = (
            '<div style="color:#00FF88;font-size:11px;">'
            '<span class="live-dot"></span>API BAĞLI</div>'
            if api_ok else
            '<div style="color:#FF6666;font-size:11px;">⚠️ API YOK — Simülasyon</div>'
        )
        st.markdown(status_html, unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

        st.markdown("**Koşul Parametreleri**")
        rainfall  = st.slider("Yağmur",    0.0, 1.0, 0.0, 0.05, key="rainfall")
        incidents = st.number_input("Pist Olayı", 0, 10, 0, key="incidents")

        st.markdown("<hr>", unsafe_allow_html=True)
        st.markdown(
            '<div style="color:#444466;font-size:9px;text-align:center;">'
            'FastF1 · XGBoost · D3.js · Streamlit</div>',
            unsafe_allow_html=True,
        )
    return float(rainfall), int(incidents)


# ─── Auto-Refresh (JS tabanlı, sleep yok) ───────────────────────────────────
def inject_autorefresh(interval_ms: int = 5000):
    """
    Gizli bir iframe içinde setTimeout ile parent pencereyi yeniler.
    st.fragment olmadan, time.sleep kullanmadan non-blocking polling sağlar.
    """
    components.html(
        f"""<script>
          setTimeout(function() {{
            window.parent.location.reload();
          }}, {interval_ms});
        </script>""",
        height=0,
        width=0,
    )


# ─── Pist Haritası ───────────────────────────────────────────────────────────
def fragment_track_map():
    from frontend.components.asset_resolver import get_headshot_url

    pos_res   = fetch_positions()
    tire_res  = fetch_tire_predictions()
    proj_res  = fetch_projected_standings()

    positions  = pos_res.get("data",  []) if pos_res  else []
    tire_preds = tire_res.get("data", []) if tire_res else []
    proj_list  = proj_res.get("data", []) if proj_res else []

    tire_map = {p["driver_number"]: p for p in tire_preds}
    proj_map = {p["driver_number"]: p for p in proj_list}

    drivers_js = []
    for d in positions:
        num = d.get("driver_number", "0")
        tp  = tire_map.get(num, {})
        pp  = proj_map.get(num, {})

        x = d.get("x", 0) or 0
        track_pos = round((x / 1000) % 1, 4)

        drivers_js.append({
            "driver_number":        num,
            "abbr":                 d.get("abbr", "---"),
            "color":                d.get("color", "#FFFFFF"),
            "team":                 d.get("team", ""),
            "position":             d.get("position", 99),
            "track_position":       track_pos,
            "tire":                 d.get("tire", "MEDIUM"),
            "tire_age":             d.get("tire_age", 0),
            "lap":                  d.get("lap", 0),
            "tire_wear_pct":        tp.get("tire_wear_pct", 0),
            "pit_recommended":      tp.get("pit_recommended", False),
            "pit_window_start":     tp.get("pit_window_start", 0),
            "pit_window_end":       tp.get("pit_window_end", 0),
            "current_champ_points": pp.get("current_champ_points", 0),
            "projected_total":      pp.get("projected_total", 0),
            "delta":                pp.get("delta", 0),
            "headshot_url":         get_headshot_url(d.get("abbr", "")),
        })

    st.markdown(
        '<div class="panel-header"><span>🗺️ Live Track Map · Abu Dhabi 2024</span></div>',
        unsafe_allow_html=True,
    )

    if not TRACK_MAP_PATH.exists():
        st.error("track_map.html bulunamadı.")
        return

    html_src   = TRACK_MAP_PATH.read_text(encoding="utf-8")
    injection  = f"<script>window.RACE_DATA={{\"drivers\":{json.dumps(drivers_js)}}};</script>"
    html_final = html_src.replace("</body>", f"{injection}</body>")
    components.html(html_final, height=MAP_HEIGHT, scrolling=False)


# ─── Sağ Paneller ────────────────────────────────────────────────────────────
def fragment_right_panels():
    rainfall  = st.session_state.get("rainfall",  0.0)
    incidents = st.session_state.get("incidents", 0)

    session_res = fetch_session()
    tire_res    = fetch_tire_predictions()
    proj_res    = fetch_projected_standings()
    sc_res      = fetch_safety_car(float(rainfall), int(incidents))
    pos_res     = fetch_positions()

    session_d  = session_res.get("data", {}) if session_res else {}
    tire_preds = tire_res.get("data",    []) if tire_res    else []
    proj_list  = proj_res.get("data",    []) if proj_res    else []
    positions  = pos_res.get("data",     []) if pos_res     else []

    # Üst metrikler
    if session_d:
        m1, m2, m3 = st.columns(3)
        m1.metric("Tur",  f"{session_d.get('current_lap','--')} / {session_d.get('total_laps','--')}")
        m2.metric("GP",   session_d.get("gp", "---"))
        sc_active = sc_res.get("data", {}).get("sc_active", False) if sc_res else False
        m3.metric("Flag", "🟡 SC" if sc_active else "🟢 GO")

        # Sidebar yarış bilgisi güncelle
        st.sidebar.markdown(
            f"""
            <div style="font-size:11px;color:#c0c0e0;margin-top:8px;">
              🏁 <b style="color:#FFCC00;">{session_d.get('gp','---')}</b> {session_d.get('year','')}<br>
              🔄 Tur: <b>{session_d.get('current_lap','--')}</b> / {session_d.get('total_laps','--')}<br>
              🚦 <b style="color:#00FF88;">{session_d.get('flag','GREEN')}</b>
              {'&nbsp;|&nbsp;⚠️ <span style="color:#FF4444;">SİMÜLASYON</span>' if session_d.get('simulated') else '&nbsp;|&nbsp;✅ CANLI'}
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    tab1, tab2, tab3 = st.tabs(["🏆 Standings", "🔧 Predictions", "⚠️ Safety Car"])

    with tab1:
        _render_standings(proj_list)
    with tab2:
        _render_predictions(tire_preds, positions)
    with tab3:
        _render_safety_car(sc_res)


# ─── Standings ───────────────────────────────────────────────────────────────
def _render_standings(proj_data: list[dict]):
    st.markdown(
        '<div class="panel-header"><span>🏆 Driver Standings · Live Delta</span></div>',
        unsafe_allow_html=True,
    )
    if not proj_data:
        st.info("Standings verisi bekleniyor...")
        return

    import pandas as pd

    rows = []
    for item in sorted(proj_data, key=lambda x: x.get("projected_total", 0), reverse=True):
        delta = item.get("delta", 0)
        rows.append({
            "P":       item.get("projected_champ_position", "-"),
            "Pilot":   item.get("abbr", "---"),
            "Takım":   item.get("team", ""),
            "Tur P.":  item.get("race_points", 0),
            "Mevcut":  item.get("current_champ_points", 0),
            "Tahmini": item.get("projected_total", 0),
            "Δ":       f"+{delta}" if delta > 0 else str(delta),
        })

    df = pd.DataFrame(rows)

    def style_delta(val):
        return "color:#00FF88;font-weight:bold;" if str(val).startswith("+") else "color:#c0c0e0;"

    st.dataframe(
        df.style.map(style_delta, subset=["Δ"]),
        use_container_width=True,
        hide_index=True,
        height=280,
    )


# ─── Predictions ─────────────────────────────────────────────────────────────
def _render_predictions(tire_preds: list[dict], positions: list[dict]):
    st.markdown(
        '<div class="panel-header"><span>🔧 Lastik Aşınması & Pit Penceresi</span></div>',
        unsafe_allow_html=True,
    )
    if not tire_preds:
        st.info("Tahmin verisi bekleniyor...")
        return

    pos_map = {p["driver_number"]: p for p in positions}

    # Pit aciliyetine göre sırala
    sorted_preds = sorted(tire_preds, key=lambda x: x.get("pit_probability", 0), reverse=True)

    # Tüm kartları tek HTML bloğuna topla → components.html() ile render et
    # Bu yaklaşım st.markdown'ın HTML sanitizer'ından kaçınır
    cards_html = ""
    for pred in sorted_preds[:10]:
        num      = pred.get("driver_number", "0")
        pos_d    = pos_map.get(num, {})
        abbr     = pos_d.get("abbr", f"#{num}")
        color    = pos_d.get("color", "#FFFFFF")
        compound = pos_d.get("tire", "MEDIUM").upper()
        wear     = float(pred.get("tire_wear_pct", 0))
        pit_rec  = bool(pred.get("pit_recommended", False))
        win_s    = pred.get("pit_window_start", "-")
        win_e    = pred.get("pit_window_end", "-")

        if wear >= 80:
            wear_color = "#FF4444"
        elif wear >= 55:
            wear_color = "#FFCC00"
        else:
            wear_color = "#00CC66"

        tire_colors_map = {"SOFT": "#FF4444", "MEDIUM": "#FFCC00", "HARD": "#DDDDDD"}
        tire_c = tire_colors_map.get(compound, "#888888")

        pit_badge_html = (
            '<span style="color:#FF4444;font-size:9px;font-weight:700;'
            'background:rgba(255,0,0,0.15);padding:1px 6px;border-radius:8px;'
            'border:1px solid #FF4444;margin-left:6px;">PIT!</span>'
            if pit_rec else ""
        )

        # Pit window 57-57 gibi son tur sınırı görünüyorsa "Son Tur" yaz
        pit_window_str = (
            "Son tur" if win_s == win_e and win_s != "-"
            else f"Tur {win_s}–{win_e}"
        )

        cards_html += f"""
        <div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);
                    border-radius:6px;padding:9px 11px;margin-bottom:7px;">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:7px;">
            <div style="display:flex;align-items:center;gap:6px;">
              <span style="color:{color};font-weight:800;font-size:14px;letter-spacing:0.5px;">{abbr}</span>
              <span style="background:rgba(255,255,255,0.06);color:{tire_c};
                           border:1px solid {tire_c};font-size:9px;font-weight:700;
                           padding:1px 7px;border-radius:10px;">{compound}</span>
              {pit_badge_html}
            </div>
            <span style="color:#8888aa;font-size:10px;">{pit_window_str}</span>
          </div>
          <div style="display:flex;align-items:center;gap:8px;">
            <div style="flex:1;background:rgba(255,255,255,0.06);border-radius:4px;
                        height:7px;overflow:hidden;">
              <div style="width:{min(wear,100):.0f}%;height:100%;background:{wear_color};
                          border-radius:4px;"></div>
            </div>
            <span style="color:{wear_color};font-size:11px;font-weight:700;
                         min-width:34px;text-align:right;">{wear:.0f}%</span>
          </div>
        </div>
        """

    # Tüm kartları dark arka plan ile tek bir components.html çağrısında render et
    components.html(
        f"""
        <html><head><style>
          * {{ margin:0; padding:0; box-sizing:border-box; }}
          body {{ background:transparent; font-family:'Arial Narrow',Arial,sans-serif; }}
        </style></head>
        <body>{cards_html}</body></html>
        """,
        height=min(len(sorted_preds[:10]) * 72 + 10, 720),
        scrolling=True,
    )


# ─── Safety Car ──────────────────────────────────────────────────────────────
def _render_safety_car(sc_res: dict | None):
    st.markdown(
        '<div class="panel-header"><span>⚠️ Safety Car Risk</span></div>',
        unsafe_allow_html=True,
    )
    if not sc_res or "data" not in sc_res:
        st.info("Safety Car verisi bekleniyor...")
        return

    d        = sc_res["data"]
    prob     = float(d.get("sc_probability", 0))
    active   = bool(d.get("sc_active", False))
    triggers = d.get("triggers", [])

    if prob >= 60:
        bar_color, risk_label, risk_color = "#FF0000", "YÜKSEK RİSK", "#FF4444"
    elif prob >= 35:
        bar_color, risk_label, risk_color = "#FFCC00", "ORTA RİSK",   "#FFCC00"
    else:
        bar_color, risk_label, risk_color = "#00CC66", "DÜŞÜK RİSK",  "#00CC66"

    triggers_html = "".join(
        f'<div style="color:#aaaacc;font-size:11px;padding:2px 0;">· {t}</div>'
        for t in triggers
    )
    active_html = (
        '<div style="background:rgba(255,0,0,0.2);border:1px solid #FF0000;'
        'border-radius:6px;padding:8px;margin-bottom:10px;text-align:center;">'
        '<span style="color:#FF4444;font-weight:700;font-size:13px;letter-spacing:1px;">'
        '🚨 GÜVENLİK ARACI AKTİF</span></div>'
    ) if active else ""

    components.html(
        f"""
        <html><head><style>
          * {{ margin:0; padding:0; box-sizing:border-box; }}
          body {{ background:transparent; font-family:'Arial Narrow',Arial,sans-serif;
                 color:#ffffff; padding:4px; }}
        </style></head><body>
          {active_html}
          <div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);
                      border-radius:8px;padding:14px;">
            <div style="display:flex;justify-content:space-between;align-items:center;
                        margin-bottom:10px;">
              <span style="color:#8888aa;font-size:11px;text-transform:uppercase;
                           letter-spacing:1px;">SC Olasılığı</span>
              <span style="color:{risk_color};font-size:14px;font-weight:700;">{risk_label}</span>
            </div>
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px;">
              <div style="flex:1;background:rgba(255,255,255,0.07);border-radius:6px;
                          height:14px;overflow:hidden;">
                <div style="width:{prob:.0f}%;height:100%;background:{bar_color};
                            border-radius:6px;box-shadow:0 0 8px {bar_color}88;"></div>
              </div>
              <span style="color:{risk_color};font-size:22px;font-weight:900;
                           min-width:52px;text-align:right;">{prob:.0f}%</span>
            </div>
            <div style="border-top:1px solid rgba(255,255,255,0.07);padding-top:8px;">
              <div style="color:#666688;font-size:9px;text-transform:uppercase;
                          letter-spacing:1px;margin-bottom:4px;">Tetikleyiciler</div>
              {triggers_html}
            </div>
          </div>
        </body></html>
        """,
        height=200 if not active else 240,
        scrolling=False,
    )


# ─── Ana Uygulama ─────────────────────────────────────────────────────────────
def main():
    inject_css()

    # Başlık (fragment dışında — bir kez render edilir)
    st.markdown(
        """
        <div style="display:flex;align-items:center;gap:14px;padding:6px 0 14px;">
          <div style="font-size:34px;">🏎️</div>
          <div>
            <div style="color:#FFF;font-size:22px;font-weight:800;letter-spacing:3px;
                        border-bottom:2px solid #0600EF;padding-bottom:4px;">
              F1 STRATEGY WALL
            </div>
            <div style="color:#8888bb;font-size:11px;letter-spacing:2px;margin-top:4px;">
              LIVE TELEMETRY · PREDICTIONS · PIT STRATEGY
            </div>
          </div>
          <div style="margin-left:auto;">
            <span class="live-dot"></span>
            <span style="color:#00FF88;font-size:11px;font-weight:700;">LIVE</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Sidebar
    render_sidebar()

    # İki sütun
    left_col, right_col = st.columns([1.25, 1], gap="medium")

    with left_col:
        fragment_track_map()

        # Timing tower (fragment dışında, expander'da)
        timing_res = fetch_timing()
        if timing_res and timing_res.get("data"):
            with st.expander("⏱️ Timing Tower", expanded=False):
                import pandas as pd
                timing_df = pd.DataFrame(timing_res["data"])
                if not timing_df.empty:
                    cols = ["position", "abbr", "lap_time", "gap", "sector1", "sector2", "sector3"]
                    cols = [c for c in cols if c in timing_df.columns]
                    st.dataframe(timing_df[cols], use_container_width=True, hide_index=True)

    with right_col:
        fragment_right_panels()

    # 5 saniyede bir sayfayı yenile (non-blocking, JS tabanlı)
    inject_autorefresh(interval_ms=POLL_SECS * 1000)


if __name__ == "__main__":
    main()
