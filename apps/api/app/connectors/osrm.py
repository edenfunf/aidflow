"""OSRM routing connector (road routes for dispatch).

Default base is the public OSRM demo server (project-osrm.org), which is
documented and free for light use; point ``OSRM_BASE_URL`` at your own OSRM
for production. Failure falls back to a straight-line estimate — callers
receive ``source="straight_line"`` so the UI can say so.
"""
from __future__ import annotations

from app.connectors.base import ConnectorError, http_get_json
from app.core.config import settings
from app.utils.geo import haversine_m

SOURCE = "osrm"

# assumed average speed when we have to estimate (mountain roads, emergency)
_FALLBACK_KMH = 40.0


def straight_line(from_lat: float, from_lon: float, to_lat: float, to_lon: float) -> dict:
    dist = haversine_m(from_lat, from_lon, to_lat, to_lon)
    return {
        "source": "straight_line",
        "distance_m": round(dist),
        "duration_s": round(dist / (_FALLBACK_KMH * 1000 / 3600)),
        "geometry": {"type": "LineString", "coordinates": [[from_lon, from_lat], [to_lon, to_lat]]},
    }


def route(from_lat: float, from_lon: float, to_lat: float, to_lon: float) -> dict:
    """Driving route as GeoJSON LineString + distance/duration. Never raises."""
    if not settings.OSRM_BASE_URL:
        return straight_line(from_lat, from_lon, to_lat, to_lon)
    url = f"{settings.OSRM_BASE_URL.rstrip('/')}/route/v1/driving/{from_lon:.6f},{from_lat:.6f};{to_lon:.6f},{to_lat:.6f}"
    try:
        body = http_get_json(url, params={"overview": "full", "geometries": "geojson", "steps": "false"}, timeout=10)
        if body.get("code") != "Ok" or not body.get("routes"):
            raise ConnectorError(f"OSRM {body.get('code')}")
        r = body["routes"][0]
        geom = r.get("geometry") or {}
        coords = geom.get("coordinates") or []
        if len(coords) < 2:
            raise ConnectorError("OSRM empty geometry")
        return {
            "source": SOURCE,
            "distance_m": round(float(r.get("distance") or 0)),
            "duration_s": round(float(r.get("duration") or 0)),
            "geometry": {"type": "LineString", "coordinates": coords},
        }
    except Exception:  # noqa: BLE001 — routing is best-effort
        return straight_line(from_lat, from_lon, to_lat, to_lon)
