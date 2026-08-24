"""Responders & dispatch (modules: case_dispatch, case_assignment).

- ``ensure_units``   : materialise the unit registry for a platform's county —
                       fire stations from open data (surveyed positions) plus
                       configured agencies (indicative positions).
- ``suggest``        : rank units for a case by the category→unit-kind rules,
                       distance and (for the top candidates) a real road route.
- ``dispatch``       : one click in the console: assignment + road route + ETA
                       + outbound notification (LINE / webhook / simulated) +
                       public timeline entry + audit event.
- ``vehicles``       : positions of responding vehicles. Real AVL pings win;
                       otherwise a clearly-labelled simulation moves vehicles
                       along the dispatch route from the unit's position,
                       derived purely from timestamps (no background worker).
"""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors import dispatch_channel, nantou_open_data, osrm
from app.connectors.base import ConnectorError
from app.core.config import settings
from app.db.models import CaseAssignment, IncidentCase, Platform, ResponderUnit, VehiclePosition
from app.domain.case_states import CaseStatus
from app.domain.responders import (
    AGENCIES_BY_COUNTY,
    UNIT_KIND_LABELS,
    VEHICLE_KIND_LABELS,
    responder_kinds,
    vehicles_for,
)
from app.services import case_service, media_service, outbox_service, privacy_service
from app.utils.geo import TOWN_CENTROIDS, centroid_for, haversine_m, normalize_admin, point_along, polyline_length_m, simplify_line


