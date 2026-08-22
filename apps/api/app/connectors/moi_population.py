"""內政部戶政司 人口統計 connector — village population for the platform's
county, aggregated to townships so cases can be weighted by the people
they may affect.

Documented: https://www.ris.gov.tw/rs-opendata/api/v1/datastore/ODRP013/{yyymm}?COUNTY=...
(各村里人口數 by 原住民身分; fields site_id = 縣市鄉鎮, village, people_total,
people_total_m/f, indigenous_mountain_total_m/f ...). Public, no key. The
newest month is found by walking back from the current ROC month.
"""
from __future__ import annotations

import threading
import time
from datetime import date

from app.connectors.base import ConnectorError, feature, http_get_json, norm_admin, to_float
from app.core.config import settings
from app.utils.geo import centroid_for

SOURCE = "moi_population"
HOMEPAGE = "https://www.ris.gov.tw/rs-opendata/api/Main/docs/v1"
ATTRIBUTION = "內政部戶政司 人口統計資料（政府資料開放授權條款）"
DATASET = "ODRP013"


def is_live_enabled() -> bool:
    return True


def roc_months(today: date | None = None, back: int = 8) -> list[str]:
    """['11507', '11506', ...] newest first."""
    d = today or date.today()
    y, m = d.year, d.month
    out = []
    for _ in range(back):
        out.append(f"{y - 1911:03d}{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out


_cache: dict[str, tuple[float, list[dict], str]] = {}
_lock = threading.Lock()


def fetch_villages(county: str) -> tuple[list[dict], str]:
    """All village rows for the county from the newest month that has data
    (cached for a day — the statistics are monthly)."""
    key = norm_admin(county)
    with _lock:
        hit = _cache.get(key)
        if hit and time.monotonic() - hit[0] < 86400:
            return hit[1], hit[2]
    last_error = "查無資料"
    for ym in roc_months():
        rows: list[dict] = []
        page = 1
        while True:
            body = http_get_json(f"{settings.MOI_RIS_API_BASE}/{DATASET}/{ym}", params={"COUNTY": key, "PAGE": page}, timeout=60)
            if not isinstance(body, dict) or str(body.get("responseCode", "")).endswith("0102-S"):
                break
            data = body.get("responseData") or []
            rows.extend(r for r in data if isinstance(r, dict))
            if page >= int(body.get("totalPage") or 1):
                break
            page += 1
        if rows:
            with _lock:
                _cache[key] = (time.monotonic(), rows, ym)
            return rows, ym
    raise ConnectorError(f"戶政司人口統計：{last_error}")


def aggregate_towns(rows: list[dict], county: str) -> list[dict]:
    """Village rows → one record per township."""
    towns: dict[str, dict] = {}
    c = norm_admin(county)
    for r in rows:
        site = norm_admin(r.get("site_id"))
        if not site.startswith(c):
            continue
        town = site[len(c):] or site
        t = towns.setdefault(town, {"town": town, "population": 0, "male": 0, "female": 0, "indigenous_mountain": 0, "villages": 0})
        t["population"] += int(to_float(r.get("people_total")) or 0)
        t["male"] += int(to_float(r.get("people_total_m")) or 0)
        t["female"] += int(to_float(r.get("people_total_f")) or 0)
        t["indigenous_mountain"] += int(to_float(r.get("indigenous_mountain_total_m")) or 0) + int(to_float(r.get("indigenous_mountain_total_f")) or 0)
        t["villages"] += 1
    return sorted(towns.values(), key=lambda t: -t["population"])


def map_population(rows: list[dict], county: str, month: str) -> list[dict]:
    towns = aggregate_towns(rows, county)
    total = sum(t["population"] for t in towns) or 1
    out: list[dict] = []
    for t in towns:
        ll = centroid_for(county, t["town"])
        if ll is None:
            continue
        share = t["population"] / total
        out.append(feature(
            id=f"{SOURCE}:town:{county}:{t['town']}", source=SOURCE, layer="population", lat=ll[0], lon=ll[1],
            properties={
                "name": t["town"],
                "town": t["town"],
                "county": norm_admin(county),
                "population": t["population"],
                "male": t["male"],
                "female": t["female"],
                "indigenous_mountain": t["indigenous_mountain"],
                "indigenous_share": round(t["indigenous_mountain"] / t["population"], 3) if t["population"] else 0,
                "villages": t["villages"],
                "share": round(share, 4),
                "county_population": total,
                "statistic_month": month,
                "status": "ok",
                "severity": "low",
                "indicative": True,
            },
        ))
    return out


def fetch_population(county: str | None) -> list[dict]:
    if not county:
        return []
    rows, ym = fetch_villages(county)
    return map_population(rows, county, ym)


SAMPLE_ROWS: list[dict] = [
    {"statistic_yyymm": "11506", "site_id": "南投縣仁愛鄉", "village": "親愛村", "people_total": "1200", "people_total_m": "620", "people_total_f": "580",
     "indigenous_mountain_total_m": "500", "indigenous_mountain_total_f": "470"},
    {"statistic_yyymm": "11506", "site_id": "南投縣仁愛鄉", "village": "大同村", "people_total": "2100", "people_total_m": "1080", "people_total_f": "1020",
     "indigenous_mountain_total_m": "600", "indigenous_mountain_total_f": "590"},
    {"statistic_yyymm": "11506", "site_id": "南投縣埔里鎮", "village": "南門里", "people_total": "3400", "people_total_m": "1700", "people_total_f": "1700",
     "indigenous_mountain_total_m": "20", "indigenous_mountain_total_f": "22"},
    {"statistic_yyymm": "11506", "site_id": "臺中市西區", "village": "民龍里", "people_total": "5000", "people_total_m": "2500", "people_total_f": "2500"},
]
