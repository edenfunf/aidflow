"""Demo scenario: 南投縣豪雨／土石流災情 (gated by DEMO_MODE).

Builds the platform through the real composer and then replays a consistent
story through the *real* report → cluster → case → review → EMIC / community
pipeline with back-dated timestamps. Nothing is written directly into the case
tables, so every timeline shown in the demo is produced by the same code that
runs in production. Idempotent: re-running without ``force`` is a no-op.
"""
from __future__ import annotations

import math

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Platform
from app.schemas.report import ReportCreate
from app.services import case_service, platform_service, report_service
from app.utils.geo import COUNTY_CENTROIDS, TOWN_CENTROIDS, haversine_m, normalize_admin

DEMO_KEY = "nantou-2026-heavy-rain"
# stable public URL for the demo: /p/nantou-heavy-rain-demo (force re-seed replaces the
# previous demo platform instead of creating a new slug)
DEMO_SLUG = "nantou-heavy-rain-demo"
DEMO_NAME = "南投縣豪雨災情（示範）"
DEMO_HAZARDS = ["typhoon", "heavy_rain", "landslide", "flood"]
DEMO_TOWNS = ["仁愛鄉", "信義鄉", "埔里鎮", "國姓鄉", "水里鄉"]
OFFICER = "縣府值班承辦"


def _r(category: str, lat: float, lon: float, desc: str, role: str, key: str, *, addr: str | None = None,
       severity: str | None = None, name: str | None = None, contact: str | None = None) -> dict:
    return {"category": category, "lat": lat, "lon": lon, "description": desc, "reporter_role": role,
            "client_key": key, "address": addr, "severity": severity, "reporter_name": name,
            "reporter_contact": contact}