class UnitNotFoundError(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── unit registry ────────────────────────────────────────────────────────
def _upsert(db: Session, county: str, external_id: str, **fields) -> ResponderUnit:
    unit = db.scalar(select(ResponderUnit).where(ResponderUnit.county == county, ResponderUnit.external_id == external_id))
    if unit is None:
        unit = ResponderUnit(county=county, external_id=external_id, **fields)
        db.add(unit)
    else:
        for k, v in fields.items():
            if k in ("lat", "lon", "name", "kind", "address", "phone", "town", "location_source", "source"):
                setattr(unit, k, v)
    return unit


def ensure_units(db: Session, platform: Platform, *, refresh: bool = False) -> list[ResponderUnit]:
    county = normalize_admin(platform.county)
    if not county:
        return []
    existing = list(db.scalars(select(ResponderUnit).where(ResponderUnit.county == county, ResponderUnit.active.is_(True))).all())
    has_fire = any(u.kind == "fire" and u.location_source == "open_data" for u in existing)
    changed = False
    if "南投" in county and (refresh or not has_fire):
        try:
            for f in nantou_open_data.fetch_fire_stations():
                p = f["properties"]
                lon, lat = f["coordinates"]
                _upsert(db, county, f["id"], name=p["name"], kind="fire", lat=lat, lon=lon, address=p.get("address"),
                        phone=p.get("phone"), town=_town_of(county, lat, lon), location_source="open_data",
                        source="nantou_open_data")
                changed = True
        except ConnectorError:
            pass
    if refresh or not any(u.location_source == "indicative" for u in existing):
        for a in AGENCIES_BY_COUNTY.get(county, ()):
            ll = (a.lat, a.lon) if a.lat is not None and a.lon is not None else (centroid_for(county, a.town) or centroid_for(county))
            if ll is None:
                continue
            _upsert(db, county, f"agency:{a.name}", name=a.name, kind=a.kind, lat=ll[0], lon=ll[1], address=None,
                    phone=a.phone, town=a.town, location_source="configured" if a.lat is not None else "indicative",
                    source="configured")
            changed = True
    if changed:
        db.commit()
        existing = list(db.scalars(select(ResponderUnit).where(ResponderUnit.county == county, ResponderUnit.active.is_(True))).all())
    return existing


def _town_of(county: str, lat: float, lon: float) -> str | None:
    towns = TOWN_CENTROIDS.get(county, {})
    best = None
    for name, (tlat, tlon) in towns.items():
        d = haversine_m(lat, lon, tlat, tlon)
        if best is None or d < best[0]:
            best = (d, name)
    return best[1] if best else None


def unit_dict(u: ResponderUnit) -> dict:
    return {
        "id": u.id, "name": u.name, "kind": u.kind, "kind_label": UNIT_KIND_LABELS.get(u.kind, u.kind),
        "town": u.town, "lat": u.lat, "lon": u.lon, "address": u.address, "phone": u.phone,
        "location_source": u.location_source, "source": u.source,
    }


# ── route cache ──────────────────────────────────────────────────────────
_route_cache: dict[str, dict] = {}
_route_lock = threading.Lock()


def cached_route(from_lat: float, from_lon: float, to_lat: float, to_lon: float) -> dict:
    key = f"{from_lat:.4f},{from_lon:.4f}>{to_lat:.4f},{to_lon:.4f}"
    with _route_lock:
        hit = _route_cache.get(key)
    if hit:
        return hit
    r = osrm.route(from_lat, from_lon, to_lat, to_lon)
    with _route_lock:
        if len(_route_cache) > 2000:
            _route_cache.clear()
        _route_cache[key] = r
    return r


def clear_route_cache() -> None:
    with _route_lock:
        _route_cache.clear()


# ── suggestion ───────────────────────────────────────────────────────────
def suggest(db: Session, platform: Platform, case: IncidentCase, *, per_kind: int = 2, routed: int = 3) -> list[dict]:
    units = ensure_units(db, platform)
    kinds = responder_kinds(case.category)
    out: list[dict] = []
    for rank, kind in enumerate(kinds):
        pool = sorted((u for u in units if u.kind == kind), key=lambda u: haversine_m(u.lat, u.lon, case.lat, case.lon))
        for u in pool[:per_kind]:
            out.append({
                "unit": unit_dict(u), "kind_rank": rank, "primary": rank == 0,
                "straight_m": round(haversine_m(u.lat, u.lon, case.lat, case.lon)),
                "vehicles": [{"kind": v, "label": VEHICLE_KIND_LABELS[v]} for v in vehicles_for(kind, case.category)],
                "distance_m": None, "eta_minutes": None, "route_source": None, "route": None,
            })
    out.sort(key=lambda s: (s["kind_rank"], s["straight_m"]))
    for s in out[:routed]:
        r = cached_route(s["unit"]["lat"], s["unit"]["lon"], case.lat, case.lon)
        s["distance_m"] = r["distance_m"]
        s["eta_minutes"] = max(1, round(r["duration_s"] / 60 + settings.DISPATCH_PREP_MINUTES))
        s["route_source"] = r["source"]
        s["route"] = r["geometry"]
    return out


# ── dispatch ─────────────────────────────────────────────────────────────
def dispatch(
    db: Session,
    platform: Platform,
    case: IncidentCase,
    unit_id: uuid.UUID,
    *,
    note: str | None = None,
    actor_name: str | None = None,
    at: datetime | None = None,
    notify: bool = True,
) -> tuple[CaseAssignment, dict]:
    unit = db.get(ResponderUnit, unit_id)
    if unit is None or not unit.active:
        raise UnitNotFoundError()
    stamp = at or _now()
    r = cached_route(unit.lat, unit.lon, case.lat, case.lon)
    eta = max(1, round(r["duration_s"] / 60 + settings.DISPATCH_PREP_MINUTES))
    assignment = case_service.assign(
        db, case, unit_name=unit.name, team_lead=None, contact=unit.phone,
        note=note, actor_name=actor_name, at=at,
    )
    assignment.unit_id = unit.id
    assignment.route_geojson = r["geometry"]
    assignment.route_source = r["source"]
    assignment.distance_m = r["distance_m"]
    assignment.eta_minutes = eta
    assignment.vehicles = [
        {"vehicle_id": f"{unit.external_id}:{kind}:{i + 1}", "kind": kind}
        for i, kind in enumerate(vehicles_for(unit.kind, case.category))
    ]
    assignment.departed_at = stamp + timedelta(minutes=settings.DISPATCH_PREP_MINUTES)
    db.flush()

    result = {"channel": "none", "status": "skipped", "detail": "未發送通報", "external_ref": None}
    if notify:
        reports = case_service.reports_of(db, case.id)
        summary = [privacy_service.redact_text(r.description) or "" for r in reports if r.description][:5]
        photos = [media_service.public_url(p) for p in media_service.photos_for_case(db, case.id, public_only=True)]
        message = dispatch_channel.build_message(platform, case, unit, reports_summary=summary, photo_urls=photos)
        try:
            result = dispatch_channel.send(message, unit)
        except ConnectorError as exc:
            result = {"channel": "error", "status": "failed", "detail": exc.reason, "external_ref": None}
        assignment.notified_via = result["channel"]
        assignment.notified_at = stamp
        ch_label = {"line": "LINE 推播", "webhook": "出勤系統", "simulated": "模擬通報", "error": "通報失敗"}.get(result["channel"], result["channel"])
        case_service._event(  # noqa: SLF001 — same module family; keeps the event+outbox contract
            db, case, event_type="dispatch_notified", actor_role="operator", actor_name=actor_name,
            note=f"已通報{unit.name}（{ch_label}），預計 {eta} 分鐘抵達", public=True, at=stamp,
            payload={"unit_id": str(unit.id), "unit_name": unit.name, "channel": result["channel"],
                     "status": result["status"], "eta_minutes": eta, "distance_m": r["distance_m"],
                     "route_source": r["source"]},
        )
    outbox_service.enqueue_event(
        db, event_type="dispatch.created", aggregate_id=assignment.id,
        payload={"platform_id": str(platform.id), "case_id": str(case.id), "assignment_id": str(assignment.id),
                 "unit_id": str(unit.id), "unit_name": unit.name, "unit_kind": unit.kind,
                 "vehicles": assignment.vehicles, "eta_minutes": eta, "notified_via": assignment.notified_via},
    )
    db.flush()
    return assignment, result


# ── vehicles & routes ────────────────────────────────────────────────────
def _active_assignments(db: Session, platform: Platform) -> list[tuple[CaseAssignment, IncidentCase]]:
    rows = db.execute(
        select(CaseAssignment, IncidentCase)
        .join(IncidentCase, IncidentCase.id == CaseAssignment.case_id)
        .where(CaseAssignment.platform_id == platform.id, CaseAssignment.route_geojson.is_not(None),
               CaseAssignment.status.in_(("active", "completed")))
    ).all()
    return [(a, c) for a, c in rows]


def simulate_position(assignment: CaseAssignment, case: IncidentCase, now: datetime, *, index: int = 0,
                      loop: bool = False, elapsed_s: float | None = None) -> dict | None:
    """Deterministic vehicle position from timestamps only. None = vehicle is
    back at base (nothing to show). With ``loop`` (demo platforms) a vehicle
    whose case is still 已派員／前往中 replays the trip instead of parking, so a
    demo seeded hours ago still shows traffic on the road; the output is
    flagged ``replay`` and the UI labels it.

    ``elapsed_s`` (demo platforms only) is how long the *viewer* has had the
    page open. A demo seeded in the morning would otherwise have every vehicle
    parked at the scene by the afternoon — nothing left to watch. Anchoring the
    outbound leg to the viewer's own session means each page load starts the
    convoy at its station and lets it drive out. It never touches AVL data or a
    real platform, and it cannot move a case's state — only where the labelled
    simulated marker is drawn."""
    coords = (assignment.route_geojson or {}).get("coordinates") or []
    if len(coords) < 2 or assignment.departed_at is None:
        return None
    total = polyline_length_m(coords)
    speed = settings.VEHICLE_SIM_SPEED_KMH * 1000 / 3600  # m/s
    travel_s = total / speed if speed > 0 else 0
    depart = assignment.departed_at + timedelta(seconds=45 * index)
    if case.status in (CaseStatus.dismissed.value,) or assignment.status == "cancelled":
        return None
    done_at = case.resolved_at if case.status in (CaseStatus.resolved.value, CaseStatus.closed.value) else None
    if done_at is not None:
        back = (now - done_at).total_seconds()
        if back >= travel_s:
            return None
        dist = max(0.0, total - back * speed)  # returning along the same route
        lat, lon, heading = point_along(coords, dist)
        return {"lat": lat, "lon": lon, "heading": (heading + 180) % 360, "status": "returning", "progress": round(dist / total, 3) if total else 1.0, "eta_minutes": None}
    # seconds this vehicle has been under way; vehicles in a convoy leave 45 s apart
    if elapsed_s is None:
        under_way = (now - depart).total_seconds()
    else:
        under_way = elapsed_s - 45.0 * index
    if under_way < 0:
        lat, lon, heading = point_along(coords, 0)
        return {"lat": lat, "lon": lon, "heading": heading, "status": "preparing", "progress": 0.0,
                "eta_minutes": max(1, round((-under_way + travel_s) / 60))}
    dist = under_way * speed
    # vehicles park on the approach, a few tens of metres short of the incident
    # (and staggered), so they stay visible beside the case marker
    park_at = max(0.0, total - 35.0 - 14.0 * index)
    replay = False
    if loop and dist >= park_at and park_at > 0 and case.status in (CaseStatus.assigned.value, CaseStatus.en_route.value):
        dist = dist % park_at
        replay = True
    if dist >= park_at:
        lat, lon, heading = point_along(coords, park_at)
        return {"lat": lat, "lon": lon, "heading": heading, "status": "on_site", "progress": 1.0, "eta_minutes": 0}
    lat, lon, heading = point_along(coords, dist)
    return {"lat": lat, "lon": lon, "heading": heading, "status": "en_route", "progress": round(dist / total, 3),
            "eta_minutes": max(1, round((total - dist) / speed / 60)), "replay": replay}


def _avl_latest(db: Session, platform: Platform, now: datetime) -> dict[str, VehiclePosition]:
    since = now - timedelta(seconds=settings.AVL_STALE_SECONDS)
    rows = db.scalars(
        select(VehiclePosition)
        .join(ResponderUnit, ResponderUnit.id == VehiclePosition.unit_id, isouter=True)
        .where(VehiclePosition.recorded_at >= since)
        .order_by(VehiclePosition.recorded_at.desc())
    ).all()
    latest: dict[str, VehiclePosition] = {}
    county = normalize_admin(platform.county)
    for v in rows:
        if v.vehicle_id in latest:
            continue
        unit = db.get(ResponderUnit, v.unit_id) if v.unit_id else None
        if unit is not None and county and normalize_admin(unit.county) != county:
            continue
        latest[v.vehicle_id] = v
    return latest


def vehicles(db: Session, platform: Platform, *, public: bool, now: datetime | None = None,
             elapsed_s: float | None = None) -> list[dict]:
    now = now or _now()
    out: list[dict] = []
    avl = _avl_latest(db, platform, now)
    used_avl: set[str] = set()
    loop = bool(settings.VEHICLE_SIM_LOOP_DEMO and (platform.configuration or {}).get("demo"))
    # only a demo platform's *simulated* markers follow the viewer's session
    session_s = elapsed_s if loop else None
    for a, c in _active_assignments(db, platform):
        unit = db.get(ResponderUnit, a.unit_id) if a.unit_id else None
        for i, v in enumerate(a.vehicles or []):
            vid = v.get("vehicle_id") or f"{a.id}:{i}"
            kind = v.get("kind", "works_truck")
            ping = avl.get(vid)
            base = {
                "vehicle_id": vid, "kind": kind, "kind_label": VEHICLE_KIND_LABELS.get(kind, kind),
                "unit_name": unit.name if unit else a.unit_name, "unit_kind": unit.kind if unit else None,
                "case_id": str(c.id), "case_number": c.case_number, "case_title": c.title,
                "assignment_id": str(a.id), "route_source": a.route_source,
            }
            if ping is not None:
                used_avl.add(vid)
                out.append({**base, "lat": ping.lat if not public else privacy_service.public_coords(ping.lat, ping.lon)[0],
                            "lon": ping.lon if not public else privacy_service.public_coords(ping.lat, ping.lon)[1],
                            "heading": ping.heading, "status": "live", "progress": None, "eta_minutes": None,
                            "source": "avl", "recorded_at": ping.recorded_at.isoformat()})
                continue
            sim = simulate_position(a, c, now, index=i, loop=loop, elapsed_s=session_s)
            if sim is None:
                continue
            out.append({**base, **sim, "source": "simulated", "recorded_at": now.isoformat()})
    # AVL vehicles not tied to an assignment are still shown (fleet view)
    for vid, ping in avl.items():
        if vid in used_avl:
            continue
        unit = db.get(ResponderUnit, ping.unit_id) if ping.unit_id else None
        out.append({
            "vehicle_id": vid, "kind": ping.kind, "kind_label": VEHICLE_KIND_LABELS.get(ping.kind, ping.kind),
            "unit_name": unit.name if unit else None, "unit_kind": unit.kind if unit else None,
            "case_id": str(ping.case_id) if ping.case_id else None, "case_number": None, "case_title": None,
            "assignment_id": None, "route_source": None, "lat": ping.lat, "lon": ping.lon, "heading": ping.heading,
            "status": "live", "progress": None, "eta_minutes": None, "source": "avl", "recorded_at": ping.recorded_at.isoformat(),
        })
    return out


def _slim(geometry: dict | None) -> dict | None:
    """Routes are polled every 20 s by every open map: send the shape, not
    every OSRM vertex."""
    if not geometry or geometry.get("type") != "LineString":
        return geometry
    coords = geometry.get("coordinates") or []
    return {**geometry, "coordinates": simplify_line(coords)}


def routes(db: Session, platform: Platform, *, public: bool) -> dict:
    feats = []
    for a, c in _active_assignments(db, platform):
        if c.status in (CaseStatus.closed.value, CaseStatus.dismissed.value):
            continue
        if c.status == CaseStatus.resolved.value and c.resolved_at and (_now() - c.resolved_at) > timedelta(hours=2):
            continue
        feats.append({
            "type": "Feature", "id": f"route:{a.id}", "geometry": _slim(a.route_geojson),
            "properties": {"assignment_id": str(a.id), "case_id": str(c.id), "case_number": c.case_number,
                           "unit_name": a.unit_name, "unit_kind": (db.get(ResponderUnit, a.unit_id).kind if a.unit_id else None),
                           "distance_m": a.distance_m, "eta_minutes": a.eta_minutes, "route_source": a.route_source,
                           "case_status": c.status, "vehicles": [v.get("kind") for v in (a.vehicles or [])]},
        })
    return {"type": "FeatureCollection", "features": feats, "generated_at": _now().isoformat()}


# ── AVL ingest ───────────────────────────────────────────────────────────
def ingest_avl(db: Session, items: list[dict]) -> int:
    n = 0
    for it in items:
        db.add(VehiclePosition(
            unit_id=it.get("unit_id"), vehicle_id=it["vehicle_id"], kind=it.get("kind") or "works_truck",
            lat=it["lat"], lon=it["lon"], heading=it.get("heading"), speed_kmh=it.get("speed_kmh"),
            case_id=it.get("case_id"), recorded_at=it.get("recorded_at") or _now(), payload=it.get("payload") or {},
        ))
        n += 1
    if n:
        outbox_service.enqueue_event(db, event_type="avl.ingested", aggregate_id=None, payload={"count": n})
    db.commit()
    return n
