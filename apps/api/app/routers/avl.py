"""AVL (automatic vehicle location) ingest — a county fleet / CAD system pushes
vehicle GPS here; fresh pings replace the dispatch simulation on every map."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.feature import AvlIngestRequest
from app.services import responder_service

router = APIRouter(prefix="/v1/avl", tags=["avl"])


@router.post("/positions", summary="Ingest vehicle positions (protected)")
def ingest(payload: AvlIngestRequest, db: Session = Depends(get_db)) -> dict:
    items = []
    for p in payload.positions:
        d = p.model_dump()
        if d.get("recorded_at"):
            d["recorded_at"] = datetime.fromisoformat(str(d["recorded_at"]).replace("Z", "+00:00"))
        items.append(d)
    return {"ingested": responder_service.ingest_avl(db, items)}