# Each site: list of reports (minutes before "now" as `t`) + the county's
# handling of the case (minutes before now for each step):
#   ("review", emic|community|dismiss, t)   審核點
#   ("emic", {no, status, unit}, t)          登錄 EMIC 案號／狀態／處理單位
#   ("status", to_status, t)                 狀態轉換
#   ("update", note, t)                      公開處理進度
#   ("community_done", note, t)              民眾回報已協助處理
#   ("confirm", approve, t)                  承辦確認民眾處理
SITES: list[dict] = [
    # ── 仁愛鄉 ────────────────────────────────────────────────────────────
    {"reports": [
        (_r("road_collapse", 24.0235, 121.1572, "台14甲線往清境方向路基掏空，單線無法通行，有落石持續掉落", "village_chief",
            "renai-chief-01", addr="南投縣仁愛鄉台14甲線 18K", name="王村長", contact="0912000101"), 470),
        (_r("road_collapse", 24.0238, 121.1576, "清境下方路段坍方，車子都卡在這裡", "citizen", "renai-cit-02",
            addr="南投縣仁愛鄉台14甲線清境農場下方"), 464),
        (_r("road_collapse", 24.0231, 121.1569, "坍方處約 30 公尺，土石還在滑動", "disaster_officer", "renai-dpo-03",
            addr="南投縣仁愛鄉台14甲線"), 455),
     ], "flow": [("review", "emic", 452),
                 ("emic", {"no": "EMIC-1150903-0012", "status": "已受理", "unit": "公路局中區養護工程分局埔里工務段"}, 446),
                 ("status", "emic_processing", 431),
                 ("update", "重機具進場清除土石，單線通行預計 2 小時後恢復", 380),
                 ("update", "單線恢復通行，實施交管", 330),
                 ("emic", {"status": "已處理完成"}, 290), ("status", "closed", 285)]},
    {"reports": [
        (_r("landslide", 24.0290, 121.1760, "廬山部落上方邊坡土石流下來，沖到產業道路", "village_chief", "renai-chief-11",
            addr="南投縣仁愛鄉精英村廬山部落", severity="high"), 210),
        (_r("landslide", 24.0287, 121.1755, "土石流把路封住了，部落出不去", "citizen", "renai-cit-12",
            addr="南投縣仁愛鄉精英村"), 203),
     ], "flow": [("review", "emic", 196),
                 ("emic", {"no": "EMIC-1150903-0031", "status": "處理中", "unit": "農業部農村發展及水土保持署南投分署"}, 190),
                 ("status", "emic_processing", 160),
                 ("update", "開設替代便道中，預計今晚前恢復聯外", 120)]},
    {"reports": [
        (_r("trapped_person", 23.9440, 121.1210, "親愛村有 3 戶共 7 人受困，聯外道路中斷，其中一位長者需洗腎", "village_chief",
            "renai-chief-21", addr="南投縣仁愛鄉親愛村", severity="critical", name="張村長", contact="0912000121"), 95),
        (_r("trapped_person", 23.9443, 121.1214, "親愛村萬大路段被土石蓋住，裡面還有人", "volunteer", "renai-vol-22",
            addr="南投縣仁愛鄉親愛村萬大路"), 88),
     ], "flow": [("review", "emic", 84),
                 ("emic", {"no": "EMIC-1150903-0047", "status": "已派員處理", "unit": "南投縣政府消防局第二大隊"}, 80),
                 ("status", "emic_processing", 52),
                 ("update", "消防人員已抵達，協助 7 人徒步撤離至親愛國小，洗腎長者後送中", 40)]},
    {"reports": [
        (_r("road_blocked", 23.9740, 121.1420, "萬大往曲冰路段有倒木擋住一半路面", "citizen", "renai-cit-31",
            addr="南投縣仁愛鄉投83線"), 33),
     ], "flow": []},
    {"reports": [
        (_r("flooding", 24.0215, 121.1335, "霧社街上排水不及，路面積水約 20 公分", "citizen", "renai-cit-41",
            addr="南投縣仁愛鄉大同村仁和路"), 18),
        # the same person sending twice must NOT count as two reporters
        (_r("flooding", 24.0216, 121.1336, "再補一次，水還在漲", "citizen", "renai-cit-41",
            addr="南投縣仁愛鄉大同村仁和路"), 12),
     ], "flow": []},
    # ── 信義鄉 ────────────────────────────────────────────────────────────
    {"reports": [
        (_r("road_collapse", 23.5540, 120.9270, "東埔往八通關步道入口前路基流失", "disaster_officer", "xinyi-dpo-01",
            addr="南投縣信義鄉東埔村開高巷"), 150),
        (_r("road_collapse", 23.5537, 120.9265, "東埔溫泉區聯外道路坍方，遊客無法下山", "community_org", "xinyi-org-02",
            addr="南投縣信義鄉東埔村"), 141),
     ], "flow": []},
    {"reports": [
        (_r("bridge_damage", 23.5604, 120.8746, "桐林橋橋墩被沖刷，橋面有裂縫", "village_chief", "xinyi-chief-11",
            addr="南投縣信義鄉同富村桐林橋", severity="high"), 62),
        (_r("bridge_damage", 23.5601, 120.8750, "桐林橋下游護坡掏空，建議封橋", "disaster_officer", "xinyi-dpo-12",
            addr="南投縣信義鄉同富村"), 55),
     ], "flow": []},
    {"reports": [
        (_r("landslide", 23.6500, 120.8400, "神木村出水溪土石流，淹到一樓", "village_chief", "xinyi-chief-21",
            addr="南投縣信義鄉神木村", severity="critical"), 540),
        (_r("landslide", 23.6497, 120.8404, "神木村土石流，有 2 戶需要撤離", "citizen", "xinyi-cit-22",
            addr="南投縣信義鄉神木村"), 536),
        (_r("trapped_person", 23.6502, 120.8398, "神木村一位阿嬤被困在二樓", "volunteer", "xinyi-vol-23",
            addr="南投縣信義鄉神木村"), 530),
     ], "flow": [("review", "emic", 526),
                 ("emic", {"no": "EMIC-1150903-0005", "status": "已派員處理", "unit": "南投縣政府消防局第三大隊"}, 522),
                 ("status", "emic_processing", 498),
                 ("update", "2 戶 5 人全數撤離至神木國小收容所", 470),
                 ("emic", {"status": "已處理完成"}, 420), ("status", "closed", 300)]},
    # ── 埔里鎮 ────────────────────────────────────────────────────────────
    {"reports": [
        (_r("flooding", 23.9620, 120.9650, "南門里中山路積水到小腿，機車騎不過去", "citizen", "puli-cit-01",
            addr="南投縣埔里鎮南門里中山路二段"), 125),
        (_r("flooding", 23.9624, 120.9655, "南門市場周邊淹水，店家在堆沙包", "citizen", "puli-cit-02",
            addr="南投縣埔里鎮南門里"), 121),
        (_r("flooding", 23.9617, 120.9647, "中山路與西安路口積水約 40 公分", "village_chief", "puli-chief-03",
            addr="南投縣埔里鎮南門里中山路", name="李里長", contact="0933000103"), 118),
        (_r("flooding", 23.9622, 120.9652, "水淹進一樓，家裡有長輩", "citizen", "puli-cit-04",
            addr="南投縣埔里鎮南門里中山路二段 120 號"), 110),
     ], "flow": [("review", "emic", 104),
                 ("emic", {"no": "EMIC-1150903-0039", "status": "處理中", "unit": "埔里鎮公所"}, 100),
                 ("status", "emic_processing", 86),
                 ("update", "抽水機 2 台進場抽水，水位已下降", 45)]},
    {"reports": [
        (_r("flooding", 23.9720, 120.9450, "愛蘭台地下方道路積水", "citizen", "puli-cit-11",
            addr="南投縣埔里鎮愛蘭里"), 600),
        (_r("flooding", 23.9723, 120.9454, "愛蘭橋頭積水，車輛拋錨", "volunteer", "puli-vol-12",
            addr="南投縣埔里鎮愛蘭里"), 592),
     ], "flow": [("review", "community", 585),
                 ("community_done", "已清除排水孔落葉，路面積水已退", 560),
                 ("confirm", True, 540)]},
    {"reports": [
        (_r("fallen_tree", 23.9580, 120.9720, "大城里中正路路樹倒塌擋住半邊車道", "citizen", "puli-cit-21",
            addr="南投縣埔里鎮大城里中正路"), 27),
        (_r("fallen_tree", 23.9582, 120.9722, "中正路有斷枝散落，機車要繞過", "citizen", "puli-cit-22",
            addr="南投縣埔里鎮大城里中正路"), 22),
     ], "flow": [("review", "community", 15)]},
    # ── 國姓鄉 ────────────────────────────────────────────────────────────
    {"reports": [
        (_r("road_blocked", 24.0600, 120.9000, "北港村投 80 線被落石封住", "village_chief", "guoxing-chief-01",
            addr="南投縣國姓鄉北港村投80線"), 70),
        (_r("road_blocked", 24.0604, 120.9004, "北港溪旁道路中斷，有落石", "citizen", "guoxing-cit-02",
            addr="南投縣國姓鄉北港村"), 63),
     ], "flow": [("review", "emic", 6)]},
    {"reports": [
        (_r("landslide", 24.0420, 120.8580, "國姓街後山邊坡滑動，土石到民宅後方", "citizen", "guoxing-cit-11",
            addr="南投縣國姓鄉國姓村"), 44),
        (_r("landslide", 24.0423, 120.8577, "邊坡崩塌，已通知住戶先撤", "disaster_officer", "guoxing-dpo-12",
            addr="南投縣國姓鄉國姓村中正路"), 39),
     ], "flow": []},
    # ── 水里鄉 ────────────────────────────────────────────────────────────
    {"reports": [
        (_r("flooding", 23.8120, 120.8550, "水里市區民權路積水", "citizen", "shuili-cit-01",
            addr="南投縣水里鄉水里村民權路"), 160),
        (_r("flooding", 23.8124, 120.8553, "民權路水淹到店門口", "community_org", "shuili-org-02",
            addr="南投縣水里鄉水里村"), 151),
     ], "flow": [("review", "community", 146),
                 ("community_done", "里民協助清除側溝堵塞，水已退", 96)]},
    {"reports": [
        (_r("bridge_damage", 23.8330, 120.8640, "車埕舊橋欄杆被沖走一段", "citizen", "shuili-cit-11",
            addr="南投縣水里鄉車埕村"), 20),
     ], "flow": []},
    # an anonymous report without coordinates (never clustered)
    {"reports": [
        ({"category": "other", "description": "山上訊號不好，麻煩多派人來看", "reporter_role": "citizen",
          "client_key": None, "lat": None, "lon": None, "address": None, "severity": None,
          "reporter_name": None, "reporter_contact": None}, 8),
     ], "flow": []},
]


