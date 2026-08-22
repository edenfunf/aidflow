"""In-memory module registry — the planner/console capability catalogue.

Registration order is preserved (dict insertion order), so listings and the
composed platform configuration are stable and predictable.
"""
from __future__ import annotations

from app.modules.base import ModuleNotFoundError, ModuleSpec


class ModuleRegistry:
    def __init__(self) -> None:
        self._modules: dict[str, ModuleSpec] = {}

    def register(self, spec: ModuleSpec) -> ModuleSpec:
        if spec.id in self._modules:
            raise ValueError(f"Duplicate module id: {spec.id}")
        if spec.module_type == "layer" and not spec.layer_key:
            raise ValueError(f"Layer module {spec.id} needs a layer_key")
        self._modules[spec.id] = spec
        return spec

    def get(self, module_id: str) -> ModuleSpec | None:
        return self._modules.get(module_id)

    def require(self, module_id: str) -> ModuleSpec:
        spec = self._modules.get(module_id)
        if spec is None:
            raise ModuleNotFoundError(module_id)
        return spec

    def all(self) -> list[ModuleSpec]:
        return list(self._modules.values())

    def layers(self) -> list[ModuleSpec]:
        return [m for m in self._modules.values() if m.module_type == "layer"]

    def layer_by_key(self, layer_key: str) -> ModuleSpec | None:
        for m in self._modules.values():
            if m.module_type == "layer" and m.layer_key == layer_key:
                return m
        return None

    def for_hazards(self, hazards: list[str] | tuple[str, ...]) -> list[ModuleSpec]:
        return [m for m in self._modules.values() if m.applies_to(hazards)]

    def core_ids(self) -> list[str]:
        return [m.id for m in self._modules.values() if m.core]

    def validate_ids(self, module_ids: list[str]) -> list[ModuleSpec]:
        """Resolve ids in order, de-duplicated; unknown ids raise."""
        out: list[ModuleSpec] = []
        seen: set[str] = set()
        for mid in module_ids:
            if mid in seen:
                continue
            seen.add(mid)
            out.append(self.require(mid))
        return out


registry = ModuleRegistry()
