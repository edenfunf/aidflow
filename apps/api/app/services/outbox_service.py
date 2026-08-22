from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import EventOutbox


def enqueue_event(
    db: Session,
    *,
    event_type: str,
    aggregate_id: uuid.UUID | None,
    payload: dict,
) -> EventOutbox:
    # Caller commits, so the event and its aggregate persist atomically.
    event = EventOutbox(
        event_type=event_type,
        aggregate_id=aggregate_id,
        payload=payload,
        processed=False,
    )
    db.add(event)
    db.flush()
    return event


def list_events(
    db: Session,
    *,
    processed: bool | None = None,
    limit: int = 20,
) -> list[EventOutbox]:
    query = select(EventOutbox)
    if processed is not None:
        query = query.where(EventOutbox.processed == processed)
    return list(db.scalars(query.order_by(EventOutbox.created_at.desc()).limit(limit)).all())


def list_platform_events(
    db: Session, platform_id: uuid.UUID, *, limit: int = 200, offset: int = 0
) -> list[EventOutbox]:
    """The audit trail of one platform — every event carries platform_id in
    its payload."""
    query = (
        select(EventOutbox)
        .where(EventOutbox.payload["platform_id"].astext == str(platform_id))
        .order_by(EventOutbox.created_at.desc(), EventOutbox.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(db.scalars(query).all())
