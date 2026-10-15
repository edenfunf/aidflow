"""LINE Messaging API webhook — only used to bind a county group to a
platform (「綁定 <代碼>」). Requests must carry a valid X-Line-Signature."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.connectors import line
from app.db.database import get_db
from app.services import line_service

router = APIRouter(prefix="/v1/line", tags=["line"])


@router.post("/webhook", summary="LINE webhook（群組加入與綁定）")
async def webhook(request: Request, x_line_signature: str | None = Header(default=None),
                  db: Session = Depends(get_db)) -> dict:
    if not line.webhook_enabled():
        raise HTTPException(status_code=503, detail="LINE_CHANNEL_SECRET 未設定")
    body = await request.body()
    if not line.verify_signature(body, x_line_signature):
        raise HTTPException(status_code=401, detail="invalid signature")
    try:
        payload = json.loads(body.decode("utf-8") or "{}")
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid body")
    return {"handled": line_service.handle_webhook(db, payload)}
