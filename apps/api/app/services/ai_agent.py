"""The single LLM touch-point: understand a disaster brief.

Returns the same structure as ``scenario_rules.parse_brief`` so the planner
can merge or ignore it. Every field is validated against the closed
vocabularies (hazards, categories, roles, known counties/towns) — the model
can only *select*, never invent. Any failure returns None and the caller
falls back to rules; the platform pipeline never depends on this call.
"""
from __future__ import annotations

import json

from app.core.config import settings
from app.domain.categories import CATEGORIES, REPORTER_ROLE_KEYS
from app.domain.hazards import HAZARD_KEYS
from app.utils.geo import COUNTY_CENTROIDS, TOWN_CENTROIDS, normalize_admin

_TIMEOUT = 20


def is_enabled() -> bool:
    return bool(settings.OPENAI_API_KEY)


def _chat(messages: list[dict], *, max_tokens: int = 500) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    resp = client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=messages,
        temperature=0.2,
        max_tokens=max_tokens,
        timeout=_TIMEOUT,
        response_format={"type": "json_object"},
    )
    return resp.choices[0].message.content or ""


_SYSTEM = (
    "你是台灣災害應變的情境分析助理。把使用者的災害背景描述抽取為結構化 JSON，"
    "只能從給定的選項中挑選，不能捏造地名或新增選項。"
)


def _prompt(message: str) -> str:
    counties = "、".join(COUNTY_CENTROIDS.keys())
    return (
        f"災害背景描述：「{message}」\n\n"
        "請輸出 JSON，欄位如下：\n"
        f'"county": 縣市（從 [{counties}] 擇一，沒有則 null）,\n'
        '"towns": 鄉鎮市區名稱陣列（只列描述中明確出現的，沒有則 []）,\n'
        f'"hazards": 災害類型陣列，從 {list(HAZARD_KEYS)} 選，依重要性排序,\n'
        f'"impacts": 主要災情陣列，從 {list(CATEGORIES.keys())} 選,\n'
        f'"reporter_roles": 回報者陣列，從 {sorted(REPORTER_ROLE_KEYS)} 選,\n'
        '"name": 平台的簡短正式名稱（20 字內）,\n'
        '"summary": 一句話的情境摘要（60 字內，繁體中文）\n'
        "無法判斷的欄位請給 null 或空陣列。"
    )


def parse_scenario(message: str) -> dict | None:
    if not is_enabled():
        return None
    try:
        content = _chat([
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": _prompt(message)},
        ])
        data = json.loads(content)
    except Exception:  # noqa: BLE001 — any failure => rules fallback
        return None
    if not isinstance(data, dict):
        return None

    county = normalize_admin(data.get("county")) or None
    if county and county not in COUNTY_CENTROIDS:
        county = None
    known_towns = TOWN_CENTROIDS.get(county or "", {})
    towns = [normalize_admin(t) for t in (data.get("towns") or []) if isinstance(t, str)]
    towns = [t for t in towns if t in known_towns] if known_towns else []
    hazards = [h for h in (data.get("hazards") or []) if h in HAZARD_KEYS]
    impacts = [c for c in (data.get("impacts") or []) if c in CATEGORIES]
    roles = [r for r in (data.get("reporter_roles") or []) if r in REPORTER_ROLE_KEYS]
    name = str(data.get("name") or "").strip()[:40] or None
    summary = str(data.get("summary") or "").strip()[:120] or None
    return {
        "county": county,
        "towns": list(dict.fromkeys(towns)),
        "hazards": list(dict.fromkeys(hazards)),
        "impacts": list(dict.fromkeys(impacts)),
        "reporter_roles": list(dict.fromkeys(roles)),
        "name": name,
        "summary": summary,
    }
