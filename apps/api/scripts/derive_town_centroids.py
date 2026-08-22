"""Derive township anchor points from the MOI shelter open-data CSV.

Run from apps/api with the venv. Emits JSON: {county: {town: [lat, lon, n]}}.
"""
import collections, csv, io, json, statistics, sys

from app.connectors.base import http_get
from app.core.config import settings

resp = http_get(settings.MOI_SHELTER_CSV_URL, timeout=180)
text = resp.content.decode("utf-8-sig", errors="replace")
rows = list(csv.DictReader(io.StringIO(text)))
print("rows:", len(rows), file=sys.stderr)
print("cols:", list(rows[0].keys())[:12], file=sys.stderr)


def norm(v):
    return (v or "").replace("臺", "台").strip()


def split_admin(value):
    v = norm(value)
    for i, ch in enumerate(v):
        if ch in "縣市" and i >= 1:
            return v[: i + 1], v[i + 1:]
    return v, ""


buckets = collections.defaultdict(list)
for r in rows:
    c, t = split_admin(r.get("縣市及鄉鎮市區") or "")
    if not c or not t:
        continue
    try:
        lat, lon = float(r.get("緯度") or ""), float(r.get("經度") or "")
    except ValueError:
        continue
    if not (21.5 <= lat <= 26.5 and 118.0 <= lon <= 122.5):
        continue
    buckets[(c, t)].append((lat, lon))

out = collections.defaultdict(dict)
for (c, t), pts in sorted(buckets.items()):
    # median, not mean: immune to a single mis-keyed coordinate
    out[c][t] = [round(statistics.median(p[0] for p in pts), 4),
                 round(statistics.median(p[1] for p in pts), 4), len(pts)]
json.dump(out, open(sys.argv[1], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("counties:", len(out), "townships:", sum(len(v) for v in out.values()), file=sys.stderr)
