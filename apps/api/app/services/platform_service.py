"""Deterministic platform composer.

Given a human-approved selection (hazards, region, modules, layers, cluster
policy) this builds the Platform row and its PlatformModuleConfig rows. It
validates everything against the module registry, always includes the core
modules and pulls in declared dependencies, so a platform can never be
generated in a non-functional shape — regardless of what the planner (or a
human) asked for.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Platform, PlatformModuleConfig
from app.domain.hazards import HAZARDS, hazard_label
from app.modules import ModuleNotFoundError, registry
from app.modules.scenarios import compose_profile
from app.services import outbox_service
from app.services.cluster_service import policy_from_dict
from app.utils.geo import TAIWAN_CENTER, TOWN_CENTROIDS, centroid_for, mean_point, normalize_admin
from app.utils.slug import short_suffix, slugify


class PlatformNotFoundError(Exception):
    pass


class InvalidSelectionError(Exception):
    pass


def _unique_slug(db: Session, base: str) -> str:
    slug = slugify(base)
    if db.scalar(select(Platform.id).where(Platform.slug == slug)) is None:
        return slug
    return f"{slug}-{short_suffix()}"


def _slug_base(county: str | None, hazards: list[str], name: str) -> str:
    # ASCII-friendly slug: county romanisation table for the common cases
    roman = {
        "南投縣": "nantou", "花蓮縣": "hualien", "台東縣": "taitung", "屏東縣": "pingtung",
        "高雄市": "kaohsiung", "台南市": "tainan", "嘉義縣": "chiayi", "雲林縣": "yunlin",
        "彰化縣": "changhua", "台中市": "taichung", "苗栗縣": "miaoli", "新竹縣": "hsinchu",
        "桃園市": "taoyuan", "新北市": "newtaipei", "台北市": "taipei", "基隆市": "keelung",
        "宜蘭縣": "yilan",
    }
    parts = [roman.get((county or "").replace("臺", "台"), "")]
    parts += [h for h in hazards[:2]]
    base = "-".join(p for p in parts if p)
    return base or slugify(name)


def resolve_selection(
    *,
    hazards: list[str],
    county: str | None,
    towns: list[str],
    modules: list[str] | None,
    layers: list[str] | None,
) -> tuple[list[str], list[str]]:
    """Validate + complete a module/layer selection. Returns (module_ids,
    layer_keys) in registry order. Unknown ids raise InvalidSelectionError."""
    profile = compose_profile(hazards, county, towns)
    wanted_modules = list(modules) if modules is not None else list(profile.modules)
    wanted_layers = list(layers) if layers is not None else list(profile.layers)

    try:
        registry.validate_ids(wanted_modules)
    except ModuleNotFoundError as exc:
        raise InvalidSelectionError(str(exc)) from exc
    for key in wanted_layers:
        if registry.layer_by_key(key) is None:
            raise InvalidSelectionError(f"Unknown layer: {key}")

    selected: set[str] = set(wanted_modules) | set(registry.core_ids())
    for key in wanted_layers:
        selected.add(registry.layer_by_key(key).id)  # type: ignore[union-attr]
    # close over dependencies (bounded by registry size)
    changed = True
    while changed:
        changed = False
        for mid in list(selected):
            for dep in registry.require(mid).dependencies:
                if dep not in selected and registry.get(dep) is not None:
                    selected.add(dep)
                    changed = True
    ordered_modules = [m.id for m in registry.all() if m.id in selected]
    ordered_layers = [m.layer_key for m in registry.layers() if m.id in selected and m.layer_key]
    # keep the caller's layer ordering where given (first = drawn first)
    if wanted_layers:
        ordered_layers.sort(key=lambda k: wanted_layers.index(k) if k in wanted_layers else len(wanted_layers))
    return ordered_modules, ordered_layers


def create_platform(
    db: Session,
    *,
    name: str,
    brief: str | None,
    hazards: list[str],
    county: str | None,
    towns: list[str],
    modules: list[str] | None = None,
    layers: list[str] | None = None,
    report_categories: list[str] | None = None,
    cluster_policy: dict | None = None,
    configuration: dict | None = None,
    publish: bool = False,
    source: str = "agent",
    slug: str | None = None,
) -> Platform:
    hz = [h for h in hazards if h in HAZARDS]
    if not hz:
        raise InvalidSelectionError("At least one known hazard is required.")
    module_ids, layer_keys = resolve_selection(
        hazards=hz, county=county, towns=towns, modules=modules, layers=layers
    )
    profile = compose_profile(hz, county, towns, mentioned_categories=report_categories)
    scenario = profile.to_dict()
    if report_categories:
        # human-approved category list wins, but only known categories
        from app.domain.categories import CATEGORIES

        keys = [c for c in report_categories if c in CATEGORIES]
        if keys:
            if "other" not in keys:
                keys.append("other")
            scenario["report_categories"] = [
                {"key": k, "label": CATEGORIES[k].label, "default_severity": CATEGORIES[k].default_severity}
                for k in keys
            ]
    scenario["modules"] = module_ids
    scenario["layers"] = layer_keys

    policy = policy_from_dict(cluster_policy)
    centre = None
    town_points = [centroid_for(county, t) for t in towns]
    town_points = [p for p in town_points if p]
    if town_points:
        centre = mean_point(town_points)
    elif county:
        centre = centroid_for(county)
    centre = centre or TAIWAN_CENTER
    cfg = {
        "cluster_policy": policy.to_dict(),
        "map": {"center": [centre[0], centre[1]], "zoom": 11 if towns else 10},
        "hazard_labels": [hazard_label(h) for h in hz],
        **(configuration or {}),
    }

    platform = Platform(
        slug=_unique_slug(db, slug) if slug else _unique_slug(db, _slug_base(county, hz, name)),
        name=name,
        brief=brief,
        county=county,
        towns=towns,
        hazards=hz,
        primary_hazard=hz[0],
        scenario=scenario,
        status="published" if publish else "draft",
        modules=module_ids,
        layers=layer_keys,
        configuration=cfg,
        center_lat=centre[0],
        center_lon=centre[1],
        published_at=datetime.now(timezone.utc) if publish else None,
    )
    db.add(platform)
    db.flush()

    for mid in module_ids:
        spec = registry.require(mid)
        conf = dict(spec.default_config)
        if mid == "two_report_trigger":
            conf = policy.to_dict()
        db.add(PlatformModuleConfig(
            platform_id=platform.id, module_id=mid, module_type=spec.module_type, enabled=True, config=conf,
        ))
    db.flush()

    outbox_service.enqueue_event(
        db,
        event_type="platform.created",
        aggregate_id=platform.id,
        payload={
            "platform_id": str(platform.id),
            "slug": platform.slug,
            "name": platform.name,
            "hazards": hz,
            "county": county,
            "modules": module_ids,
            "layers": layer_keys,
            "source": source,
            "published": publish,
        },
    )
    db.commit()
    db.refresh(platform)
    return platform


def set_status(db: Session, platform: Platform, status: str) -> Platform:
    if status not in ("draft", "published", "archived"):
        raise InvalidSelectionError(f"Unknown platform status: {status}")
    platform.status = status
    if status == "published" and platform.published_at is None:
        platform.published_at = datetime.now(timezone.utc)
    outbox_service.enqueue_event(
        db, event_type=f"platform.{status}", aggregate_id=platform.id,
        payload={"platform_id": str(platform.id), "slug": platform.slug},
    )
    db.commit()
    db.refresh(platform)
    return platform


def update_configuration(
    db: Session, platform: Platform, *, name: str | None = None, cluster_policy: dict | None = None,
    configuration: dict | None = None,
) -> Platform:
    if name:
        platform.name = name
    cfg = dict(platform.configuration or {})
    if cluster_policy is not None:
        cfg["cluster_policy"] = policy_from_dict(cluster_policy).to_dict()
        row = db.scalar(select(PlatformModuleConfig).where(
            PlatformModuleConfig.platform_id == platform.id,
            PlatformModuleConfig.module_id == "two_report_trigger",
        ))
        if row is not None:
            row.config = cfg["cluster_policy"]
    if configuration:
        cfg.update(configuration)
    platform.configuration = cfg
    outbox_service.enqueue_event(
        db, event_type="platform.configured", aggregate_id=platform.id,
        payload={"platform_id": str(platform.id), "cluster_policy": cfg.get("cluster_policy")},
    )
    db.commit()
    db.refresh(platform)
    return platform


def get_platform(db: Session, platform_id: uuid.UUID) -> Platform | None:
    return db.get(Platform, platform_id)


def require_platform(db: Session, platform_id: uuid.UUID) -> Platform:
    p = db.get(Platform, platform_id)
    if p is None:
        raise PlatformNotFoundError()
    return p


def get_by_slug(db: Session, slug: str, *, published_only: bool = False) -> Platform | None:
    q = select(Platform).where(Platform.slug == slug)
    if published_only:
        q = q.where(Platform.status == "published")
    return db.scalar(q)


def list_platforms(
    db: Session, *, status: str | None = None, limit: int = 50, offset: int = 0
) -> tuple[list[Platform], int]:
    filters = []
    if status:
        filters.append(Platform.status == status)
    total = db.scalar(select(func.count()).select_from(Platform).where(*filters)) or 0
    rows = db.scalars(
        select(Platform).where(*filters).order_by(Platform.created_at.desc()).limit(limit).offset(offset)
    ).all()
    return list(rows), int(total)


def module_configs(db: Session, platform_id: uuid.UUID) -> list[PlatformModuleConfig]:
    return list(db.scalars(
        select(PlatformModuleConfig).where(PlatformModuleConfig.platform_id == platform_id)
    ).all())


def has_module(platform: Platform, module_id: str) -> bool:
    return module_id in (platform.modules or [])


def public_config(platform: Platform) -> dict:
    """What the public portal needs to render itself. No internal config."""
    scenario = platform.scenario or {}
    cfg = platform.configuration or {}
    return {
        "id": str(platform.id),
        "slug": platform.slug,
        "name": platform.name,
        "status": platform.status,
        "county": platform.county,
        "towns": platform.towns or [],
        "hazards": platform.hazards or [],
        "hazard_labels": cfg.get("hazard_labels", []),
        "primary_hazard": platform.primary_hazard,
        "report_categories": scenario.get("report_categories", []),
        "reporter_roles": scenario.get("reporter_roles", []),
        "modules": platform.modules or [],
        "layers": platform.layers or [],
        "map": cfg.get("map", {"center": [platform.center_lat, platform.center_lon], "zoom": 10}),
        # township reference points (town-hall area) — used by the portal for
        # labels and as the *indicative* origin of non-fire dispatch arcs
        "town_centers": {
            t: {"lat": ll[0], "lon": ll[1]}
            for t, ll in TOWN_CENTROIDS.get(normalize_admin(platform.county), {}).items()
            if not platform.towns or t in platform.towns
        },
        "cluster_policy": {
            # the rule itself is public information (transparency), not PII
            "required_unique_reporters": (cfg.get("cluster_policy") or {}).get("required_unique_reporters"),
            "radius_meters": (cfg.get("cluster_policy") or {}).get("radius_meters"),
            "time_window_minutes": (cfg.get("cluster_policy") or {}).get("time_window_minutes"),
        },
        "contacts": cfg.get("contacts", [
            {"name": "消防救護", "phone": "119"},
            {"name": "警察", "phone": "110"},
            {"name": "災害通報專線", "phone": "1991"},
        ]),
        "published_at": platform.published_at.isoformat() if platform.published_at else None,
    }


def prune_generated(db: Session, *, keep: int | None = None) -> list[str]:
    """Keep the workspace clean between demonstrations.

    Everything the generator produced is disposable: only the newest ``keep``
    survive, and the built-in 南投 demo platform (the one carrying a
    ``demo_key``) is never touched. Returns the slugs that were removed.
    """
    if not settings.DEMO_MODE:
        return []
    limit = settings.DEMO_KEEP_GENERATED if keep is None else keep
    if limit < 0:
        return []
    rows = list(db.scalars(select(Platform).order_by(Platform.created_at.desc())).all())
    disposable = [p for p in rows if not (p.configuration or {}).get("demo_key")]
    removed: list[str] = []
    for p in disposable[limit:]:
        removed.append(p.slug)
        db.delete(p)
    if removed:
        db.commit()
    return removed
