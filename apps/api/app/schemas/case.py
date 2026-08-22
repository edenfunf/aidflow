from __future__ import annotations

import uuid
from datetime import datetime

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
    lat: float
    lon: float
    town: str | None = None
    location_label: str | None = None
    report_count: int
    unique_reporter_count: int
    assigned_unit: str | None = None
    public_summary: str | None = None
    threshold_reached_at: datetime | None = None
    dispatched_at: datetime | None = None
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
    from_status: str | None = None
    to_status: str | None = None
    to_status_label: str | None = None
    actor_role: str
    actor_name: str | None = None
    note: str | None = None
    public: bool
    created_at: datetime


class AssignmentItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    unit_name: str
    team_lead: str | None = None
    contact: str | None = None
    note: str | None = None
    status: str
    unit_id: uuid.UUID | None = None
    route_source: str | None = None
    distance_m: int | None = None
    eta_minutes: int | None = None
    vehicles: list[dict] = Field(default_factory=list)
    notified_via: str | None = None
    notified_at: datetime | None = None
    departed_at: datetime | None = None
    created_at: datetime


class ResponderUnitItem(BaseModel):
    id: uuid.UUID
    name: str
    kind: str
    kind_label: str
    town: str | None = None
    lat: float
    lon: float
    address: str | None = None
    phone: str | None = None
    location_source: str
    source: str | None = None


class ResponderSuggestion(BaseModel):
    unit: ResponderUnitItem
    kind_rank: int
    primary: bool
    straight_m: int
    vehicles: list[dict]
    distance_m: int | None = None
    eta_minutes: int | None = None
    route_source: str | None = None
    route: dict | None = None


class ResponderSuggestionResponse(BaseModel):
    case_id: uuid.UUID
    category: str
    items: list[ResponderSuggestion]


class DispatchRequest(BaseModel):
    unit_id: uuid.UUID
    note: str | None = Field(default=None, max_length=500)
    actor_name: str | None = Field(default=None, max_length=100)
    notify: bool = True


class DispatchNotification(BaseModel):
    channel: str
    status: str
    detail: str | None = None
    external_ref: str | None = None


class NearbyCase(BaseModel):
    id: uuid.UUID
    case_number: str
    title: str
    category: str
    severity: str
    status: str
    distance_m: float


class CaseDetailResponse(BaseModel):
    case: CaseItem
    reports: list[ReportInternal]
    assignments: list[AssignmentItem]
    events: list[CaseEventItem]
    photos: list[PhotoItem]
    nearby: list[NearbyCase]
    reporter_roles: dict[str, int]


class TransitionRequest(BaseModel):
    status: str = Field(..., description="目標狀態（須為允許的轉換）")
    note: str | None = Field(default=None, max_length=500)
    public: bool = Field(default=True, description="是否顯示在公開時間軸")
    actor_name: str | None = Field(default=None, max_length=100)


class AssignRequest(BaseModel):
    unit_name: str = Field(..., min_length=1, max_length=100, description="處理單位，例如 仁愛鄉公所工務課")
    team_lead: str | None = Field(default=None, max_length=100)
    contact: str | None = Field(default=None, max_length=100)
    note: str | None = Field(default=None, max_length=500)
    actor_name: str | None = Field(default=None, max_length=100)


class UpdateRequest(BaseModel):
    note: str = Field(..., min_length=1, max_length=1000)
    public: bool = True
    actor_name: str | None = Field(default=None, max_length=100)


class CaseActionResponse(BaseModel):
    case: CaseItem
    event: CaseEventItem | None = None
    assignment: AssignmentItem | None = None


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
    lat: float
    lon: float
    town: str | None = None
    location_label: str | None = None
    report_count: int
    unique_reporter_count: int
    assigned_unit: str | None = None
    public_summary: str | None = None
    created_at: datetime
    updated_at: datetime
    dispatched_at: datetime | None = None
    resolved_at: datetime | None = None


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


class DispatchResponse(BaseModel):
    case: CaseItem
    assignment: AssignmentItem
    notification: DispatchNotification