def _apply_flow(db: Session, platform: Platform, case, flow: list[tuple], now: datetime) -> None:
    for step in flow:
        kind = step[0]
        at = now - timedelta(minutes=step[-1])
        if kind == "review":
            case_service.review(db, platform, case, step[1], actor_name=OFFICER, at=at)
        elif kind == "emic":
            info = step[1]
            case_service.update_emic(db, case, actor_name=OFFICER, emic_case_no=info.get("no"),
                                     emic_status=info.get("status"), assigned_unit=info.get("unit"), at=at)
        elif kind == "status":
            case_service.transition(db, case, step[1], actor_role="operator", actor_name=OFFICER, at=at)
        elif kind == "update":
            case_service.add_update(db, case, note=step[1], public=True, actor_name="現場回報", at=at)
        elif kind == "community_done":
            case_service.community_submit(db, case, note=step[1], at=at)
        elif kind == "confirm":
            case_service.community_confirm(db, case, approve=step[1], actor_name=OFFICER, at=at)
        db.commit()


def find_demo_platform(db: Session) -> Platform | None:
    return db.scalar(
        select(Platform).where(Platform.configuration.op("@>")({"demo_key": DEMO_KEY}))
        .order_by(Platform.created_at.desc())
    )


def seed_nantou(db: Session, *, force: bool = False) -> dict:
    if not settings.DEMO_MODE:
        return {"enabled": False}
    existing = find_demo_platform(db)
    if existing is not None and not force:
        return {"seeded": False, "skipped": True, "platform_id": str(existing.id), "slug": existing.slug}
    if existing is not None:
        for old in db.scalars(select(Platform).where(Platform.configuration.op("@>")({"demo_key": DEMO_KEY}))).all():
            db.delete(old)  # cascades reports / clusters / cases / events / photos
        db.commit()

    platform = platform_service.create_platform(
        db, name=DEMO_NAME, brief=None, hazards=DEMO_HAZARDS, county="南投縣", towns=DEMO_TOWNS,
        configuration={"demo": True, "demo_key": DEMO_KEY, "case_prefix": "NT"}, publish=True, source="demo",
        slug=DEMO_SLUG,
    )
    reports, cases = _replay(db, platform, lambda lat, lon, addr: (lat, lon, addr))
    return {"seeded": True, "platform_id": str(platform.id), "slug": platform.slug,
            "reports": reports, "cases": cases}


