"""審核點 → 上報 EMIC／民間可處理／不成案, public progress, map removal,
LINE / e-mail notifications (needs a live database)."""
from __future__ import annotations

import io
import struct
import uuid
import zlib

import httpx
from sqlalchemy import select

from app.core.config import settings
from app.db.database import SessionLocal
from app.db.models import NotificationLog, Report


def _png() -> bytes:
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00\x00\xff\x00")) + chunk(b"IEND", b""))


def _case(client, slug, lat, lon, category="flooding", **extra) -> str:
    body = {"category": category, "lat": lat, "lon": lon, "description": "積水", "reporter_role": "citizen"}
    client.post(f"/v1/public/platforms/{slug}/reports", json={**body, "client_key": f"k-{uuid.uuid4().hex}", **extra})
    second = client.post(f"/v1/public/platforms/{slug}/reports", json={**body, "client_key": f"k-{uuid.uuid4().hex}"}).json()
    assert second["case_created"], second
    return second["case_id"]


def _on_map(client, slug, case_id) -> bool:
    feats = client.get(f"/v1/public/platforms/{slug}/map").json()["features"]
    return any(f["id"] == f"case:{case_id}" for f in feats)


def test_emic_track_manual_entry_to_closed_and_off_the_map(client, platform):
    slug = platform["slug"]
    case_id = _case(client, slug, 24.0001, 121.1001, category="road_collapse")
    assert _on_map(client, slug, case_id)

    r = client.post(f"/v1/cases/{case_id}/review", json={"decision": "emic"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["case"]["status"] == "reported_emic" and body["case"]["track"] == "emic"
    assert body["result"]["mode"] == "manual" and "回填" in body["result"]["detail"]
    assert body["case"]["reviewed_at"] and body["case"]["reviewed_by"] == "開發模式"
    # reviewing twice is refused
    assert client.post(f"/v1/cases/{case_id}/review", json={"decision": "community"}).status_code == 409

    upd = client.post(f"/v1/cases/{case_id}/emic", json={
        "emic_case_no": "EMIC-TEST-0001", "emic_status": "已派員處理", "assigned_unit": "公路局埔里工務段",
        "note": "單線通行 洽 0912-111-222", "status": "emic_processing"})
    assert upd.status_code == 200, upd.text
    c = upd.json()["case"]
    assert c["status"] == "emic_processing" and c["emic_case_no"] == "EMIC-TEST-0001" and c["emic_status"] == "已派員處理"

    public = client.get(f"/v1/public/platforms/{slug}/cases/{case_id}").json()
    assert public["case"]["emic_status"] == "已派員處理" and public["case"]["assigned_unit"] == "公路局埔里工務段"
    assert "EMIC-TEST-0001" not in str(public)  # the EMIC case number stays internal
    labels = [t["label"] for t in public["timeline"]]
    assert labels[:2] == ["民眾回報", "民眾回報"]
    assert labels.index("成案") < labels.index("已上報 EMIC") < labels.index("處理中")
    assert "EMIC 資訊更新" in labels
    notes = " ".join(t["note"] or "" for t in public["timeline"])
    assert "0912-111-222" not in notes and "[已遮蔽]" in notes
    assert [p["key"] for p in public["progress"]] == ["pending_review", "reported_emic", "emic_processing", "closed"]
    assert public["can_assist"] is False

    done = client.post(f"/v1/cases/{case_id}/transition", json={"status": "closed"})
    assert done.status_code == 200 and done.json()["case"]["closed_at"]
    assert not _on_map(client, slug, case_id), "closed cases are removed from the public map"
    # still reachable by link (a subscriber's e-mail), and listed under 已結案
    assert client.get(f"/v1/public/platforms/{slug}/cases/{case_id}").status_code == 200
    closed = client.get(f"/v1/public/platforms/{slug}/cases", params={"phase": "done"}).json()["items"]
    assert any(x["id"] == case_id for x in closed)
    # the reports that formed it leave the public map too
    feats = client.get(f"/v1/public/platforms/{slug}/map").json()["features"]
    assert not any(f["properties"].get("case_id") == case_id for f in feats)


def test_emic_api_mode_submits_mapped_fields(client, platform, monkeypatch):
    sent: dict = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        sent.update(url=url, json=json, headers=headers)
        return httpx.Response(200, json={"case_no": "EMIC-API-9", "status": "已受理"})

    monkeypatch.setattr(settings, "EMIC_SUBMIT_URL", "https://emic.example.invalid/submit")
    monkeypatch.setattr(settings, "EMIC_API_TOKEN", "tok")
    monkeypatch.setattr(httpx, "post", fake_post)
    case_id = _case(client, platform["slug"], 24.0101, 121.1101, category="landslide")
    body = client.post(f"/v1/cases/{case_id}/review", json={"decision": "emic"}).json()
    assert body["result"]["submitted"] is True
    assert body["case"]["emic_channel"] == "api" and body["case"]["emic_case_no"] == "EMIC-API-9"
    assert sent["headers"]["Authorization"] == "Bearer tok"
    assert sent["json"]["source_system"] == "AidFlow" and sent["json"]["county"] == "南投縣"
    assert sent["json"]["reporter_count"] == 2


def test_emic_api_failure_falls_back_to_manual(client, platform, monkeypatch):
    monkeypatch.setattr(settings, "EMIC_SUBMIT_URL", "https://emic.example.invalid/submit")
    monkeypatch.setattr(httpx, "post", lambda *a, **k: httpx.Response(503, text="down"))
    case_id = _case(client, platform["slug"], 24.0201, 121.1201)
    body = client.post(f"/v1/cases/{case_id}/review", json={"decision": "emic"}).json()
    assert body["case"]["status"] == "reported_emic" and body["case"]["emic_channel"] == "manual"
    assert body["result"]["submitted"] is False and "人工登錄" in body["result"]["detail"]
    internal = client.get(f"/v1/cases/{case_id}").json()
    assert any(e["event_type"] == "emic_submit_failed" and not e["public"] for e in internal["events"])


def test_community_track_citizen_submits_officer_confirms(client, platform):
    slug = platform["slug"]
    case_id = _case(client, slug, 24.0301, 121.1301, category="flooding")
    r = client.post(f"/v1/cases/{case_id}/review", json={"decision": "community"}).json()
    assert r["case"]["status"] == "community_open" and r["case"]["track"] == "community"
    detail = client.get(f"/v1/public/platforms/{slug}/cases/{case_id}").json()
    assert detail["can_assist"] is True and detail["case"]["phase"] == "community"

    url = f"/v1/public/platforms/{slug}/cases/{case_id}/community-report"
    # a photo is required
    assert client.post(url, data={"note": "清好了"}).status_code == 422
    assert client.post(url, files=[("files", ("x.txt", io.BytesIO(b"no"), "text/plain"))]).status_code == 415
    ok = client.post(url, files=[("files", ("done.png", io.BytesIO(_png()), "image/png"))],
                     data={"note": "已清除排水孔，聯絡 0912-000-000", "helper_name": "熱心鄰居"})
    assert ok.status_code == 201, ok.text
    assert ok.json()["case"]["status"] == "community_submitted" and ok.json()["photos"] == 1
    # nobody can submit again while it waits for confirmation
    assert client.post(url, files=[("files", ("done.png", io.BytesIO(_png()), "image/png"))]).status_code == 409

    public = client.get(f"/v1/public/platforms/{slug}/cases/{case_id}").json()
    assert any(p["kind"] == "after" and p["source"] == "citizen" for p in public["photos"])
    assert "0912-000-000" not in str(public) and "熱心鄰居" not in str(public)

    # the officer sends it back once …
    back = client.post(f"/v1/cases/{case_id}/community/confirm", json={"approve": False, "note": "照片看不出已清除"}).json()
    assert back["case"]["status"] == "community_open"
    client.post(url, files=[("files", ("again.png", io.BytesIO(_png()), "image/png"))])
    # … then accepts: closed and off the map
    closed = client.post(f"/v1/cases/{case_id}/community/confirm", json={"approve": True}).json()
    assert closed["case"]["status"] == "closed" and closed["case"]["track"] == "community"
    assert not _on_map(client, slug, case_id)
    assert client.post(f"/v1/cases/{case_id}/community/confirm", json={"approve": True}).status_code == 409


def test_community_case_can_be_escalated_and_pending_can_be_dismissed(client, platform):
    slug = platform["slug"]
    case_id = _case(client, slug, 24.0401, 121.1401)
    client.post(f"/v1/cases/{case_id}/review", json={"decision": "community"})
    esc = client.post(f"/v1/cases/{case_id}/transition", json={"status": "reported_emic"})
    assert esc.status_code == 200 and esc.json()["case"]["track"] == "emic"

    other = _case(client, slug, 24.0501, 121.1501)
    gone = client.post(f"/v1/cases/{other}/review", json={"decision": "dismiss", "note": "重複通報"}).json()
    assert gone["case"]["status"] == "dismissed"
    assert client.get(f"/v1/public/platforms/{slug}/cases/{other}").status_code == 404
    assert not _on_map(client, slug, other)

    # the state machine still refuses shortcuts
    third = _case(client, slug, 24.0601, 121.1601)
    bad = client.post(f"/v1/cases/{third}/transition", json={"status": "closed"})
    assert bad.status_code == 400 and "reported_emic" in bad.json()["detail"]["allowed"]
    assert client.post(f"/v1/cases/{third}/emic", json={"emic_status": "處理中"}).status_code == 409


def test_manual_promotion_goes_to_review(client, platform):
    slug = platform["slug"]
    one = client.post(f"/v1/public/platforms/{slug}/reports", json={
        "category": "trapped_person", "lat": 24.0701, "lon": 121.1701, "client_key": "solo"}).json()
    assert one["case_created"] is False
    case = client.post(f"/v1/platforms/{platform['id']}/clusters/{one['cluster_id']}/promote").json()
    assert case["status"] == "pending_review"
    events = client.get(f"/v1/cases/{case['id']}").json()["events"]
    assert any(e["event_type"] == "case.created" and "人工成案" in (e["note"] or "") for e in events)


def test_notifications_are_logged_and_subscribers_can_unsubscribe(client, platform):
    slug = platform["slug"]
    body = {"category": "flooding", "lat": 24.0801, "lon": 121.1801, "reporter_role": "citizen"}
    first = client.post(f"/v1/public/platforms/{slug}/reports", json={
        **body, "client_key": "n1", "reporter_email": "Sub@Example.com", "notify_opt_in": True}).json()
    assert first["notify_opt_in"] is True and "Email" in first["message"]
    second = client.post(f"/v1/public/platforms/{slug}/reports", json={**body, "client_key": "n2"}).json()
    case_id = second["case_id"]
    client.post(f"/v1/cases/{case_id}/review", json={"decision": "community"})

    logs = client.get(f"/v1/platforms/{platform['id']}/notifications").json()["items"]
    kinds = {(n["channel"], n["kind"], n["status"]) for n in logs}
    # no LINE group bound → staff pushes are skipped; no SMTP → e-mails simulated, never sent
    assert ("line", "new_report", "skipped") in kinds
    assert ("line", "review_needed", "skipped") in kinds
    progress = [n for n in logs if n["channel"] == "email" and n["kind"] == "case_progress"]
    assert progress and all(n["status"] == "simulated" for n in progress)
    assert all(n["recipient"] == "s***@example.com" for n in progress)
    assert len(progress) == 2  # 審核中, then 開放民眾協助

    with SessionLocal() as db:
        token = db.scalar(select(Report.notify_token).where(Report.id == uuid.UUID(first["report_id"])))
    assert token
    assert client.post("/v1/public/unsubscribe", params={"token": token}).status_code == 200
    assert client.post("/v1/public/unsubscribe", params={"token": "x" * 20}).status_code == 404
    client.post(f"/v1/cases/{case_id}/transition", json={"status": "closed"})
    with SessionLocal() as db:
        n = db.scalars(select(NotificationLog).where(NotificationLog.case_id == uuid.UUID(case_id),
                                                     NotificationLog.channel == "email")).all()
    assert len(n) == 2, "no e-mail after unsubscribing"
