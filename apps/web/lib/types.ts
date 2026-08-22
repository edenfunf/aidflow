// API types mirroring the AidFlow backend (apps/api/app/schemas).

export type Severity = "low" | "medium" | "high" | "critical";
export type Phase = "pending" | "active" | "done" | "dismissed";
export type CaseStatus =
  | "reported"
  | "verifying"
  | "threshold_reached"
  | "awaiting_dispatch"
  | "assigned"
  | "en_route"
  | "on_site"
  | "processing"
  | "resolved"
  | "closed"
  | "dismissed";

export interface ReportCategory {
  key: string;
  label: string;
  default_severity: Severity;
}

export interface ReporterRole {
  key: string;
  label: string;
}

export interface PublicPlatform {
  id: string;
  slug: string;
  name: string;
  status: string;
  county: string | null;
  towns: string[];
  hazards: string[];
  hazard_labels: string[];
  primary_hazard: string;
  report_categories: ReportCategory[];
  reporter_roles: ReporterRole[];
  modules: string[];
  layers: string[];
  map: { center: [number, number]; zoom: number };
  cluster_policy: {
    required_unique_reporters: number | null;
    radius_meters: number | null;
    time_window_minutes: number | null;
  };
  contacts: { name: string; phone: string }[];
  town_centers?: Record<string, { lat: number; lon: number }>;
  published_at: string | null;
}

export interface CountByKey {
  key: string;
  label: string;
  count: number;
}

export interface TrendBucket {
  start: string;
  reports: number;
  cases_created: number;
  cases_resolved: number;
}

export interface Situation {
  platform_id: string;
  slug: string;
  name: string;
  generated_at: string;
  last_report_at: string | null;
  last_update_at: string | null;
  cases_total: number;
  cases_open: number;
  cases_pending: number;
  cases_active: number;
  cases_done: number;
  cases_high_risk: number;
  reports_total: number;
  reports_last_hour: number;
  reports_last_24h: number;
  clusters_open: number;
  trend_direction: "rising" | "falling" | "steady";
  by_category: CountByKey[];
  by_town: CountByKey[];
  by_status: CountByKey[];
  by_severity: CountByKey[];
  trend: TrendBucket[];
}

export interface ConsoleOverview extends Situation {
  cases_new_last_hour: number;
  reports_unclustered: number;
  reports_rejected: number;
  median_dispatch_minutes: number | null;
  median_resolve_minutes: number | null;
  by_reporter_role: CountByKey[];
}

export interface GlobalOverview {
  platforms_total: number;
  platforms_published: number;
  cases_open: number;
  cases_awaiting_dispatch: number;
  cases_active: number;
  reports_last_24h: number;
}

export interface PublicCase {
  id: string;
  case_number: string;
  title: string;
  category: string;
  category_label: string;
  severity: Severity;
  status: CaseStatus;
  status_label: string;
  phase: Phase;
  lat: number;
  lon: number;
  town: string | null;
  location_label: string | null;
  report_count: number;
  unique_reporter_count: number;
  assigned_unit: string | null;
  public_summary: string | null;
  created_at: string;
  updated_at: string;
  dispatched_at: string | null;
  resolved_at: string | null;
}

export interface CaseItem extends PublicCase {
  platform_id: string;
  cluster_id: string | null;
  threshold_reached_at: string | null;
  closed_at: string | null;
  next_statuses: CaseStatus[];
}

export interface PublicTimelineItem {
  event_type: string;
  label: string;
  note: string | null;
  to_status: CaseStatus | null;
  at: string;
}

export interface ProgressStep {
  key: CaseStatus;
  label: string;
  reached: boolean;
  current: boolean;
  at: string | null;
}

export interface ReportPublic {
  report_id: string;
  category: string;
  severity: Severity;
  status: string;
  town: string | null;
  location_label: string | null;
  description: string | null;
  reporter_role: string;
  photo_count: number;
  case_id: string | null;
  cluster_id: string | null;
  created_at: string | null;
  lat: number | null;
  lon: number | null;
}

export interface PhotoItem {
  id: string;
  report_id: string | null;
  case_id: string | null;
  kind: "scene" | "before" | "after";
  source: "citizen" | "agency";
  content_type: string;
  size_bytes: number;
  caption: string | null;
  url: string;
  created_at: string;
}

export interface PublicCaseDetail {
  case: PublicCase;
  timeline: PublicTimelineItem[];
  reports: ReportPublic[];
  photos: PhotoItem[];
  progress: ProgressStep[];
}

export interface ReportInternal {
  id: string;
  platform_id: string;
  category: string;
  description: string | null;
  severity: Severity;
  triage_severity: Severity;
  lat: number | null;
  lon: number | null;
  town: string | null;
  address: string | null;
  reporter_role: string;
  reporter_name: string | null;
  reporter_contact: string | null;
  has_identity: boolean;
  status: string;
  cluster_id: string | null;
  case_id: string | null;
  photo_count: number;
  source: string;
  created_at: string;
  updated_at: string;
}

