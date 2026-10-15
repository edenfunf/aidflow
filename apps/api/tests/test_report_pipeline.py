"""Report → cluster → N-reporter trigger → case awaiting review → public
timeline (needs a live database)."""
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


def test_two_distinct_reporters_create_a_case_awaiting_review(client, platform):
    slug = platform["slug"]
    first = _submit(client, slug, client_key="device-A", reporter_contact="0912000001", reporter_name="王村長")
    assert first["case_created"] is False and first["unique_reporters"] == 1
    assert first["required_unique_reporters"] == 2
    assert "承辦人員會收到通知" in first["message"]

    # the same person again (same contact, other device) — still one reporter
    dup = _submit(client, slug, client_key="device-B", reporter_contact="0912000001", lat=24.02352, lon=121.15722)
    assert dup["case_created"] is False and dup["unique_reporters"] == 1
    assert dup["cluster_id"] == first["cluster_id"]

    # a different person nearby with a *similar* category → threshold reached
    second = _submit(client, slug, client_key="device-C", category="road_blocked", lat=24.0237, lon=121.1575)
    assert second["case_created"] is True and second["unique_reporters"] == 2
    assert second["cluster_id"] == first["cluster_id"]
    assert second["case_number"].startswith("NAN-")
    assert "審核" in second["message"]

    # a third report joins the existing case instead of opening another
    third = _submit(client, slug, client_key="device-D", lat=24.0236, lon=121.1573)
    assert third["case_created"] is False and third["case_id"] == second["case_id"]
    assert "併入" in third["message"]

    case = client.get(f"/v1/cases/{second['case_id']}").json()
    assert case["case"]["status"] == "pending_review" and case["case"]["track"] is None
    assert case["case"]["next_statuses"] == ["reported_emic", "community_open", "dismissed"]
    assert case["case"]["report_count"] == 4 and case["case"]["unique_reporter_count"] == 3
    assert case["case"]["title"].endswith("道路坍方")
    assert case["case"]["location_label"] and "12 號" not in case["case"]["location_label"]
    assert case["reporter_roles"]["citizen"] == 4
    # the 開發模式 principal holds view_pii: the officer view carries PII
    assert case["pii_visible"] is True
    assert any(r["reporter_contact"] == "0912000001" for r in case["reports"])
    assert case["emic"]["mode"] == "manual" and case["emic"]["field_map"]

    # a pending case is not in the queue yet
    queued = client.get(f"/v1/platforms/{platform['id']}/cases", params={"phase": "queued"}).json()
    assert all(c["id"] != second["case_id"] for c in queued["items"])
    pending = client.get(f"/v1/platforms/{platform['id']}/cases", params={"phase": "pending"}).json()
    assert any(c["id"] == second["case_id"] for c in pending["items"])


def test_far_apart_or_unrelated_reports_do_not_merge(client, platform):
    slug = platform["slug"]
    a = _submit(client, slug, client_key="x1")
    far = _submit(client, slug, client_key="x2", lat=24.0300, lon=121.1572)  # ~720 m
    assert far["cluster_id"] != a["cluster_id"] and far["case_created"] is False
    other = _submit(client, slug, client_key="x3", category="flooding")  # same spot, unrelated category
    assert other["cluster_id"] != a["cluster_id"] and other["case_created"] is False
    nocoord = client.post(f"/v1/public/platforms/{slug}/reports",
                          json={"category": "other", "description": "沒有座標"}).json()
    assert nocoord["cluster_id"] is None and "位置" in nocoord["message"]


def test_time_window_is_enforced(client, platform):
    db = SessionLocal()
    try:
        p = db.get(Platform, __import__("uuid").UUID(platform["id"]))
        old = datetime.now(timezone.utc) - timedelta(minutes=180)
        r1, c1, case1 = report_service.create_report(
            db, p, ReportCreate(**_report(lat=23.9, lon=120.9)), client_key="t1", created_at=old, notify=False)
        r2, c2, case2 = report_service.create_report(
            db, p, ReportCreate(**_report(lat=23.9, lon=120.9)), client_key="t2", notify=False)
        assert c1 is not None and c2 is not None
        assert c1.id != c2.id, "a report 3 h later must open a new cluster"
        assert case1 is None and case2 is None
    finally:
        db.close()


def test_invalid_category_and_subscription_validation(client, platform):
    resp = client.post(f"/v1/public/platforms/{platform['slug']}/reports",
                       json=_report(category="gas_leak", client_key="g1"))
    assert resp.status_code == 422
    assert "road_collapse" in resp.json()["detail"]["allowed"]
    assert client.post(f"/v1/public/platforms/{platform['slug']}/reports",
                       json={"category": "flooding", "lat": 24.0}).status_code == 422  # lon missing
    # subscribing to progress needs an e-mail, and it has to look like one
    assert client.post(f"/v1/public/platforms/{platform['slug']}/reports",
                       json=_report(client_key="g2", notify_opt_in=True)).status_code == 422
    assert client.post(f"/v1/public/platforms/{platform['slug']}/reports",
                       json=_report(client_key="g3", notify_opt_in=True, reporter_email="not-an-email")).status_code == 422


