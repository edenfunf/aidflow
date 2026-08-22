"""Report → cluster → 2-reporter trigger → case → dispatch → public timeline
(needs a live database)."""
from __future__ import annotations

import io
import struct
import zlib
from datetime import datetime, timedelta, timezone

from app.db.database import SessionLocal
from app.db.models import Platform
from app.schemas.report import ReportCreate
from app.services import report_service

SITE = {"lat": 24.0235, "lon": 121.1572}


def _report(**over) -> dict:
    body = {"category": "road_collapse", "description": "台14甲線路基掏空", "reporter_role": "citizen",
            "address": "南投縣仁愛鄉台14甲線 18K 旁 12 號", **SITE}
    body.update(over)
    return body


def _submit(client, slug, **over):
    resp = client.post(f"/v1/public/platforms/{slug}/reports", json=_report(**over))
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_two_distinct_reporters_create_a_case_same_person_twice_does_not(client, platform):
    slug = platform["slug"]
    first = _submit(client, slug, client_key="device-A", reporter_contact="0912000001", reporter_name="王村長")
    assert first["case_created"] is False and first["unique_reporters"] == 1
    assert first["required_unique_reporters"] == 2

    # the same person again (same contact, other device) — still one reporter
    dup = _submit(client, slug, client_key="device-B", reporter_contact="0912000001", lat=24.02352, lon=121.15722)
    assert dup["case_created"] is False and dup["unique_reporters"] == 1
    assert dup["cluster_id"] == first["cluster_id"]

    # a different person nearby with a *similar* category → threshold reached
    second = _submit(client, slug, client_key="device-C", category="road_blocked", lat=24.0237, lon=121.1575)
    assert second["case_created"] is True and second["unique_reporters"] == 2
    assert second["cluster_id"] == first["cluster_id"]
    assert second["case_number"].startswith("NAN-")

    # a third report joins the existing case instead of opening another
    third = _submit(client, slug, client_key="device-D", lat=24.0236, lon=121.1573)
    assert third["case_created"] is False and third["case_id"] == second["case_id"]
    assert "併入" in third["message"]

    case = client.get(f"/v1/cases/{second['case_id']}").json()
    assert case["case"]["status"] == "awaiting_dispatch"
    assert case["case"]["report_count"] == 4 and case["case"]["unique_reporter_count"] == 3
    assert case["case"]["title"].endswith("道路坍方")
    assert case["case"]["location_label"] and "12 號" not in case["case"]["location_label"]
    assert case["reporter_roles"]["citizen"] == 4
    # internal view carries PII, as it must for the EOC
    assert any(r["reporter_contact"] == "0912000001" for r in case["reports"])


def test_far_apart_or_unrelated_reports_do_not_merge(client, platform):
    slug = platform["slug"]
    a = _submit(client, slug, client_key="x1")
    far = _submit(client, slug, client_key="x2", lat=24.0300, lon=121.1572)  # ~720 m
    assert far["cluster_id"] != a["cluster_id"] and far["case_created"] is False
    other = _submit(client, slug, client_key="x3", category="flooding")  # same spot, unrelated category
    assert other["cluster_id"] != a["cluster_id"] and other["case_created"] is False
    nocoord = client.post(f"/v1/public/platforms/{slug}/reports",
                          json={"category": "other", "description": "沒有座標"}).json()
    assert nocoord["cluster_id"] is None and "座標" in nocoord["message"]


def test_time_window_is_enforced(client, platform):
    db = SessionLocal()
    try:
        p = db.get(Platform, __import__("uuid").UUID(platform["id"]))
        old = datetime.now(timezone.utc) - timedelta(minutes=180)
        r1, c1, case1 = report_service.create_report(
            db, p, ReportCreate(**_report(lat=23.9, lon=120.9)), client_key="t1", created_at=old)
        r2, c2, case2 = report_service.create_report(
            db, p, ReportCreate(**_report(lat=23.9, lon=120.9)), client_key="t2")
        assert c1 is not None and c2 is not None
        assert c1.id != c2.id, "a report 3 h later must open a new cluster"
        assert case1 is None and case2 is None
    finally:
        db.close()