export interface CaseEventItem {
  id: string;
  event_type: string;
  from_status: string | null;
  to_status: string | null;
  to_status_label: string | null;
  actor_role: string;
  actor_name: string | null;
  note: string | null;
  public: boolean;
  created_at: string;
}

export interface AssignmentItem {
  id: string;
  unit_name: string;
  team_lead: string | null;
  contact: string | null;
  note: string | null;
  status: string;
  unit_id?: string | null;
  route_source?: string | null;
  distance_m?: number | null;
  eta_minutes?: number | null;
  vehicles?: { vehicle_id: string; kind: VehicleKind }[];
  notified_via?: string | null;
  notified_at?: string | null;
  departed_at?: string | null;
  created_at: string;
}

export type VehicleKind = "fire_engine" | "ambulance" | "police_car" | "works_truck";
export type UnitKind = "fire" | "police" | "town_office" | "highway" | "river" | "slope" | "power" | "water_supply";

export interface ResponderUnit {
  id: string;
  name: string;
  kind: UnitKind;
  kind_label: string;
  town: string | null;
  lat: number;
  lon: number;
  address: string | null;
  phone: string | null;
  location_source: "open_data" | "configured" | "indicative";
  source: string | null;
}

export interface ResponderSuggestion {
  unit: ResponderUnit;
  kind_rank: number;
  primary: boolean;
  straight_m: number;
  vehicles: { kind: VehicleKind; label: string }[];
  distance_m: number | null;
  eta_minutes: number | null;
  route_source: "osrm" | "straight_line" | null;
  route: { type: "LineString"; coordinates: [number, number][] } | null;
}

export interface DispatchResponse {
  case: CaseItem;
  assignment: AssignmentItem;
  notification: { channel: string; status: string; detail: string | null; external_ref: string | null };
}

export interface VehicleItem {
  vehicle_id: string;
  kind: VehicleKind;
  kind_label: string;
  unit_name: string | null;
  unit_kind: UnitKind | null;
  case_id: string | null;
  case_number: string | null;
  case_title: string | null;
  assignment_id: string | null;
  route_source: string | null;
  lat: number;
  lon: number;
  heading: number | null;
  status: "preparing" | "en_route" | "on_site" | "returning" | "live";
  progress: number | null;
  eta_minutes: number | null;
  source: "simulated" | "avl";
  recorded_at: string | null;
  replay?: boolean;
}

export interface VehicleListResponse {
  items: VehicleItem[];
  generated_at: string;
  has_live: boolean;
}

export interface RouteFeature {
  type: "Feature";
  id: string;
  geometry: { type: "LineString"; coordinates: [number, number][] };
  properties: {
    assignment_id: string;
    case_id: string;
    case_number: string;
    unit_name: string;
    unit_kind: UnitKind | null;
    distance_m: number | null;
    eta_minutes: number | null;
    route_source: string | null;
    case_status: CaseStatus;
    vehicles: VehicleKind[];
  };
}

export interface RouteCollection {
  type: "FeatureCollection";
  features: RouteFeature[];
  generated_at: string;
}

export interface NearbyCase {
  id: string;
  case_number: string;
  title: string;
  category: string;
  severity: Severity;
  status: CaseStatus;
  distance_m: number;
}

export interface CaseDetail {
  case: CaseItem;
  reports: ReportInternal[];
  assignments: AssignmentItem[];
  events: CaseEventItem[];
  photos: PhotoItem[];
  nearby: NearbyCase[];
  reporter_roles: Record<string, number>;
}

export interface SubmitReportPayload {
  category: string;
  description?: string | null;
  severity?: Severity | null;
  lat?: number | null;
  lon?: number | null;
  address?: string | null;
  town?: string | null;
  reporter_role: string;
  reporter_name?: string | null;
  reporter_contact?: string | null;
  client_key?: string | null;
}

export interface SubmitReportResponse {
  report_id: string;
  status: string;
  cluster_id: string | null;
  case_id: string | null;
  case_number: string | null;
  case_created: boolean;
  unique_reporters: number;
  required_unique_reporters: number;
  message: string;
}

// ── map ────────────────────────────────────────────────────────────────
export interface MapFeature {
  type: "Feature";
  id: string;
  geometry: { type: "Point"; coordinates: [number, number] };
  properties: Record<string, any> & { layer: "incident_cases" | "report_clusters" | "citizen_reports" };
}

export interface MapFeatureCollection {
  type: "FeatureCollection";
  features: MapFeature[];
  generated_at: string;
}

export interface GeoFeature {
  id: string;
  source: string;
  layer: string;
  type: "Point" | "Polygon" | "LineString" | "Raster";
  coordinates: any;
  properties: Record<string, any>;
}

