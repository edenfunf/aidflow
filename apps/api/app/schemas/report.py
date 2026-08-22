from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Severity = Literal["low", "medium", "high", "critical"]


class ReportCreate(BaseModel):
    """Citizen report. lat/lon are optional but must come together; reports
    without coordinates are stored but never clustered."""

    category: str = Field(..., min_length=1, description="災情類別（需在平台啟用的類別內）")
    description: str | None = Field(default=None, max_length=2000, description="簡單描述（選填）")
    severity: Severity | None = Field(default=None, description="回報者認知的嚴重度（選填）")
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    address: str | None = Field(default=None, max_length=300, description="地點描述（內部使用，公開時遮罩）")
    town: str | None = Field(default=None, max_length=50)
    reporter_role: str = Field(default="citizen", description="citizen / village_chief / disaster_officer / volunteer / community_org")
    reporter_name: str | None = Field(default=None, max_length=100, description="PII，僅內部")
    reporter_contact: str | None = Field(default=None, max_length=100, description="PII，僅內部")
    client_key: str | None = Field(
        default=None, max_length=128,
        description="前端產生的裝置識別，用於計算不同回報者；只儲存雜湊",
    )

    @model_validator(mode="after")
    def _coords_paired(self) -> ReportCreate:
        if (self.lat is None) != (self.lon is None):
            raise ValueError("lat and lon must be provided together")
        return self

    model_config = {
        "json_schema_extra": {
            "example": {
                "category": "road_collapse",
                "description": "台14甲線往清境方向路基掏空，單線無法通行",
                "lat": 24.0235,
                "lon": 121.1572,
                "address": "南投縣仁愛鄉台14甲線 18K",
                "reporter_role": "village_chief",
                "reporter_contact": "0912345678",
                "client_key": "d3b07384d113edec49eaa6238ad5ff00",
            }
        }
    }


class ReportCreateResponse(BaseModel):
    report_id: uuid.UUID
    status: str
    cluster_id: uuid.UUID | None = None
    case_id: uuid.UUID | None = None
    case_number: str | None = None
    case_created: bool = False
    unique_reporters: int = 0
    required_unique_reporters: int
    message: str


class ReportPublic(BaseModel):
    """No PII; coarse location; redacted text."""

    report_id: str
    category: str
    severity: str
    status: str
    town: str | None = None
    location_label: str | None = None
    description: str | None = None
    reporter_role: str
    photo_count: int
    case_id: str | None = None
    cluster_id: str | None = None
    created_at: str | None = None
    lat: float | None = None
    lon: float | None = None


class ReportInternal(BaseModel):
    """Government view — includes PII; only behind the API key gate."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    platform_id: uuid.UUID
    category: str
    description: str | None = None
    severity: str
    triage_severity: str
    lat: float | None = None
    lon: float | None = None
    town: str | None = None
    address: str | None = None
    reporter_role: str
    reporter_name: str | None = None
    reporter_contact: str | None = None
    has_identity: bool = False
    status: str
    cluster_id: uuid.UUID | None = None
    case_id: uuid.UUID | None = None
    photo_count: int
    source: str
    created_at: datetime
    updated_at: datetime


class ReportListResponse(BaseModel):
    items: list[ReportInternal]
    total: int
    limit: int
    offset: int


class PublicReportListResponse(BaseModel):
    items: list[ReportPublic]
    total: int


class PhotoItem(BaseModel):
    id: uuid.UUID
    report_id: uuid.UUID | None = None
    case_id: uuid.UUID | None = None
    kind: str
    source: str
    content_type: str
    size_bytes: int
    caption: str | None = None
    url: str
    created_at: datetime