def _replay(db: Session, platform: Platform, tf) -> tuple[int, int]:
    now = datetime.now(timezone.utc)
    reports = cases = 0
    for site in SITES:
        case = None
        for raw, minutes_ago in site["reports"]:
            lat, lon, addr = tf(raw["lat"], raw["lon"], raw.get("address"))
            payload = ReportCreate(**{**{k: v for k, v in raw.items() if k != "client_key"},
                                      "category": _category_for(platform, raw["category"]),
                                      "lat": lat, "lon": lon, "address": addr})
            report, _cluster, created = report_service.create_report(
                db, platform, payload, client_key=raw.get("client_key"), source="demo",
                created_at=now - timedelta(minutes=minutes_ago), notify=False,
            )
            reports += 1
            if created is not None:
                case = created
                cases += 1
            elif report.case_id and case is None:
                case = case_service.get_case(db, report.case_id)
        if case is not None:
            _apply_flow(db, platform, case, site["flow"], now)
    db.commit()
    return reports, cases


# ── seed the same story into a platform the operator just created ─────────
# Used by the console's 「帶入示範資料」 button: the Nantou sites are replayed
# through the real pipeline against *this* platform. Outside Nantou the
# sites are shifted to the platform's county and its townships, and
# categories the platform does not offer fall back to the nearest enabled
# one — so any freshly created platform can be demonstrated in one click.
_CATEGORY_FALLBACK: dict[str, tuple[str, ...]] = {
    "road_collapse": ("road_blocked", "landslide", "other"),
    "road_blocked": ("road_collapse", "fallen_tree", "other"),
    "landslide": ("road_collapse", "building_damage", "other"),
    "flooding": ("embankment_damage", "road_blocked", "other"),
    "bridge_damage": ("road_collapse", "road_blocked", "other"),
    "trapped_person": ("medical_need", "building_damage", "other"),
    "fallen_tree": ("road_blocked", "power_outage", "other"),
    "embankment_damage": ("flooding", "other"),
    "medical_need": ("trapped_person", "other"),
    "building_damage": ("other",),
}


