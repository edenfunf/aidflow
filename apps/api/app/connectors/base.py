"""Shared connector plumbing.

A connector does exactly two things: fetch an official source (thin, optional,
credential-aware) and *normalise* its native records into ``GeoFeature``
dicts. Mapping is pure and deterministic so it is tested offline against
representative payloads; fetching is isolated so an upstream outage degrades
to a clear "unavailable" status instead of a broken map.
"""
from __future__ import annotations

import ssl
from typing import Any

import httpx

from app.core.config import settings


class ConnectorError(Exception):
    """A live call failed (network, HTTP error, unexpected payload)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class ConnectorDisabled(Exception):
    """The connector needs a credential / URL that is not configured."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _ssl_context() -> ssl.SSLContext:
    """Default verification, minus OpenSSL's *strict* X.509 profile: several
    Taiwanese government certificates omit the Subject Key Identifier and are
    rejected by the strict flag on Python ≥ 3.13 even though the chain is
    valid. Chain + hostname verification stay fully enabled."""
    ctx = ssl.create_default_context()
    strict = getattr(ssl, "VERIFY_X509_STRICT", 0)
    if strict:
        ctx.verify_flags &= ~strict
    return ctx


_CTX = _ssl_context()


def http_get(url: str, *, params: dict | None = None, timeout: float | None = None) -> httpx.Response:
    try:
        resp = httpx.get(
            url,
            params=params,
            timeout=timeout or settings.OFFICIAL_DATA_TIMEOUT_SECONDS,
            follow_redirects=True,
            verify=_CTX,
            headers={"User-Agent": "AidFlow/1.0 (+disaster platform; open data client)"},
        )
    except httpx.HTTPError as exc:
        raise ConnectorError(f"連線失敗：{exc.__class__.__name__}") from exc
    if resp.status_code >= 400:
        raise ConnectorError(f"上游回應 HTTP {resp.status_code}")
    return resp


def http_get_json(url: str, *, params: dict | None = None, timeout: float | None = None) -> Any:
    resp = http_get(url, params=params, timeout=timeout)
    try:
        return resp.json()
    except ValueError as exc:
        raise ConnectorError("上游回應不是有效的 JSON") from exc


def to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        f = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return f


def valid_point(lat: float | None, lon: float | None) -> bool:
    return (
        lat is not None and lon is not None
        and 21.5 <= lat <= 26.5 and 118.0 <= lon <= 122.5
    )


def feature(
    *,
    id: str,
    source: str,
    layer: str,
    lat: float,
    lon: float,
    properties: dict,
) -> dict:
    return {
        "id": id,
        "source": source,
        "layer": layer,
        "type": "Point",
        "coordinates": [round(lon, 6), round(lat, 6)],
        "properties": properties,
    }


def polygon_feature(*, id: str, source: str, layer: str, rings: list, properties: dict) -> dict:
    return {
        "id": id,
        "source": source,
        "layer": layer,
        "type": "Polygon",
        "coordinates": rings,
        "properties": properties,
    }


def norm_admin(text: str | None) -> str:
    return (text or "").replace("臺", "台").strip()


def matches_county(text: str | None, county: str | None) -> bool:
    """True when no county filter is given, or ``text`` mentions the county."""
    if not county:
        return True
    return norm_admin(county) in norm_admin(text)
