"""內政部消防署 避難收容處所點位檔 (data.gov.tw dataset 73242).

A nationwide CSV published through the MOI open-data resource API (no auth).
We filter by county and normalise to ``shelter`` features. Manager name and
phone are in the public dataset but we deliberately drop the manager's
*name* (a private individual) and keep only the shelter phone.
"""
from __future__ import annotations

import csv
import io

from app.connectors.base import feature, http_get, norm_admin, to_float, valid_point
from app.core.config import settings

SOURCE = "moi_shelter"
HOMEPAGE = "https://data.gov.tw/dataset/73242"
ATTRIBUTION = "內政部消防署 避難收容處所點位檔（政府資料開放授權條款）"


def is_live_enabled() -> bool:
    return bool(settings.MOI_SHELTER_CSV_URL)


def parse_csv(text: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))


def _split_admin(value: str) -> tuple[str, str]:
    """'南投縣信義鄉' -> ('南投縣', '信義鄉'); '新竹縣' -> ('新竹縣', '')."""
    v = norm_admin(value)
    for i, ch in enumerate(v):
        if ch in "縣市" and i >= 1:
            return v[: i + 1], v[i + 1:]
    return v, ""


def map_shelters(rows: list[dict], county: str | None) -> list[dict]:
    out: list[dict] = []
    wanted = norm_admin(county) if county else None
    for row in rows:
        admin = row.get("縣市及鄉鎮市區") or ""
        c, town = _split_admin(admin)
        if wanted and c != wanted:
            continue
        lat = to_float(row.get("緯度"))
        lon = to_float(row.get("經度"))
        if not valid_point(lat, lon):
            continue
        capacity = to_float(row.get("預計收容人數"))
        hazards = [h.strip() for h in (row.get("適用災害類別") or "").split(",") if h.strip()]
        out.append(
            feature(
                id=f"{SOURCE}:{row.get('序號') or len(out)}",
                source=SOURCE,
                layer="shelter",
                lat=lat,  # type: ignore[arg-type]
                lon=lon,  # type: ignore[arg-type]
                properties={
                    "name": (row.get("避難收容處所名稱") or "").strip(),
                    "county": c,
                    "town": town or None,
                    "village": (row.get("村里") or "").strip() or None,
                    "address": (row.get("避難收容處所地址") or "").strip() or None,
                    "capacity": int(capacity) if capacity is not None else None,
                    "hazards": hazards,
                    "indoor": (row.get("室內") or "").strip() == "是",
                    "outdoor": (row.get("室外") or "").strip() == "是",
                    "vulnerable_friendly": (row.get("適合避難弱者安置") or "").strip() == "是",
                    "phone": (row.get("管理人電話") or "").strip() or None,
                    "status": "available",
                },
            )
        )
    return out


def fetch_shelters(county: str | None) -> list[dict]:
    resp = http_get(settings.MOI_SHELTER_CSV_URL, timeout=60)
    text = resp.content.decode("utf-8-sig", errors="replace")
    return map_shelters(parse_csv(text), county)


SAMPLE_CSV = (
    "序號,縣市及鄉鎮市區,村里,避難收容處所地址,經度,緯度,避難收容處所名稱,預計收容村里,預計收容人數,"
    "適用災害類別,管理人姓名,管理人電話,室內,室外,適合避難弱者安置\n"
    "1995,南投縣信義鄉,東埔村,開高巷9號,120.927346,23.554004,東光基督長老教會,東埔村1鄰,150,"
    "\"水災,震災,土石流\",伍宗信 牧師,049-2701402,是,否,否\n"
    "2020,南投縣信義鄉,同富村,太平巷57-1號,120.874626,23.560392,桐林活動中心,同富村-桐林社區,150,"
    "\"水災,震災,土石流\",張進福 理事長,049-2700070,是,否,是\n"
    "2,金門縣烈嶼鄉,林湖村,東林24號,118.248571,24.428328,金門縣烈嶼鄉林湖村辦公處,林湖村,30,"
    "\"水災,震災,土石流,海嘯\",林妙玲,082-364503,是,否,是\n"
)