def test_public_surfaces_never_expose_pii(client, platform):
    slug = platform["slug"]
    _submit(client, slug, client_key="p1", reporter_name="林小姐", reporter_contact="0933111222",
            reporter_email="lin@example.com", notify_opt_in=True,
            description="我是林小姐 電話 0933111222", lat=24.0500, lon=121.1000)
    _submit(client, slug, client_key="p2", lat=24.0501, lon=121.1001)
    for path in (f"/v1/public/platforms/{slug}/reports", f"/v1/public/platforms/{slug}/map",
                 f"/v1/public/platforms/{slug}/cases"):
        text = client.get(path).text
        assert "林小姐" not in text and "0933111222" not in text and "reporter_contact" not in text
        assert "lin@example.com" not in text and "notify_token" not in text
        assert "12 號" not in text
    feats = client.get(f"/v1/public/platforms/{slug}/map").json()["features"]
    rep = next(f for f in feats if f["properties"]["layer"] == "citizen_reports")
    lon, lat = rep["geometry"]["coordinates"]
    assert round(lat, 3) == lat and round(lon, 3) == lon  # coarsened
    internal = client.get(f"/v1/platforms/{platform['id']}/map").json()["features"]
    rep_i = next(f for f in internal if f["properties"]["layer"] == "citizen_reports")
    assert "address" in rep_i["properties"]
    # the console report list never carries personal data
    listed = client.get(f"/v1/platforms/{platform['id']}/reports").json()["items"]
    assert all(r["reporter_email"] is None and r["reporter_contact"] is None for r in listed)
    assert any(r["pii_hidden"] and r["notify_opt_in"] for r in listed)


def _png_bytes() -> bytes:
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    raw = b"\x00\xff\x00\x00"  # 1x1 red pixel, filter byte 0
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"tEXt", b"GPS\x0024.0235,121.1572")
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def test_photo_upload_strips_metadata_and_serves(client, platform):
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
    assert b"121.1572" not in served.content and b"tEXt" not in served.content  # metadata stripped
    assert client.get(f"/v1/reports/{rid}").json()["report"]["photo_count"] == 1
    bad = client.post(f"/v1/public/reports/{rid}/photos", files={"file": ("a.txt", io.BytesIO(b"hello"), "text/plain")})
    assert bad.status_code == 415
    fake = client.post(f"/v1/public/reports/{rid}/photos", files={"file": ("a.png", io.BytesIO(b"\x89PNG\r\n\x1a\nnope"), "image/png")})
    assert fake.status_code == 415  # looks like PNG, is not decodable
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
    assert case["status"] == "pending_review"  # cases are never silently deleted


def test_situation_and_console_overview_are_consistent(client, platform):
    slug = platform["slug"]
    _submit(client, slug, client_key="s1", lat=23.7500, lon=120.7500, category="flooding")
    _submit(client, slug, client_key="s2", lat=23.7500, lon=120.7500, category="flooding")
    s = client.get(f"/v1/public/platforms/{slug}/situation").json()
    assert s["cases_total"] == s["cases_pending"] + s["cases_active"] + s["cases_community"] + s["cases_done"]
    assert s["cases_pending"] >= 1
    assert [t["key"] for t in s["by_severity"]] == ["critical", "high", "medium", "low"]
    assert s["reports_total"] >= 2 and len(s["trend"]) == 24
    assert s["trend_direction"] in {"rising", "falling", "steady"}
    o = client.get(f"/v1/platforms/{platform['id']}/overview").json()
    assert o["cases_total"] == s["cases_total"]
    assert sum(t["count"] for t in o["pending_by_severity"]) == o["cases_pending"]
    assert "by_reporter_role" in o and "median_review_minutes" in o
    g = client.get("/v1/overview").json()
    assert g["platforms_published"] >= 1 and "cases_pending_review" in g


def test_reporter_contact_details_are_encrypted_at_rest(client, platform):
    from sqlalchemy import text

    from app.db import crypto

    _submit(client, platform["slug"], client_key="enc-1", reporter_name="陳先生", reporter_contact="0977123456",
            reporter_email="chen@example.com", notify_opt_in=True)
    with SessionLocal() as db:
        raw = db.execute(text(
            "SELECT r.reporter_name, r.reporter_contact, r.reporter_email FROM reports r "
            "JOIN platforms p ON p.id = r.platform_id WHERE p.slug = :slug"), {"slug": platform["slug"]}).one()
    assert all(v.startswith(crypto.PREFIX) for v in raw)
    assert "0977123456" not in "".join(raw) and "chen@example.com" not in "".join(raw)

    # the ORM (and so officers with view_pii) still see the plain values
    listed = client.get(f"/v1/platforms/{platform['id']}/reports").json()
    assert listed  # platform report list omits PII
    assert crypto.decrypt(raw[1]) == "0977123456"
    assert crypto.decrypt("legacy plaintext") == "legacy plaintext"
    assert crypto.encrypt(raw[1]) == raw[1]  # never double-encrypted
    assert crypto.decrypt(crypto.PREFIX + "AAAA") == crypto.UNREADABLE