def _category_for(platform: Platform, category: str) -> str:
    allowed = report_service.allowed_categories(platform)
    if category in allowed:
        return category
    for alt in _CATEGORY_FALLBACK.get(category, ()):
        if alt in allowed:
            return alt
    return "other" if "other" in allowed else allowed[0]


# Each demo site belongs to one 南投 township. Translating a site means moving
# it onto a *real* township of the target county — a township anchor derived
# from official shelter locations, so it is always habitable land — and keeping
# the site's own offset from its source township. That preserves the layout
# (and therefore the clustering behaviour) without ever landing in the sea,
# which a single county-wide offset does the moment the target county is a
# narrow coastal strip.
NANTOU_TOWNS = ["仁愛鄉", "信義鄉", "埔里鎮", "國姓鄉", "水里鄉"]

# Bounds for how far a translated point may sit from its township anchor.
# 仁愛鄉 and 信義鄉 are vast mountain townships; carrying their full internal
# spread onto a compact urban district — or onto a small island — would put
# points outside it. The actual cap is derived per county from how far apart
# that county's townships are (see _offset_cap_m).
MIN_OFFSET_CAP_M = 1_500.0
MAX_OFFSET_CAP_M = 6_000.0

_M_PER_DEG_LAT = 111_320.0


def _m_per_deg_lon(at_lat: float) -> float:
    return _M_PER_DEG_LAT * max(math.cos(math.radians(at_lat)), 1e-6)


def _town_of_address(addr: str | None) -> str | None:
    for town in NANTOU_TOWNS:
        if addr and town in addr:
            return town
    return None


