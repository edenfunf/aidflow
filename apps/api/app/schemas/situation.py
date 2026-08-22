from __future__ import annotations

from pydantic import BaseModel, Field


class CountByKey(BaseModel):
    key: str
    label: str
    count: int


class TrendBucket(BaseModel):
    start: str
    reports: int
    cases_created: int
    cases_resolved: int


class SituationResponse(BaseModel):
    """Public situational picture for a platform — what the portal header and
    statistics blocks show."""

    platform_id: str
    slug: str
    name: str
    generated_at: str
    last_report_at: str | None = None
    last_update_at: str | None = None
    cases_total: int
    cases_open: int
    cases_pending: int
    cases_active: int
    cases_done: int
    cases_high_risk: int
    reports_total: int
    reports_last_hour: int
    reports_last_24h: int
    clusters_open: int
    trend_direction: str  # rising | falling | steady
    by_category: list[CountByKey]
    by_town: list[CountByKey]
    by_status: list[CountByKey]
    by_severity: list[CountByKey]
    trend: list[TrendBucket]


class ConsoleOverviewResponse(SituationResponse):
    """Console adds internal-only figures."""

    cases_new_last_hour: int = 0
    reports_unclustered: int = 0
    reports_rejected: int = 0
    median_dispatch_minutes: float | None = None
    median_resolve_minutes: float | None = None
    by_reporter_role: list[CountByKey] = Field(default_factory=list)


class GlobalOverviewResponse(BaseModel):
    platforms_total: int
    platforms_published: int
    cases_open: int
    cases_awaiting_dispatch: int
    cases_active: int
    reports_last_24h: int