export interface LayerResponse {
  layer: string;
  source: string;
  status: "ok" | "disabled" | "unavailable" | "not_enabled" | "unsupported";
  detail: string | null;
  attribution: string | null;
  fetched_at: string | null;
  cached: boolean;
  count: number;
  features: GeoFeature[];
}

export interface LayerStatusItem {
  layer: string;
  module_id: string;
  name: string;
  kind: "internal" | "official";
  source: string | null;
  status: string;
  detail: string | null;
}

// ── platforms / console ────────────────────────────────────────────────
export interface PlatformItem {
  id: string;
  slug: string;
  name: string;
  county: string | null;
  towns: string[];
  hazards: string[];
  primary_hazard: string;
  status: "draft" | "published" | "archived";
  modules: string[];
  layers: string[];
  center_lat: number | null;
  center_lon: number | null;
  created_at: string;
  published_at: string | null;
}

export interface ModuleConfigItem {
  module_id: string;
  module_type: string;
  enabled: boolean;
  config: Record<string, any>;
}

export interface PlatformDetail extends PlatformItem {
  brief: string | null;
  scenario: Record<string, any>;
  configuration: Record<string, any> & {
    cluster_policy?: ClusterPolicy;
    map?: { center: [number, number]; zoom: number };
    hazard_labels?: string[];
  };
  module_configs: ModuleConfigItem[];
  public_url: string;
  console_url: string;
  updated_at: string;
}

export interface ClusterPolicy {
  required_unique_reporters: number;
  radius_meters: number;
  time_window_minutes: number;
  count_anonymous_reporters?: boolean;
}

export interface ClusterRow {
  cluster_id: string;
  category: string;
  category_label: string;
  severity: Severity;
  status: string;
  town: string | null;
  report_count: number;
  unique_reporter_count: number;
  case_id: string | null;
  first_reported_at: string | null;
  last_reported_at: string | null;
  lat: number;
  lon: number;
}

export interface AuditEvent {
  id: string;
  event_type: string;
  aggregate_id: string | null;
  payload: Record<string, any>;
  created_at: string;
}

// ── modules / connectors ───────────────────────────────────────────────
export interface ModuleSpecItem {
  id: string;
  name: string;
  description: string;
  domain: string;
  domain_label: string;
  module_type: "feature" | "layer" | "processor" | "action" | "connector";
  surfaces: string[];
  applicable_hazards: string[];
  default_enabled: boolean;
  core: boolean;
  implemented: boolean;
  dependencies: string[];
  layer_key: string | null;
  source: string | null;
  default_config: Record<string, any>;
}

export interface DomainItem {
  key: string;
  label: string;
  count: number;
}

export interface ConnectorStatusItem {
  id: string;
  name: string;
  provider: string;
  homepage: string;
  description: string;
  layers: string[];
  requires_key: boolean;
  key_env: string | null;
  live_enabled: boolean;
  status: "ready" | "disabled";
  detail: string | null;
}

// ── agent ──────────────────────────────────────────────────────────────
export interface ScenarioAnalysis {
  region: { county: string | null; towns: string[] };
  hazards: string[];
  hazard_labels: string[];
  impacts: string[];
  impact_labels: string[];
  reporter_roles: string[];
  data_needs: string[];
  summary: string;
}

export interface ModuleSuggestion {
  id: string;
  name: string;
  description: string;
  domain: string;
  domain_label: string;
  module_type: string;
  recommended: boolean;
  core: boolean;
  implemented: boolean;
  reason: string;
}

export interface LayerSuggestion {
  key: string;
  module_id: string;
  name: string;
  description: string;
  recommended: boolean;
  core: boolean;
  source: string | null;
  live: boolean | null;
  reason: string;
}

export interface CategorySuggestion {
  key: string;
  label: string;
  default_severity: Severity;
  recommended: boolean;
}

export interface PlatformDraft {
  name: string;
  brief: string | null;
  hazards: string[];
  county: string | null;
  towns: string[];
  modules: string[] | null;
  layers: string[] | null;
  report_categories: string[] | null;
  cluster_policy: Partial<ClusterPolicy> | null;
  configuration?: Record<string, any> | null;
  publish: boolean;
}

export interface AgentPlan {
  scenario: ScenarioAnalysis;
  suggested_name: string;
  suggested_modules: ModuleSuggestion[];
  suggested_layers: LayerSuggestion[];
  suggested_report_categories: CategorySuggestion[];
  suggested_cluster_policy: Partial<ClusterPolicy>;
  suggested_workflow: { step: string; label: string; detail: string }[];
  reasons: string[];
  intent_mode: "ai" | "rules";
  ai_enabled: boolean;
  note: string | null;
  draft: PlatformDraft;
}

export interface AgentExecuteResponse {
  platform: PlatformDetail;
  public_url: string;
  console_url: string;
  enabled_modules: number;
  enabled_layers: number;
  /** demo mode: platforms retired so test runs don't pile up */
  retired: string[];
}

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
  ai_enabled: boolean;
  demo_mode: boolean;
  api_key_required: boolean;
}
