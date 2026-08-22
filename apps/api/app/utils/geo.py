"""Geo helpers: distance, centroids, Taiwan coordinate conversion.

Everything here is pure math so the clustering engine and the connector
normalizers are unit-testable offline.
"""
from __future__ import annotations

import math

EARTH_RADIUS_M = 6_371_008.8


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def bbox_for(lat: float, lon: float, radius_m: float) -> tuple[float, float, float, float]:
    """(min_lat, min_lon, max_lat, max_lon) — a cheap pre-filter before haversine."""
    dlat = radius_m / 111_320.0
    dlon = radius_m / (111_320.0 * max(math.cos(math.radians(lat)), 1e-6))
    return lat - dlat, lon - dlon, lat + dlat, lon + dlon


def round_coord(value: float, decimals: int = 3) -> float:
    """Coarsen a coordinate for public output (3 decimals ≈ 110 m)."""
    return round(value, decimals)


# ── TWD97 (TM2, central meridian 121°E) → WGS84 ──────────────────────────
# WRA publishes station positions as TWD97 easting/northing. Standard inverse
# Transverse Mercator on the GRS80 ellipsoid (TWD97 uses GRS80; the datum
# shift to WGS84 is negligible at map scale).
_A = 6378137.0
_F = 1 / 298.257222101
_K0 = 0.9999
_DX = 250_000.0
_LON0 = math.radians(121.0)
_E2 = 2 * _F - _F * _F
_EP2 = _E2 / (1 - _E2)


def twd97_to_wgs84(x: float, y: float) -> tuple[float, float]:
    """Return (lat, lon) in degrees for TWD97 TM2 (x=easting, y=northing)."""
    x = x - _DX
    m = y / _K0
    mu = m / (_A * (1 - _E2 / 4 - 3 * _E2**2 / 64 - 5 * _E2**3 / 256))
    e1 = (1 - math.sqrt(1 - _E2)) / (1 + math.sqrt(1 - _E2))
    j1 = 3 * e1 / 2 - 27 * e1**3 / 32
    j2 = 21 * e1**2 / 16 - 55 * e1**4 / 32
    j3 = 151 * e1**3 / 96
    j4 = 1097 * e1**4 / 512
    fp = mu + j1 * math.sin(2 * mu) + j2 * math.sin(4 * mu) + j3 * math.sin(6 * mu) + j4 * math.sin(8 * mu)

    c1 = _EP2 * math.cos(fp) ** 2
    t1 = math.tan(fp) ** 2
    r1 = _A * (1 - _E2) / (1 - _E2 * math.sin(fp) ** 2) ** 1.5
    n1 = _A / math.sqrt(1 - _E2 * math.sin(fp) ** 2)
    d = x / (n1 * _K0)

    q1 = n1 * math.tan(fp) / r1
    q2 = d**2 / 2
    q3 = (5 + 3 * t1 + 10 * c1 - 4 * c1**2 - 9 * _EP2) * d**4 / 24
    q4 = (61 + 90 * t1 + 298 * c1 + 45 * t1**2 - 3 * c1**2 - 252 * _EP2) * d**6 / 720
    lat = fp - q1 * (q2 - q3 + q4)

    q5 = d
    q6 = (1 + 2 * t1 + c1) * d**3 / 6
    q7 = (5 - 2 * c1 + 28 * t1 - 3 * c1**2 + 8 * _EP2 + 24 * t1**2) * d**5 / 120
    lon = _LON0 + (q5 - q6 + q7) / math.cos(fp)
    return math.degrees(lat), math.degrees(lon)


def parse_twd97_xy(text: str | None) -> tuple[float, float] | None:
    """'310928.30 2790168.45' (or comma separated) -> (lat, lon) or None."""
    if not text:
        return None
    parts = text.replace(",", " ").split()
    if len(parts) != 2:
        return None
    try:
        x, y = float(parts[0]), float(parts[1])
    except ValueError:
        return None
    if not (100_000 < x < 400_000 and 2_400_000 < y < 2_900_000):
        return None
    lat, lon = twd97_to_wgs84(x, y)
    return round(lat, 6), round(lon, 6)


# ── administrative centroids ──────────────────────────────────────────────
# (lat, lon) approximate centroids for Taiwan counties/cities.
COUNTY_CENTROIDS: dict[str, tuple[float, float]] = {
    "台北市": (25.03, 121.56),
    "新北市": (25.01, 121.46),
    "基隆市": (25.13, 121.74),
    "桃園市": (24.99, 121.30),
    "新竹市": (24.80, 120.97),
    "新竹縣": (24.70, 121.12),
    "苗栗縣": (24.56, 120.82),
    "台中市": (24.15, 120.68),
    "彰化縣": (24.05, 120.52),
    "南投縣": (23.91, 120.69),
    "雲林縣": (23.71, 120.43),
    "嘉義市": (23.48, 120.45),
    "嘉義縣": (23.46, 120.29),
    "台南市": (23.00, 120.20),
    "高雄市": (22.63, 120.30),
    "屏東縣": (22.55, 120.55),
    "宜蘭縣": (24.70, 121.74),
    "花蓮縣": (23.99, 121.60),
    "台東縣": (22.79, 121.11),
    "澎湖縣": (23.57, 119.58),
    "金門縣": (24.43, 118.32),
    "連江縣": (26.16, 119.95),
}

