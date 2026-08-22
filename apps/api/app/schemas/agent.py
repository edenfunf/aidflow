from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.platform import ClusterPolicyInput, PlatformCreate, PlatformDetail


class AgentPlanRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000, description="災害背景描述")


class ScenarioRegion(BaseModel):
    county: str | None = None
    towns: list[str] = Field(default_factory=list)


class ScenarioAnalysis(BaseModel):
    region: ScenarioRegion
    hazards: list[str]
    hazard_labels: list[str]
    # impacts the brief mentioned, as report category keys
    impacts: list[str]
    impact_labels: list[str]
    reporter_roles: list[str]
    data_needs: list[str]
    summary: str


class ModuleSuggestion(BaseModel):
    id: str
    name: str
    description: str
    domain: str
    domain_label: str
    module_type: str
    recommended: bool
    core: bool
    implemented: bool
    reason: str


class LayerSuggestion(BaseModel):
    key: str
    module_id: str
    name: str
    description: str
    recommended: bool
    core: bool
    source: str | None = None
    live: bool | None = None
    reason: str


class CategorySuggestion(BaseModel):
    key: str
    label: str
    default_severity: str
    recommended: bool


class AgentPlanResponse(BaseModel):
    scenario: ScenarioAnalysis
    suggested_name: str
    suggested_modules: list[ModuleSuggestion]
    suggested_layers: list[LayerSuggestion]
    suggested_report_categories: list[CategorySuggestion]
    suggested_cluster_policy: ClusterPolicyInput
    suggested_workflow: list[dict]
    reasons: list[str]
    intent_mode: str  # ai | rules
    ai_enabled: bool
    note: str | None = None
    # a ready-to-send execute payload (the human edits then approves it)
    draft: PlatformCreate


class AgentExecuteRequest(PlatformCreate):
    """The approved plan. Same shape as PlatformCreate."""


class AgentExecuteResponse(BaseModel):
    platform: PlatformDetail
    public_url: str
    console_url: str
    enabled_modules: int
    enabled_layers: int
    # 示範模式下自動退場的舊平台（避免測試平台累積）
    retired: list[str] = []