def _offset_cap_m(anchors: dict[str, tuple[float, float]]) -> float:
    """How much room a county has: half the typical gap between its townships.

    澎湖's townships sit a couple of kilometres apart, 花蓮's tens of
    kilometres. Sizing the cap off the county's own geometry keeps points
    inside small island townships without needlessly squashing large ones.
    """
    points = list(anchors.values())
    if len(points) < 2:
        return MIN_OFFSET_CAP_M
    nearest: list[float] = []
    for i, a in enumerate(points):
        d = min(haversine_m(a[0], a[1], b[0], b[1]) for j, b in enumerate(points) if j != i)
        nearest.append(d)
    nearest.sort()
    typical = nearest[len(nearest) // 2]
    return max(MIN_OFFSET_CAP_M, min(MAX_OFFSET_CAP_M, typical / 2))


def _township_scales(cap_m: float, src_towns: dict[str, tuple[float, float]]) -> dict[str, float]:
    """One shrink factor per source township, so relative layout is preserved.

    Clamping each point independently would collapse a township's sites onto a
    single circle — distinct incidents 800 m apart ended up 97 m apart. Scaling
    the whole township by one factor keeps them proportionally separated.
    """
    worst: dict[str, float] = {}
    for site in SITES:
        for raw, _ in site["reports"]:
            lat, lon = raw.get("lat"), raw.get("lon")
            if lat is None or lon is None:
                continue
            town = _town_of_address(raw.get("address"))
            anchor = src_towns.get(town) if town else None
            if anchor is None:
                continue
            d = haversine_m(anchor[0], anchor[1], lat, lon)
            worst[town] = max(worst.get(town, 0.0), d)
    return {t: (1.0 if d <= cap_m or d == 0 else cap_m / d) for t, d in worst.items()}


def _site_transform(platform: Platform):
    """(lat, lon, addr) → values that actually fall inside the platform's county.

    Returns the identity for 南投 (the demo's home county) and whenever the
    target county has no township reference data to move onto.
    """
    county = normalize_admin(platform.county)
    if not county or "南投" in county:
        return lambda lat, lon, addr: (lat, lon, addr)
    src_towns = TOWN_CENTROIDS.get("南投縣") or {}
    dst_towns = TOWN_CENTROIDS.get(county) or {}
    if not src_towns or not dst_towns:
        return lambda lat, lon, addr: (lat, lon, addr)

    # prefer the townships the platform actually declared; otherwise spread the
    # demo across the county's own townships, in a stable order
    preferred = [t for t in (platform.towns or []) if t in dst_towns]
    pool = preferred or sorted(dst_towns)
    mapping = {t: pool[i % len(pool)] for i, t in enumerate(NANTOU_TOWNS)}
    cap = _offset_cap_m(dst_towns)
    scales = _township_scales(cap, src_towns)

    def tf(lat: float | None, lon: float | None, addr: str | None):
        source_town = _town_of_address(addr)
        target_town = mapping.get(source_town) if source_town else None

        new_addr = addr
        if addr:
            new_addr = addr.replace("南投縣", county)
            if source_town and target_town:
                new_addr = new_addr.replace(source_town, target_town)

        # one demo report deliberately carries no coordinates (it exercises the
        # "no location" path): there is nothing to shift
        if lat is None or lon is None:
            return (lat, lon, new_addr)

        if not source_town or not target_town:
            # no township to hang it on — fall back to the county centre
            src_c, dst_c = COUNTY_CENTROIDS.get("南投縣"), COUNTY_CENTROIDS.get(county)
            if not src_c or not dst_c:
                return (lat, lon, new_addr)
            s_lat, s_lon, d_lat, d_lon, k = src_c[0], src_c[1], dst_c[0], dst_c[1], 0.3
        else:
            s_lat, s_lon = src_towns[source_town]
            d_lat, d_lon = dst_towns[target_town]
            k = scales.get(source_town, 1.0)

        # scale in metres, not degrees, so the shape survives the latitude change
        dy = (lat - s_lat) * _M_PER_DEG_LAT * k
        dx = (lon - s_lon) * _m_per_deg_lon(s_lat) * k
        return (round(d_lat + dy / _M_PER_DEG_LAT, 5),
                round(d_lon + dx / _m_per_deg_lon(d_lat), 5),
                new_addr)

    return tf


def seed_into_platform(db: Session, platform: Platform, *, replace: bool = False) -> dict:
    from app.db.models import IncidentCase, Report, ReportCluster

    if replace:
        for model in (IncidentCase, ReportCluster, Report):
            for row in db.scalars(select(model).where(model.platform_id == platform.id)).all():
                db.delete(row)
        db.commit()
    reports, cases = _replay(db, platform, _site_transform(platform))
    cfg = dict(platform.configuration or {})
    cfg["demo"] = True
    cfg["demo_seeded_at"] = datetime.now(timezone.utc).isoformat()
    platform.configuration = cfg
    db.commit()
    return {"seeded": True, "platform_id": str(platform.id), "slug": platform.slug, "reports": reports, "cases": cases,
            "translated": "南投" not in normalize_admin(platform.county or "")}
