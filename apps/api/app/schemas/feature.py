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
