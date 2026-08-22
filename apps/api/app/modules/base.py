"""Module contract for the AidFlow capability registry.

A *module* is a reusable, deterministic building block of a disaster
platform. The agent planner only *suggests* module ids; the platform composer
turns an approved selection into a Platform + PlatformModuleConfig rows, and
the public portal / console render whatever the platform has enabled.

Module types:
  - feature    — a capability surfaced in the UI (report form, timeline, …)
  - layer      — a map layer (citizen reports, clusters, official data …)
  - processor  — a deterministic engine that runs on the report pipeline
  - action     — an outbound side effect (LINE notify)
  - connector  — an official open-data source feeding one or more layers
"""
from __future__ import annotations

from dataclasses import dataclass, field

# the AidFlow domains
DOMAINS: dict[str, str] = {
    "reporting": "災情通報",
    "processing": "案件處理",
    "dispatch": "派工調度",
    "visualization": "災情視覺化",
    "official_data": "官方資料",
    "notification": "通知推播",
    "privacy": "隱私保護",
    "public_transparency": "公開透明",
    "analytics": "統計分析",
}

MODULE_TYPES = ("feature", "layer", "processor", "action", "connector")
SURFACES = ("public", "console")


@dataclass(frozen=True)
class ModuleSpec:
    id: str
    name: str
    description: str
    domain: str
    module_type: str = "feature"
    surfaces: tuple[str, ...] = ("public", "console")
    # hazard keys this module is relevant for ("*" = every hazard)
    applicable_hazards: tuple[str, ...] = ("*",)
    # suggested by default for applicable hazards
    default_enabled: bool = True
    # core modules cannot be switched off — the platform would not function
    core: bool = False
    implemented: bool = True
    dependencies: tuple[str, ...] = ()
    # for layers: the layer key the frontend + feature service use
    layer_key: str | None = None
    # for official layers: the connector module id that feeds it
    source: str | None = None
    default_config: dict = field(default_factory=dict)

    def applies_to(self, hazards: list[str] | tuple[str, ...]) -> bool:
        if "*" in self.applicable_hazards:
            return True
        return any(h in self.applicable_hazards for h in hazards)


class ModuleNotFoundError(Exception):
    def __init__(self, module_id: str) -> None:
        super().__init__(f"Unknown module: {module_id}")
        self.module_id = module_id