# Fallback map centre when a platform names neither a county nor a township.
TAIWAN_CENTER: tuple[float, float] = (23.75, 121.0)

# Every township in Taiwan, derived from official open data — see
# app/utils/town_centroids.py for the source and the regeneration command.
# Re-exported here so callers keep importing geo.TOWN_CENTROIDS.
from app.utils.town_centroids import TOWN_CENTROIDS  # noqa: E402


def normalize_admin(name: str | None) -> str:
    return (name or "").replace("臺", "台").strip()


def centroid_for(county: str | None, town: str | None = None) -> tuple[float, float] | None:
    """Best-known (lat, lon) for a county (+ optional town), or None."""
    c = normalize_admin(county)
    t = normalize_admin(town)
    if c in TOWN_CENTROIDS and t in TOWN_CENTROIDS[c]:
        return TOWN_CENTROIDS[c][t]
    return COUNTY_CENTROIDS.get(c)


def towns_of(county: str | None) -> list[str]:
    return list(TOWN_CENTROIDS.get(normalize_admin(county), {}).keys())


def mean_point(points: list[tuple[float, float]]) -> tuple[float, float]:
    n = len(points)
    if n == 0:
        raise ValueError("mean_point of empty list")
    return (sum(p[0] for p in points) / n, sum(p[1] for p in points) / n)


# ── polyline helpers (dispatch routes / vehicle simulation) ─────────────
def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing from point 1 to point 2, degrees clockwise from north."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def polyline_length_m(coords: list[list[float]]) -> float:
    """Length of a GeoJSON LineString ([lon, lat] pairs) in metres."""
    total = 0.0
    for (lon1, lat1), (lon2, lat2) in zip(coords, coords[1:]):
        total += haversine_m(lat1, lon1, lat2, lon2)
    return total


def point_along(coords: list[list[float]], dist_m: float) -> tuple[float, float, float]:
    """(lat, lon, heading) at ``dist_m`` along a [lon, lat] polyline; clamped
    to the ends."""
    if not coords:
        raise ValueError("empty polyline")
    if len(coords) == 1 or dist_m <= 0:
        lon, lat = coords[0]
        nxt = coords[1] if len(coords) > 1 else coords[0]
        return lat, lon, bearing_deg(lat, lon, nxt[1], nxt[0])
    walked = 0.0
    for (lon1, lat1), (lon2, lat2) in zip(coords, coords[1:]):
        seg = haversine_m(lat1, lon1, lat2, lon2)
        if seg <= 0:
            continue
        if walked + seg >= dist_m:
            t = (dist_m - walked) / seg
            return lat1 + (lat2 - lat1) * t, lon1 + (lon2 - lon1) * t, bearing_deg(lat1, lon1, lat2, lon2)
        walked += seg
    (lon1, lat1), (lon2, lat2) = coords[-2], coords[-1]
    return lat2, lon2, bearing_deg(lat1, lon1, lat2, lon2)


def simplify_line(coords: list[list[float]], tolerance_deg: float = 0.0004, max_points: int = 260) -> list[list[float]]:
    """Ramer–Douglas–Peucker in degree space (≈45 m at the default tolerance).

    A dispatch route from OSRM can carry 2,000 vertices — far more than any
    map scale shows, and the browser pays for every one of them on each poll.
    The shape is preserved; only redundant collinear points are dropped.
    """
    if len(coords) <= 2:
        return coords

    def rdp(points: list[list[float]], eps: float) -> list[list[float]]:
        if len(points) < 3:
            return points
        (x1, y1), (x2, y2) = points[0], points[-1]
        dx, dy = x2 - x1, y2 - y1
        norm = (dx * dx + dy * dy) ** 0.5
        worst, index = 0.0, 0
        for i in range(1, len(points) - 1):
            x, y = points[i]
            d = abs(dy * x - dx * y + x2 * y1 - y2 * x1) / norm if norm else ((x - x1) ** 2 + (y - y1) ** 2) ** 0.5
            if d > worst:
                worst, index = d, i
        if worst <= eps:
            return [points[0], points[-1]]
        return rdp(points[: index + 1], eps)[:-1] + rdp(points[index:], eps)

    out = rdp([list(c) for c in coords], tolerance_deg)
    # a pathological road can still exceed the cap: thin it evenly, keeping the ends
    while len(out) > max_points:
        step = max(2, round(len(out) / max_points))
        out = out[::step] + [out[-1]]
    return out
