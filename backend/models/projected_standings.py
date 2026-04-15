# backend/models/projected_standings.py
"""
Yarış sonu tahmini şampiyona puan durumu (Projected Standings).

Algoritma:
  1. Mevcut yarış sıralamasını (anlık pozisyonlar) al.
  2. Her pozisyon için F1 puan tablosunu uygula (25-18-15-12-10-8-6-4-2-1).
  3. Fastest lap bonusunu (1 puan, top-10'da biten sürücüye) ekle.
  4. Yarış öncesi şampiyona puanlarına ekle → Projected Total.
  5. Current Total ile farkı (Delta) hesapla.
"""

from backend.data.fastf1_loader import CHAMPIONSHIP_POINTS_2024, DRIVER_INFO

# F1 Puan tablosu (1. → 10. pozisyon)
F1_POINTS_TABLE: dict[int, int] = {
    1: 25, 2: 18, 3: 15, 4: 12, 5: 10,
    6: 8,  7: 6,  8: 4,  9: 2,  10: 1,
}

def calculate_projected_standings(
    current_race_positions: list[dict],
    fastest_lap_driver: str | None = None,
    championship_points: dict[str, int] | None = None,
) -> list[dict]:
    """
    Parameters
    ----------
    current_race_positions : list[dict]
        get_positions() çıktısı — her eleman {'abbr': str, 'position': int, ...}
    fastest_lap_driver : str | None
        En hızlı turu atan pilotun kısa adı (örn: 'VER').
        Top-10'da biterse +1 puan alır.
    championship_points : dict[str, int] | None
        {'VER': 393, 'NOR': 331, ...} — None ise varsayılan 2024 verileri kullanılır.

    Returns
    -------
    list[dict]
        [
            {
                'abbr': 'VER',
                'driver_number': '1',
                'team': 'Red Bull Racing',
                'current_champ_points': 393,   # yarış öncesi
                'race_points': 25,              # bu yarıştan kazanılan
                'projected_total': 418,         # tahmini yeni toplam
                'delta': +25,                   # değişim
                'projected_position': 1,        # tahmini şampiyona sırası
            },
            ...
        ]
    """
    if championship_points is None:
        championship_points = CHAMPIONSHIP_POINTS_2024

    # Pozisyon listesini sırala (bazı veri kaynaklarında karışık gelir)
    sorted_positions = sorted(current_race_positions, key=lambda d: d.get("position", 99))

    # En hızlı tur üstündeki pilotun top-10'da olup olmadığını belirle
    fastest_top10_abbr: str | None = None
    if fastest_lap_driver:
        for d in sorted_positions[:10]:
            if d.get("abbr") == fastest_lap_driver:
                fastest_top10_abbr = fastest_lap_driver
                break

    results = []
    for driver in sorted_positions:
        abbr = driver.get("abbr", "")
        drv_num = driver.get("driver_number", "")
        pos = driver.get("position", 99)
        team = driver.get("team", "")

        # Bu yarıştan kazanılan puan
        race_pts = F1_POINTS_TABLE.get(pos, 0)
        if abbr == fastest_top10_abbr:
            race_pts += 1

        current = championship_points.get(abbr, 0)
        projected = current + race_pts

        results.append({
            "abbr": abbr,
            "driver_number": drv_num,
            "team": team,
            "race_position": pos,
            "current_champ_points": current,
            "race_points": race_pts,
            "projected_total": projected,
            "delta": race_pts,  # yarış öncesine göre fark
        })

    # Tahmini şampiyona sıralaması (projected_total'a göre büyükten küçüğe)
    results_sorted = sorted(results, key=lambda x: x["projected_total"], reverse=True)
    for rank, item in enumerate(results_sorted, start=1):
        item["projected_champ_position"] = rank

    # Orijinal yarış pozisyon sırasına geri döndür
    results_by_abbr = {r["abbr"]: r for r in results_sorted}
    final = []
    for driver in sorted_positions:
        abbr = driver.get("abbr", "")
        if abbr in results_by_abbr:
            final.append(results_by_abbr[abbr])

    return final


def get_standings_summary(projected: list[dict]) -> dict:
    """
    Şampiyona lideri ve top-3'ü özetler.
    Streamlit sidebar'da gösterim için kullanılır.
    """
    if not projected:
        return {}

    by_proj = sorted(projected, key=lambda x: x["projected_total"], reverse=True)
    return {
        "leader": by_proj[0]["abbr"] if by_proj else "N/A",
        "leader_points": by_proj[0]["projected_total"] if by_proj else 0,
        "top3": [
            {
                "abbr": d["abbr"],
                "projected_total": d["projected_total"],
                "delta": d["delta"],
                "team": d["team"],
            }
            for d in by_proj[:3]
        ],
    }
