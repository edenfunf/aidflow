"""台灣電力公司 計畫性工作停電資料 connector (data.gov.tw 26144).

A daily ZIP of per-district CSVs (utf-8-sig) with 營業區處, 請求號數, 工作概述,
第一次停電時間, 第二次停電時間, 停電範圍 (free-text address), 查詢電話. No
coordinates are published, so outages are aggregated per township and placed
at the township centre (flagged ``indicative``). These are *planned*
maintenance outages — the only outage data Taipower publishes as open data;
incident outages are not available and are never fabricated.
"""
from __future__ import annotations

import csv
import io
import zipfile

from app.connectors.base import ConnectorError, feature, http_get, norm_admin
from app.core.config import settings
from app.utils.geo import centroid_for, towns_of

SOURCE = "taipower"
HOMEPAGE = "https://data.gov.tw/dataset/26144"
ATTRIBUTION = "台灣電力公司 計畫性工作停電資料（政府資料開放授權條款）"


def is_live_enabled() -> bool:
    return True


def fetch_rows() -> list[dict]:
    resp = http_get(settings.TAIPOWER_OUTAGE_ZIP_URL, timeout=60)
    try:
        z = zipfile.ZipFile(io.BytesIO(resp.content))
    except zipfile.BadZipFile as exc:
        raise ConnectorError("停電資料不是 ZIP 檔") from exc
    rows: list[dict] = []
    for name in z.namelist():
        if not name.lower().endswith(".csv"):
            continue
        text = z.read(name).decode("utf-8-sig", "replace")
        for r in csv.DictReader(io.StringIO(text)):
            rows.append({(k or "").strip(): (v or "").strip() for k, v in r.items()})
    return rows


def map_outages(rows: list[dict], county: str | None) -> list[dict]:
    if not county:
        return []
    c = norm_admin(county)
    towns = towns_of(county)
    per_town: dict[str, list[dict]] = {}
    for r in rows:
        area = norm_admin(r.get("停電範圍"))
        if not area.startswith(c):
            continue
        town = next((t for t in towns if t in area), None) or "其他"
        per_town.setdefault(town, []).append(r)
    out: list[dict] = []
    for town, items in per_town.items():
        ll = centroid_for(county, town if town != "其他" else None)
        if ll is None:
            continue
        out.append(feature(
            id=f"{SOURCE}:town:{c}:{town}", source=SOURCE, layer="power_outage", lat=ll[0], lon=ll[1],
            properties={
                "name": f"{town} 計畫停電 {len(items)} 件",
                "town": town,
                "county": c,
                "count": len(items),
                "items": [{"when": i.get("第一次停電時間"), "when2": i.get("第二次停電時間") if i.get("第二次停電時間") not in ("", "無") else None,
                           "work": i.get("工作概述"), "area": i.get("停電範圍"), "office": i.get("營業區處"), "ref": i.get("請求號數")} for i in items[:12]],
                "phone": items[0].get("查詢電話(1911)") or "1911",
                "status": "planned",
                "severity": "medium" if len(items) >= 5 else "low",
                "kind": "planned_outage",
                "indicative": True,
            },
        ))
    return out


def fetch_outages(county: str | None) -> list[dict]:
    return map_outages(fetch_rows(), county)


SAMPLE_ROWS: list[dict] = [
    {"營業區處": "台電南投區營業處", "請求號數": "N10001", "工作概述": "改良工程", "第一次停電時間": "2026/08/23 09:00~12:00", "第二次停電時間": "無",
     "停電範圍": "南投縣埔里鎮中山路二段", "查詢電話(1911)": "1911"},
    {"營業區處": "台電南投區營業處", "請求號數": "N10002", "工作概述": "線路遷移", "第一次停電時間": "2026/08/23 13:00~16:00", "第二次停電時間": "無",
     "停電範圍": "南投縣埔里鎮南門里", "查詢電話(1911)": "1911"},
    {"營業區處": "台電基隆區營業處", "請求號數": "L18081", "工作概述": "改良工程", "第一次停電時間": "2026/08/22 09:00~12:00", "第二次停電時間": "無",
     "停電範圍": "基隆市仁愛區仁二路", "查詢電話(1911)": "1911"},
]
