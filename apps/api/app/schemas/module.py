from __future__ import annotations

from pydantic import BaseModel


class ModuleSpecItem(BaseModel):
    id: str
    name: str
    description: str
    domain: str
    domain_label: str
    module_type: str
    surfaces: list[str]
    applicable_hazards: list[str]
    default_enabled: bool
    core: bool
    implemented: bool
    dependencies: list[str]
    layer_key: str | None = None
    source: str | None = None
    default_config: dict


class ModuleListResponse(BaseModel):
    items: list[ModuleSpecItem]
    total: int


class DomainItem(BaseModel):
    key: str
    label: str
    count: int


class DomainListResponse(BaseModel):
    items: list[DomainItem]


class ConnectorStatusItem(BaseModel):
    id: str
    name: str
    provider: str
    homepage: str
    description: str
    layers: list[str]
    requires_key: bool
    key_env: str | None = None
    live_enabled: bool
    status: str  # ready | disabled
    detail: str | None = None


class ConnectorListResponse(BaseModel):
    items: list[ConnectorStatusItem]