def test_invalid_category_for_platform_is_rejected(client, platform):
    resp = client.post(f"/v1/public/platforms/{platform['slug']}/reports",
                       json=_report(category="gas_leak", client_key="g1"))
    assert resp.status_code == 422
    assert "road_collapse" in resp.json()["detail"]["allowed"]
    assert client.post(f"/v1/public/platforms/{platform['slug']}/reports",
                       json={"category": "flooding", "lat": 24.0}).status_code == 422  # lon missing


def _make_case(client, slug, **over):
    _submit(client, slug, client_key="c1", **over)
    created = _submit(client, slug, client_key="c2", **over)
    assert created["case_created"]
    return created["case_id"]


def test_dispatch_state_machine_and_public_timeline(client, platform):
    slug = platform["slug"]
    case_id = _make_case(client, slug, lat=24.0100, lon=121.1400)

    # cannot skip dispatch
    bad = client.post(f"/v1/cases/{case_id}/transition", json={"status": "resolved"})
    assert bad.status_code == 400 and "assigned" in bad.json()["detail"]["allowed"]

    assigned = client.post(f"/v1/cases/{case_id}/assign",
                           json={"unit_name": "公路局埔里工務段", "team_lead": "陳工程司", "contact": "049-0000000",
                                 "actor_name": "值班承辦"}).json()
    assert assigned["case"]["status"] == "assigned" and assigned["case"]["assigned_unit"] == "公路局埔里工務段"
    assert assigned["assignment"]["contact"] == "049-0000000"

    for status in ("en_route", "on_site", "processing"):
        r = client.post(f"/v1/cases/{case_id}/transition", json={"status": status, "actor_name": "現場"})
        assert r.status_code == 200, r.text
    client.post(f"/v1/cases/{case_id}/updates", json={"note": "單線恢復通行 請洽 0912-111-222", "public": True})
    client.post(f"/v1/cases/{case_id}/updates", json={"note": "內部：機具調度備註", "public": False})
    done = client.post(f"/v1/cases/{case_id}/transition", json={"status": "resolved"}).json()
    assert done["case"]["resolved_at"]

    public = client.get(f"/v1/public/platforms/{slug}/cases/{case_id}").json()
    labels = [t["label"] for t in public["timeline"]]
    assert labels[:2] == ["民眾回報", "民眾回報"]
    assert "達到案件成立門檻" in labels and "正式成案" in labels
    assert labels.index("已派員") < labels.index("人員抵達") < labels.index("處理中") < labels.index("已完成")
    notes = " ".join(t["note"] or "" for t in public["timeline"])
    assert "內部" not in notes and "0912-111-222" not in notes and "[已遮蔽]" in notes
    assert "contact" not in str(public) and "049-0000000" not in str(public)
    prog = public["progress"]
    assert prog[-1]["key"] == "resolved" and prog[-1]["reached"] and prog[-1]["current"]
    assert all(step["reached"] for step in prog)
    # timeline is chronological
    ats = [t["at"] for t in public["timeline"]]
    assert ats == sorted(ats)

    internal = client.get(f"/v1/cases/{case_id}").json()
    assert any(e["event_type"] == "internal_note" for e in internal["events"])
    audit = client.get(f"/v1/platforms/{platform['id']}/audit").json()["items"]
    types = {e["event_type"] for e in audit}
    assert {"report.created", "cluster.opened", "case.created", "case.status_changed"} <= types


