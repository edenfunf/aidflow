"""Scenario profiles — compose hazards into one platform recipe.

A ScenarioProfile is derived deterministically from the hazards (and region)
the planner extracted from the brief. It decides which report categories the
form shows, which map layers are relevant, and which modules are suggested.
Adding a new disaster type is a new Hazard in domain/hazards.py, not new code
here.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from app.domain.categories import CATEGORIES, REPORTER_ROLES
from app.domain.hazards import HAZARDS, hazard_label
from app.modules.registry import registry


@dataclass(frozen=True)
class ScenarioProfile:
    hazards: tuple[str, ...]
    primary_hazard: str
    label: str  # 颱風豪雨 / 地震 …
    county: str | None
    towns: tuple[str, ...]
    report_categories: tuple[dict, ...]  # {key, label, default_severity}
    reporter_roles: tuple[dict, ...]  # {key, label}
    layers: tuple[str, ...]
    modules: tuple[str, ...]
    reasons: tuple[dict, ...] = field(default_factory=tuple)  # {module_id, reason}

    def to_dict(self) -> dict:
        return asdict(self)


_FORM_ORDER = [
    "road_collapse", "flooding", "landslide", "trapped_person", "bridge_damage", "road_blocked",
    "fallen_tree", "building_damage", "fire", "gas_leak", "embankment_damage", "power_outage",
    "water_outage", "medical_need", "other",
]


def _ordered_union(seqs: list[tuple[str, ...]], order: list[str] | None = None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for seq in seqs:
        for v in seq:
            if v not in seen:
                seen.add(v)
                out.append(v)
    if order:
        out.sort(key=lambda v: order.index(v) if v in order else len(order))
    return out


def scenario_label(hazards: list[str] | tuple[str, ...]) -> str:
    if not hazards:
        return "災害"
    return "".join(hazard_label(h) for h in hazards[:2]) + ("等" if len(hazards) > 2 else "")


def compose_profile(
    hazards: list[str],
    county: str | None = None,
    towns: list[str] | None = None,
    *,
    mentioned_categories: list[str] | None = None,
) -> ScenarioProfile:
    """Deterministic composition. ``mentioned_categories`` are categories the
    brief explicitly mentioned; they are pinned to the top of the form."""
    hz = [h for h in hazards if h in HAZARDS] or []
    primary = hz[0] if hz else "generic"

    cat_seqs = [HAZARDS[h].report_categories for h in hz]
    if not cat_seqs:
        cat_seqs = [("road_blocked", "flooding", "trapped_person", "building_damage", "other")]
    cats = _ordered_union(cat_seqs, _FORM_ORDER)
    mentioned = [c for c in (mentioned_categories or []) if c in CATEGORIES]
    cats = mentioned + [c for c in cats if c not in mentioned]
    if "other" in cats:
        cats.remove("other")
    cats.append("other")

    layer_seqs = [HAZARDS[h].layers for h in hz]
    hazard_layers = _ordered_union(layer_seqs) if layer_seqs else ["road_damage", "shelter", "official_alert"]
    # core layers always on; hazard-driven layers only if a layer module exists
    base_layers = ["incident_cases", "report_clusters", "citizen_reports", "heatmap",
                   "government_processing"]
    layers = base_layers + [l for l in hazard_layers if l not in base_layers and registry.layer_by_key(l)]
    # the county-specific connectors only make sense for that county
    if county and "南投" not in county and "fire_station" in layers:
        layers.remove("fire_station")
    if "fire_station" not in layers and county and "南投" in county:
        layers.append("fire_station")

    # modules: every core module + default-enabled modules applicable to the hazards
    module_ids: list[str] = []
    reasons: list[dict] = []
    for spec in registry.all():
        if spec.module_type == "layer":
            continue
        if spec.core:
            module_ids.append(spec.id)
            reasons.append({"module_id": spec.id, "reason": "核心能力，平台運作所必需。"})
            continue
        if spec.default_enabled and spec.applies_to(hz or ["*"]):
            if spec.id == "nantou_open_data_connector" and not (county and "南投" in county):
                continue
            module_ids.append(spec.id)
            reasons.append({"module_id": spec.id, "reason": _reason_for(spec.id, hz)})
    # layers are modules too — add their module ids
    for layer_key in layers:
        spec = registry.layer_by_key(layer_key)
        if spec and spec.id not in module_ids:
            module_ids.append(spec.id)
            reasons.append({"module_id": spec.id, "reason": _layer_reason(layer_key, hz)})
            for dep in spec.dependencies:
                if dep not in module_ids and registry.get(dep):
                    module_ids.append(dep)

    return ScenarioProfile(
        hazards=tuple(hz),
        primary_hazard=primary,
        label=scenario_label(hz),
        county=county,
        towns=tuple(towns or ()),
        report_categories=tuple(
            {"key": c, "label": CATEGORIES[c].label, "default_severity": CATEGORIES[c].default_severity}
            for c in cats
        ),
        reporter_roles=tuple({"key": k, "label": v} for k, v in REPORTER_ROLES),
        layers=tuple(layers),
        modules=tuple(module_ids),
        reasons=tuple(reasons),
    )


_MODULE_REASONS: dict[str, str] = {
    "photo_upload": "現場照片是政府研判與公開透明的重要依據。",
    "reporter_role": "村里長、防災士與志工的回報需要被區分並加權。",
    "case_assignment": "需指定處理單位與帶隊人員，便於追蹤與稽核。",
    "trend_visualization": "判斷災情是否惡化需要時間趨勢。",
    "moi_shelter_connector": "提供避難收容處所位置。",
    "cwa_connector": "官方雨量與天氣特報是豪雨／颱風情境的核心資料。",
    "wra_connector": "河川水位與警戒水位對積淹水研判至關重要。",
    "nantou_open_data_connector": "南投縣政府開放資料提供在地消防單位點位。",
}

_LAYER_REASONS: dict[str, str] = {
    "flooding": "情境包含積淹水，需獨立圖層掌握淹水熱點。",
    "road_damage": "道路坍方／中斷直接影響救援路徑。",
    "landslide": "山區豪雨的土石流風險需獨立呈現。",
    "trapped_people": "人員受困永遠是最高優先。",
    "rainfall": "雨量是研判土石流與淹水的先行指標。",
    "water": "河川水位接近警戒值時需提前應變。",
    "shelter": "民眾需要知道最近的避難收容處所。",
    "fire_station": "在地消防單位位置協助派工與民眾求援。",
    "official_alert": "官方警戒讓民眾以政府公告為準。",
    "radar": "雷達回波回放讓民眾與指揮中心看見雨帶正往哪個鄉鎮移動。",
    "debris_flow": "山區豪雨最切題的官方圖層：潛勢溪流與即時紅黃警戒。",
    "landslide_zone": "大規模崩塌潛勢區讓通報落點有官方潛勢依據。",
    "road_traffic": "路況 CCTV 與封閉消息把「民眾說路斷了」升級成官方佐證。",
    "reservoir": "水庫蓄水率與洩洪狀態影響下游鄉鎮的應變。",
    "population": "鄉鎮人口讓派工順序能考慮受影響人數。",
    "power_outage": "計畫性停電公告避免把例行停電誤判為災情。",
    "building_damage": "建築損害與火災在此情境需獨立追蹤。",
    "lifeline": "停電停水影響範圍需要掌握。",
}


def _reason_for(module_id: str, hazards: list[str]) -> str:
    return _MODULE_REASONS.get(module_id, f"適用於{scenario_label(hazards)}情境。")


def _layer_reason(layer_key: str, hazards: list[str]) -> str:
    return _LAYER_REASONS.get(layer_key, f"{scenario_label(hazards)}情境建議啟用。")
