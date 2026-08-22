"""Module registry catalogue + connector status."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.modules import DOMAINS, registry
from app.modules.base import ModuleSpec
from app.schemas.module import (
    ConnectorListResponse,
    ConnectorStatusItem,
    DomainItem,
    DomainListResponse,
    ModuleListResponse,
    ModuleSpecItem,
)
from app.services import official_data_service

router = APIRouter(prefix="/v1", tags=["modules"])


def _item(spec: ModuleSpec) -> ModuleSpecItem:
    return ModuleSpecItem(
        id=spec.id, name=spec.name, description=spec.description, domain=spec.domain,
        domain_label=DOMAINS.get(spec.domain, spec.domain), module_type=spec.module_type,
        surfaces=list(spec.surfaces), applicable_hazards=list(spec.applicable_hazards),
        default_enabled=spec.default_enabled, core=spec.core, implemented=spec.implemented,
        dependencies=list(spec.dependencies), layer_key=spec.layer_key, source=spec.source,
        default_config=dict(spec.default_config),
    )


@router.get("/modules", response_model=ModuleListResponse, summary="Module registry")
def list_modules(
    hazard: str | None = Query(default=None),
    domain: str | None = Query(default=None),
    module_type: str | None = Query(default=None),
) -> ModuleListResponse:
    specs = registry.for_hazards([hazard]) if hazard else registry.all()
    if domain:
        specs = [s for s in specs if s.domain == domain]
    if module_type:
        specs = [s for s in specs if s.module_type == module_type]
    return ModuleListResponse(items=[_item(s) for s in specs], total=len(specs))


@router.get("/modules/domains", response_model=DomainListResponse, summary="AidFlow domains")
def list_domains() -> DomainListResponse:
    counts = {k: 0 for k in DOMAINS}
    for s in registry.all():
        counts[s.domain] = counts.get(s.domain, 0) + 1
    return DomainListResponse(items=[DomainItem(key=k, label=v, count=counts.get(k, 0)) for k, v in DOMAINS.items()])


@router.get("/modules/{module_id}", response_model=ModuleSpecItem, summary="Module spec")
def get_module(module_id: str) -> ModuleSpecItem:
    spec = registry.get(module_id)
    if spec is None:
        raise HTTPException(status_code=404, detail="Unknown module")
    return _item(spec)


@router.get("/connectors", response_model=ConnectorListResponse, summary="Official data connectors and their status", tags=["connectors"])
def list_connectors() -> ConnectorListResponse:
    return ConnectorListResponse(items=[ConnectorStatusItem(**c) for c in official_data_service.connector_statuses()])