def test_public_surfaces_never_expose_pii(client, platform):
    slug = platform["slug"]
    _submit(client, slug, client_key="p1", reporter_name="林小姐", reporter_contact="0933111222",
            description="我是林小姐 電話 0933111222", lat=24.0500, lon=121.1000)
    _submit(client, slug, client_key="p2", lat=24.0501, lon=121.1001)
    for path in (f"/v1/public/platforms/{slug}/reports", f"/v1/public/platforms/{slug}/map",
                 f"/v1/public/platforms/{slug}/cases"):
        text = client.get(path).text
        assert "林小姐" not in text and "0933111222" not in text and "reporter_contact" not in text
        assert "12 號" not in text
    feats = client.get(f"/v1/public/platforms/{slug}/map").json()["features"]
    rep = next(f for f in feats if f["properties"]["layer"] == "citizen_reports")
    lon, lat = rep["geometry"]["coordinates"]
    assert round(lat, 3) == lat and round(lon, 3) == lon  # coarsened
    internal = client.get(f"/v1/platforms/{platform['id']}/map").json()["features"]
    rep_i = next(f for f in internal if f["properties"]["layer"] == "citizen_reports")
    assert "address" in rep_i["properties"]


def _png_bytes() -> bytes:
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    raw = b"\x00\xff\x00\x00"  # 1x1 red pixel, filter byte 0
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def test_photo_upload_and_media_serving(client, platform):
    slug = platform["slug"]
    created = _submit(client, slug, client_key="ph1", lat=23.9700, lon=120.9600, category="flooding")
    rid = created["report_id"]
    resp = client.post(f"/v1/public/reports/{rid}/photos", files={"file": ("a.png", io.BytesIO(_png_bytes()), "image/png")},
                       data={"caption": "現場"})
    assert resp.status_code == 201, resp.text
    photo = resp.json()
    assert photo["content_type"] == "image/png" and photo["kind"] == "scene"
    served = client.get(photo["url"])
    assert served.status_code == 200 and served.headers["content-type"] == "image/png"
    assert client.get(f"/v1/reports/{rid}").json()["report"]["photo_count"] == 1
    bad = client.post(f"/v1/public/reports/{rid}/photos", files={"file": ("a.txt", io.BytesIO(b"hello"), "text/plain")})
    assert bad.status_code == 415
    # a case photo from the agency
    _submit(client, slug, client_key="ph2", lat=23.9701, lon=120.9601, category="flooding")
    case_id = client.get(f"/v1/reports/{rid}").json()["report"]["case_id"]
    assert case_id
    after = client.post(f"/v1/cases/{case_id}/photos", files={"file": ("b.png", io.BytesIO(_png_bytes()), "image/png")},
                        data={"kind": "after"})
    assert after.status_code == 201 and after.json()["source"] == "agency"
    detail = client.get(f"/v1/public/platforms/{slug}/cases/{case_id}").json()
    assert {p["kind"] for p in detail["photos"]} == {"scene", "after"}


def test_rejecting_a_report_recounts_the_cluster(client, platform):
    slug = platform["slug"]
    a = _submit(client, slug, client_key="rj1", lat=23.8000, lon=120.8000, category="flooding")
    b = _submit(client, slug, client_key="rj2", lat=23.8001, lon=120.8001, category="flooding")
    assert b["case_created"]
    client.post(f"/v1/reports/{a['report_id']}/reject", params={"note": "誤報"})
    case = client.get(f"/v1/cases/{b['case_id']}").json()["case"]
    assert case["unique_reporter_count"] == 1 and case["report_count"] == 1
    assert case["status"] == "awaiting_dispatch"  # cases are never silently deleted


def test_situation_and_console_overview_are_consistent(client, platform):
    slug = platform["slug"]
    _make_case(client, slug, lat=23.7500, lon=120.7500, category="flooding")
    s = client.get(f"/v1/public/platforms/{slug}/situation").json()
    assert s["cases_total"] == s["cases_pending"] + s["cases_active"] + s["cases_done"]
    assert s["reports_total"] >= 2 and len(s["trend"]) == 24
    assert s["trend_direction"] in {"rising", "falling", "steady"}
    o = client.get(f"/v1/platforms/{platform['id']}/overview").json()
    assert o["cases_total"] == s["cases_total"]
    assert "by_reporter_role" in o
    g = client.get("/v1/overview").json()
    assert g["platforms_published"] >= 1
