"""Official open-data connectors — each normalises one government source into
the unified GeoFeature shape (see app/schemas/feature.py) — plus the outbound
channels: LINE (staff group), e-mail (reporters) and EMIC (上報)."""
from __future__ import annotations

from app.connectors import cwa, emic, line, mailer, moi_shelters, nantou_open_data, ncdr, wra

__all__ = ["cwa", "emic", "line", "mailer", "moi_shelters", "nantou_open_data", "ncdr", "wra"]
