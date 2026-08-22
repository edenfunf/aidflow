"""Image abstraction (module: photo_upload).

Bytes live in a media store (local filesystem under MEDIA_ROOT — a Docker
volume in compose; swap for object storage by replacing ``_write``/``path``);
the database keeps metadata only. No placeholders are ever generated: when a
report has no photo the UI shows an honest empty state.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import IncidentCase, Report, ReportPhoto
from app.services import outbox_service

ALLOWED_TYPES: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/heic": "heic",
}
KINDS = ("scene", "before", "after")


class UnsupportedMediaError(Exception):
    pass


class MediaTooLargeError(Exception):
    pass


def _root() -> Path:
    root = Path(settings.MEDIA_ROOT)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _sniff(data: bytes, declared: str) -> str:
    """Trust magic bytes over the declared content type."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[4:12] in (b"ftypheic", b"ftypheix", b"ftypmif1"):
        return "image/heic"
    return declared


def public_url(photo: ReportPhoto) -> str:
    return f"/v1/public/media/{photo.id}"


def save_photo(
    db: Session,
    *,
    platform_id: uuid.UUID,
    data: bytes,
    content_type: str,
    report: Report | None = None,
    case: IncidentCase | None = None,
    kind: str = "scene",
    source: str = "citizen",
    caption: str | None = None,
) -> ReportPhoto:
    if len(data) > settings.MEDIA_MAX_BYTES:
        raise MediaTooLargeError()
    ctype = _sniff(data, (content_type or "").split(";")[0].strip().lower())
    if ctype not in ALLOWED_TYPES:
        raise UnsupportedMediaError()
    if kind not in KINDS:
        kind = "scene"
    photo_id = uuid.uuid4()
    rel = Path(str(platform_id)) / f"{photo_id}.{ALLOWED_TYPES[ctype]}"
    target = _root() / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)

    photo = ReportPhoto(
        id=photo_id,
        report_id=report.id if report else None,
        case_id=case.id if case else (report.case_id if report else None),
        platform_id=platform_id,
        kind=kind,
        source=source,
        storage_key=rel.as_posix(),
        content_type=ctype,
        size_bytes=len(data),
        caption=caption,
        public=True,
    )
    db.add(photo)
    if report is not None:
        report.photo_count = (report.photo_count or 0) + 1
    db.flush()
    outbox_service.enqueue_event(
        db, event_type="photo.uploaded", aggregate_id=photo.id,
        payload={"platform_id": str(platform_id), "photo_id": str(photo.id),
                 "report_id": str(report.id) if report else None,
                 "case_id": str(photo.case_id) if photo.case_id else None, "kind": kind, "source": source},
    )
    db.commit()
    db.refresh(photo)
    return photo


def path_for(photo: ReportPhoto) -> Path:
    return _root() / photo.storage_key


def get_photo(db: Session, photo_id: uuid.UUID) -> ReportPhoto | None:
    return db.get(ReportPhoto, photo_id)


def photos_for_case(db: Session, case_id: uuid.UUID, *, public_only: bool) -> list[ReportPhoto]:
    q = select(ReportPhoto).where(ReportPhoto.case_id == case_id)
    if public_only:
        q = q.where(ReportPhoto.public.is_(True))
    return list(db.scalars(q.order_by(ReportPhoto.created_at.asc())).all())


def photos_for_report(db: Session, report_id: uuid.UUID) -> list[ReportPhoto]:
    return list(db.scalars(
        select(ReportPhoto).where(ReportPhoto.report_id == report_id).order_by(ReportPhoto.created_at.asc())
    ).all())


def to_item(photo: ReportPhoto) -> dict:
    return {
        "id": photo.id,
        "report_id": photo.report_id,
        "case_id": photo.case_id,
        "kind": photo.kind,
        "source": photo.source,
        "content_type": photo.content_type,
        "size_bytes": photo.size_bytes,
        "caption": photo.caption,
        "url": public_url(photo),
        "created_at": photo.created_at,
    }
