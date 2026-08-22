"""Module package — importing it registers every built-in module exactly once."""
from __future__ import annotations

from app.modules import aidflow_modules
from app.modules.base import DOMAINS, ModuleNotFoundError, ModuleSpec
from app.modules.registry import registry

aidflow_modules.register()

__all__ = ["registry", "ModuleSpec", "ModuleNotFoundError", "DOMAINS"]
