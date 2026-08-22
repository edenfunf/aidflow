"""Unified map feature schema. Every official API is normalised into this
shape by its connector, so the frontend never sees a government schema."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class GeoFeature(BaseModel):
    id: str
    source: str
    layer: str
    type: Literal["Point", "Polygon", "LineString", "Raster"] = "Point"
    coordinates: list = Field(..., description="[lon, lat] for Point (GeoJSON order)")
    properties: dict = Field(default_factory=dict)


class LayerResponse(BaseModel):
    layer: str
    source: str
    # ok | disabled (no credential) | unavailable (upstream failed) | not_enabled | unsupported
    status: str
    detail: str | None = None
    attribution: str | None = None
    fetched_at: str | None = None
    cached: bool = False
    count: int = 0
    features: list[GeoFeature] = Field(default_factory=list)


class LayerStatusItem(BaseModel):
    layer: str
    module_id: str
    name: str
    kind: str  # internal | official
    source: str | None = None
    status: str
    detail: str | None = None


class LayerStatusResponse(BaseModel):
    items: list[LayerStatusItem]


class MapFeatureCollection(BaseModel):
    """GeoJSON FeatureCollection for the internal layers (cases / clusters /
    reports)."""

    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[dict]
    generated_at: str


class VehicleItem(BaseModel):
    vehicle_id: str
    kind: str
    kind_label: str
    unit_name: str | None = None
    unit_kind: str | None = None
    case_id: str | None = None
    case_number: str | None = None
    case_title: str | None = None
    assignment_id: str | None = None
    route_source: str | None = None
    lat: float
    lon: float
    heading: float | None = None
    # preparing | en_route | on_site | returning | live
    status: str
    progress: float | None = None
    eta_minutes: int | None = None
    # simulated | avl
    source: str
    recorded_at: str | None = None
    # demo platforms: the trip is being replayed because the case is still 前往中
    replay: bool = False


class VehicleListResponse(BaseModel):
    items: list[VehicleItem]
    generated_at: str
    has_live: bool


class AvlPosition(BaseModel):
    vehicle_id: str = Field(..., min_length=1, max_length=64)
    unit_id: str | None = None
    kind: str = Field(default="works_truck")
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    heading: float | None = Field(default=None, ge=0, le=360)
    speed_kmh: float | None = Field(default=None, ge=0)
    case_id: str | None = None
    recorded_at: str | None = None
    payload: dict = Field(default_factory=dict)


class AvlIngestRequest(BaseModel):
    positions: list[AvlPosition] = Field(..., min_length=1, max_length=500)
