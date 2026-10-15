from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.report import PhotoItem, ReportInternal, ReportPublic


class CaseItem(BaseModel):
    """Console list/detail item."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    platform_id: uuid.UUID
    cluster_id: uuid.UUID | None = None
    case_number: str
    title: str
    category: str
    category_label: str = ""
    severity: str
    status: str
    status_label: str = ""
    phase: str = ""
    track: str | None = None
    track_label: str | None = None
    lat: float
    lon: float
    town: str | None = None
    location_label: str | None = None
    report_count: int
    unique_reporter_count: int
    assigned_unit: str | None = None
    public_summary: str | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    emic_case_no: str | None = None
    emic_status: str | None = None
    emic_channel: str | None = None
    emic_reported_at: datetime | None = None
    emic_synced_at: datetime | None = None
    community_submitted_at: datetime | None = None
    threshold_reached_at: datetime | None = None
    resolved_at: datetime | None = None
    closed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    next_statuses: list[str] = Field(default_factory=list)


class CaseListResponse(BaseModel):
    items: list[CaseItem]
    total: int
    limit: int
    offset: int


class CaseEventItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_type: str
    label: str = ""
    from_status: str | None = None
    to_status: str | None = None
    to_status_label: str | None = None
    actor_role: str
    actor_name: str | None = None
    note: str | None = None
    public: bool
    created_at: datetime


class NearbyCase(BaseModel):
    id: uuid.UUID
    case_number: str
    title: str
    category: str
    severity: str
    status: str
    distance_m: float


class EmicInfo(BaseModel):
    mode: str  # manual | api
    field_map: list[dict]
    status_suggestions: list[str]


class CaseDetailResponse(BaseModel):
    case: CaseItem
    reports: list[ReportInternal]
    events: list[CaseEventItem]
    photos: list[PhotoItem]
    nearby: list[NearbyCase]
    reporter_roles: dict[str, int]
    emic: EmicInfo
    pii_visible: bool


class TransitionRequest(BaseModel):
    status: str = Field(..., description="目標狀態（須為允許的轉換）")
    note: str | None = Field(default=None, max_length=500)
    public: bool = Field(default=True, description="是否顯示在公開時間軸")


class ReviewRequest(BaseModel):
    decision: Literal["emic", "community", "dismiss"] = Field(..., description="上報 EMIC／民間可處理／不成案")
    note: str | None = Field(default=None, max_length=500)


class EmicUpdateRequest(BaseModel):
    emic_case_no: str | None = Field(default=None, max_length=60)
    emic_status: str | None = Field(default=None, max_length=60)
    assigned_unit: str | None = Field(default=None, max_length=100)
    note: str | None = Field(default=None, max_length=1000, description="公開處理進度（選填）")
    status: Literal["emic_processing", "closed"] | None = None


class CommunityConfirmRequest(BaseModel):
    approve: bool
    note: str | None = Field(default=None, max_length=500)


class UpdateRequest(BaseModel):
    note: str = Field(..., min_length=1, max_length=1000)
    public: bool = True


class CaseActionResponse(BaseModel):
    case: CaseItem
    event: CaseEventItem | None = None
    result: dict | None = None


# ── public ────────────────────────────────────────────────────────────────
class PublicCase(BaseModel):
    id: uuid.UUID
    case_number: str
    title: str
    category: str
    category_label: str
    severity: str
    status: str
    status_label: str
    phase: str
    track: str | None = None
    track_label: str | None = None
    lat: float
    lon: float
    town: str | None = None
    location_label: str | None = None
    report_count: int
    unique_reporter_count: int
    assigned_unit: str | None = None
    emic_status: str | None = None
    public_summary: str | None = None
    created_at: datetime
    updated_at: datetime
    reviewed_at: datetime | None = None
    closed_at: datetime | None = None


class PublicCaseListResponse(BaseModel):
    items: list[PublicCase]
    total: int


class PublicTimelineItem(BaseModel):
    event_type: str
    label: str
    note: str | None = None
    to_status: str | None = None
    at: datetime


class PublicCaseDetail(BaseModel):
    case: PublicCase
    timeline: list[PublicTimelineItem]
    reports: list[ReportPublic]
    photos: list[PhotoItem]
    progress: list[dict]
    can_assist: bool = False


class CommunitySubmitResponse(BaseModel):
    case: PublicCase
    photos: int
    message: str
