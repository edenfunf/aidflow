"""Agent planner — LLM understands, rules compose, humans approve, the
deterministic composer builds.

    plan    : brief → scenario analysis (AI, rules fallback) → suggested
              modules / layers / categories / cluster policy + a draft payload.
              Nothing is written.
    execute : the human-edited draft → platform_service.create_platform.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import settings
from app.domain.categories import CATEGORIES, REPORTER_ROLES, category_label
from app.domain.hazards import hazard_label
from app.modules import DOMAINS, registry
from app.modules.scenarios import compose_profile
from app.schemas.platform import ClusterPolicyInput, PlatformCreate
from app.services import ai_agent, official_data_service, outbox_service, platform_service, scenario_rules

_WORKFLOW = [
    {"step": "report", "label": "民眾通報", "detail": "表單送出後立即進入規則式分級與地理聚類。"},
    {"step": "cluster", "label": "同地點聚類", "detail": "相近類別、{radius} 公尺內、{window} 分鐘內的通報視為同一災點。"},
    {"step": "threshold", "label": "多人回報成案", "detail": "{n} 位不同回報者（同一人重複不計）即自動建立正式案件。"},
    {"step": "dispatch", "label": "縣府確認與派工", "detail": "後台指定處理單位，公開端即時顯示「已派員」。"},
    {"step": "progress", "label": "處理進度", "detail": "前往中→人員抵達→處理中→完成，每一步都寫入公開時間軸。"},
    {"step": "close", "label": "結案與稽核", "detail": "所有操作進入事件稽核軌跡。"},
]


def _merge(rules: dict, ai: dict | None) -> tuple[dict, str]:
    if ai is None:
        return rules, "rules"
    merged = dict(rules)
    for key in ("county", "name", "summary"):
        if ai.get(key):
            merged[key] = ai[key]
    for key in ("towns", "hazards", "impacts", "reporter_roles"):
        if ai.get(key):
            merged[key] = list(dict.fromkeys(list(ai[key]) + [v for v in rules.get(key, []) if v not in ai[key]]))
    if merged.get("county") != rules.get("county"):
        # county changed → towns from rules may be wrong; recompute
        merged["towns"] = scenario_rules.detect_towns(rules.get("_text", ""), merged.get("county")) or merged["towns"]
    merged["data_needs"] = scenario_rules.data_needs(merged["impacts"], merged["hazards"])
    if not ai.get("name"):
        merged["name"] = scenario_rules.suggest_name(merged["county"], merged["towns"], merged["hazards"])
    if not ai.get("summary"):
        merged["summary"] = scenario_rules.summarize(
            merged["county"], merged["towns"], merged["hazards"], merged["impacts"], merged["reporter_roles"]
        )
    return merged, "ai"


def _cluster_policy(analysis: dict, text: str) -> tuple[ClusterPolicyInput, list[str]]:
    base = settings.default_cluster_policy
    reasons: list[str] = []
    radius = base["radius_meters"]
    window = base["time_window_minutes"]
    required = base["required_unique_reporters"]
    if "landslide" in analysis["hazards"] or analysis.get("towns") and any(
        t in ("仁愛鄉", "信義鄉") for t in analysis["towns"]
    ):
        radius = max(radius, 150)
        reasons.append("山區 GPS 誤差較大，聚類半徑建議放寬至 150 公尺。")
    if "trapped_person" in analysis["impacts"]:
        reasons.append("人員受困類別由分級引擎直接提升為高風險，不受成案門檻影響。")
    if any(w in text for w in ("偏遠", "部落", "交通中斷")):
        window = max(window, 120)
        reasons.append("偏遠地區通訊可能延遲，時間窗建議放寬至 120 分鐘。")
    reasons.append(f"同地點需 {required} 位不同回報者才成案；同一人重複送出只計一次。")
    return ClusterPolicyInput(
        required_unique_reporters=required, radius_meters=radius, time_window_minutes=window,
        count_anonymous_reporters=True,
    ), reasons


def plan(db: Session, message: str) -> dict:
    rules = scenario_rules.parse_brief(message)
    rules["_text"] = message
    ai = ai_agent.parse_scenario(message)
    analysis, mode = _merge(rules, ai)
    hazards = analysis["hazards"] or ["flood"]
    if not analysis["hazards"]:
        analysis["hazards"] = hazards
    profile = compose_profile(hazards, analysis["county"], analysis["towns"], mentioned_categories=analysis["impacts"])
    reason_by_module = {r["module_id"]: r["reason"] for r in profile.reasons}

    suggested_modules = []
    for spec in registry.all():
        if spec.module_type == "layer":
            continue
        recommended = spec.id in profile.modules
        suggested_modules.append({
            "id": spec.id, "name": spec.name, "description": spec.description, "domain": spec.domain,
            "domain_label": DOMAINS.get(spec.domain, spec.domain), "module_type": spec.module_type,
            "recommended": recommended, "core": spec.core, "implemented": spec.implemented,
            "reason": reason_by_module.get(spec.id) or ("此情境非必要，可手動啟用。" if spec.implemented else "規劃中。"),
        })
    suggested_layers = []
    for spec in registry.layers():
        live = None
        if spec.source and spec.source in official_data_service.CONNECTORS:
            live = official_data_service.CONNECTORS[spec.source].live_enabled()
        suggested_layers.append({
            "key": spec.layer_key, "module_id": spec.id, "name": spec.name, "description": spec.description,
            "recommended": spec.layer_key in profile.layers, "core": spec.core, "source": spec.source, "live": live,
            "reason": reason_by_module.get(spec.id) or "此情境非必要，可手動啟用。",
        })
    recommended_cats = [c["key"] for c in profile.report_categories]
    suggested_categories = [
        {"key": c.key, "label": c.label, "default_severity": c.default_severity, "recommended": c.key in recommended_cats}
        for c in sorted(CATEGORIES.values(), key=lambda c: recommended_cats.index(c.key) if c.key in recommended_cats else 99)
    ]
    policy, policy_reasons = _cluster_policy(analysis, message)
    workflow = [
        {**w, "detail": w["detail"].format(
            radius=policy.radius_meters, window=policy.time_window_minutes, n=policy.required_unique_reporters)}
        for w in _WORKFLOW
    ]
    hz_labels = [hazard_label(h) for h in hazards]
    reasons = [
        f"偵測到災害類型：{'、'.join(hz_labels)}；依此啟用 {len(profile.layers)} 個地圖圖層。",
        f"通報表單只顯示 {len(recommended_cats)} 個相關災情類別："
        + "、".join(category_label(c) for c in recommended_cats[:6]) + ("…" if len(recommended_cats) > 6 else "") + "。",
        *policy_reasons,
    ]
    if analysis["county"] and "南投" in analysis["county"]:
        reasons.append("地區為南投縣：啟用南投縣政府開放資料（消防單位）與消防署避難收容處所圖層。")
    unavailable = [l["name"] for l in suggested_layers if l["recommended"] and l["live"] is False]
    if unavailable:
        reasons.append("尚未設定金鑰的官方圖層（" + "、".join(unavailable) + "）會以「暫無資料」呈現，不影響平台建立。")

    draft = PlatformCreate(
        name=analysis["name"],
        brief=message,
        hazards=hazards,
        county=analysis["county"],
        towns=analysis["towns"],
        modules=list(profile.modules),
        layers=list(profile.layers),
        report_categories=recommended_cats,
        cluster_policy=policy,
        publish=True,
    )
    outbox_service.enqueue_event(
        db, event_type="agent.planned", aggregate_id=None,
        payload={"intent_mode": mode, "county": analysis["county"], "hazards": hazards,
                 "modules": len(profile.modules), "layers": list(profile.layers)},
    )
    db.commit()
    role_labels = dict(REPORTER_ROLES)
    return {
        "scenario": {
            "region": {"county": analysis["county"], "towns": analysis["towns"]},
            "hazards": hazards,
            "hazard_labels": hz_labels,
            "impacts": analysis["impacts"],
            "impact_labels": [category_label(c) for c in analysis["impacts"]],
            "reporter_roles": analysis["reporter_roles"],
            "data_needs": analysis["data_needs"],
            "summary": analysis["summary"],
        },
        "suggested_name": analysis["name"],
        "suggested_modules": suggested_modules,
        "suggested_layers": suggested_layers,
        "suggested_report_categories": suggested_categories,
        "suggested_cluster_policy": policy,
        "suggested_workflow": workflow,
        "reasons": reasons,
        "intent_mode": mode,
        "ai_enabled": ai_agent.is_enabled(),
        "note": None if mode == "ai" else (
            "AI 情境解析未啟用或不可用，已改用關鍵字規則分析；規劃結果仍可直接確認建立。"
        ),
        "draft": draft,
        "_role_labels": {k: role_labels.get(k, k) for k in analysis["reporter_roles"]},
    }


def execute(db: Session, payload: PlatformCreate) -> dict:
    platform = platform_service.create_platform(
        db,
        name=payload.name,
        brief=payload.brief,
        hazards=payload.hazards,
        county=payload.county,
        towns=payload.towns,
        modules=payload.modules,
        layers=payload.layers,
        report_categories=payload.report_categories,
        cluster_policy=payload.cluster_policy.model_dump() if payload.cluster_policy else None,
        configuration=payload.configuration,
        publish=payload.publish,
        source="agent",
        slug=payload.slug,
    )
    outbox_service.enqueue_event(
        db, event_type="agent.executed", aggregate_id=platform.id,
        payload={"platform_id": str(platform.id), "slug": platform.slug,
                 "modules": len(platform.modules or []), "layers": len(platform.layers or [])},
    )
    db.commit()
    # demonstrations should not leave a trail of test platforms behind
    retired = platform_service.prune_generated(db)
    return {"platform": platform, "retired": retired}
