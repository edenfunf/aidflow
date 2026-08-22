from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ClusterPolicyInput(BaseModel):
    required_unique_reporters: int | None = Field(default=None, ge=1, le=20)
    radius_meters: int | None = Field(default=None, ge=10, le=5000)
    time_window_minutes: int | None = Field(default=None, ge=1, le=10080)
    count_anonymous_reporters: bool | None = None


class PlatformCreate(BaseModel):
    """The human-approved plan. Everything is validated against the registry;
    core modules and dependencies are always added."""

    name: str = Field(..., min_length=1, max_length=120)
    brief: str | None = Field(default=None, max_length=4000)
    hazards: list[str] = Field(..., min_length=1)
    county: str | None = Field(default=None, max_length=20)
    towns: list[str] = Field(default_factory=list)
    modules: list[str] | None = None
    layers: list[str] | None = None
    report_categories: list[str] | None = None
    cluster_policy: ClusterPolicyInput | None = None
    configuration: dict | None = None
    publish: bool = True
    # optional stable public slug (/p/{slug}); a suffix is added if it is taken
    slug: str | None = Field(default=None, max_length=80, pattern=r"^[a-z0-9][a-z0-9-]*$")


class PlatformItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    name: str
    county: str | None = None
    towns: list[str] = Field(default_factory=list)
    hazards: list[str] = Field(default_factory=list)
    primary_hazard: str
    status: str
    modules: list[str] = Field(default_factory=list)
    layers: list[str] = Field(default_factory=list)
    center_lat: float | None = None
    center_lon: float | None = None
    created_at: datetime
    published_at: datetime | None = None


class ModuleConfigItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    module_id: str
    module_type: str
    enabled: bool
    config: dict


class PlatformDetail(PlatformItem):
    brief: str | None = None
    scenario: dict
    configuration: dict
    module_configs: list[ModuleConfigItem] = Field(default_factory=list)
    public_url: str
    console_url: str
    updated_at: datetime


class PlatformListResponse(BaseModel):
    items: list[PlatformItem]
    total: int


class PlatformStatusUpdate(BaseModel):
    status: str = Field(..., description="draft | published | archived")


class PlatformConfigUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    cluster_policy: ClusterPolicyInput | None = None
    configuration: dict | None = None
