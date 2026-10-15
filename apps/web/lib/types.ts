// API types mirroring the AidFlow backend (apps/api/app/schemas).

export type Severity = "low" | "medium" | "high" | "critical";
export type Phase = "pending" | "active" | "community" | "done" | "dismissed";
export type CaseStatus =
  | "pending_review"
  | "reported_emic"
  | "emic_processing"
  | "community_open"
  | "community_submitted"
  | "closed"
  | "dismissed";
export type CaseTrack = "emic" | "community";

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
  /** 審核中 */
  cases_pending: number;
  /** 已上報 EMIC／處理中 */
  cases_active: number;
  /** 開放民眾協助（含處理完成確認中） */
  cases_community: number;
  cases_community_submitted: number;
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
  /** open cases per severity tier — always critical, high, medium, low */
  by_severity: CountByKey[];
  trend: TrendBucket[];
}

export interface ConsoleOverview extends Situation {
  cases_new_last_hour: number;
  reports_unclustered: number;
  reports_rejected: number;
  reports_subscribed: number;
  median_review_minutes: number | null;
  median_close_minutes: number | null;
  pending_by_severity: CountByKey[];
  by_reporter_role: CountByKey[];
}

export interface GlobalOverview {
  platforms_total: number;
  platforms_published: number;
  cases_open: number;
  cases_pending_review: number;
  cases_active: number;
  cases_community: number;
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
  track: CaseTrack | null;
  track_label: string | null;
  lat: number;
  lon: number;
  town: string | null;
  location_label: string | null;
  report_count: number;
  unique_reporter_count: number;
  /** 處理單位 as recorded in EMIC */
  assigned_unit: string | null;
  /** EMIC 處理狀態文字（公開） */
  emic_status: string | null;
  public_summary: string | null;
  created_at: string;
  updated_at: string;
  reviewed_at: string | null;
  closed_at: string | null;
}

export interface CaseItem extends PublicCase {
  platform_id: string;
  cluster_id: string | null;
  reviewed_by: string | null;
  emic_case_no: string | null;
  emic_channel: "manual" | "api" | null;
  emic_reported_at: string | null;
  emic_synced_at: string | null;
  community_submitted_at: string | null;
  threshold_reached_at: string | null;
  resolved_at: string | null;
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
  /** 開放民眾協助處理中 — the portal shows the 「我來協助處理」 button */
  can_assist: boolean;
}

export interface CommunitySubmitResponse {
  case: PublicCase;
  photos: number;
  message: string;
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
  /** personal data: null unless the viewer's role holds view_pii */
  reporter_name: string | null;
  reporter_contact: string | null;
  reporter_email: string | null;
  pii_hidden: boolean;
  notify_opt_in: boolean;
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
  label: string;
  from_status: string | null;
  to_status: string | null;
  to_status_label: string | null;
  actor_role: string;
  actor_name: string | null;
  note: string | null;
  public: boolean;
  created_at: string;
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

export interface EmicInfo {
  mode: "manual" | "api";
  field_map: { key: string; label: string; source: string }[];
  status_suggestions: string[];
}

export interface CaseDetail {
  case: CaseItem;
  reports: ReportInternal[];
  events: CaseEventItem[];
  photos: PhotoItem[];
  nearby: NearbyCase[];
  reporter_roles: Record<string, number>;
  emic: EmicInfo;
  pii_visible: boolean;
}

export type ReviewDecision = "emic" | "community" | "dismiss";

export interface CaseActionResponse {
  case: CaseItem;
  result?: { decision?: ReviewDecision; mode?: string; submitted?: boolean; detail?: string | null } | null;
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
  reporter_email?: string | null;
  notify_opt_in?: boolean;
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
  notify_opt_in: boolean;
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
  embed_url: string;
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
  aggregate_id?: string | null;
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

// ── platform creation (災害名稱 → 平台) ─────────────────────────────────
export interface PlatformDraft {
  name: string;
  hazards: string[];
  county: string | null;
  towns: string[];
  report_categories?: string[] | null;
  cluster_policy?: Partial<ClusterPolicy> | null;
  configuration?: Record<string, any> | null;
  publish: boolean;
}

export interface PlatformOptions {
  hazards: { key: string; label: string }[];
  regions: { county: string; towns: string[] }[];
}

export interface PlatformPreview {
  detected_hazards: string[];
  hazards: string[];
  hazard_labels: string[];
  report_categories: ReportCategory[];
  layers: string[];
  modules: string[];
  suggested_name: string;
}

// ── auth ───────────────────────────────────────────────────────────────
export type Role = "officer" | "supervisor" | "admin";
export type Permission = "view_console" | "review_cases" | "view_pii" | "manage_platforms" | "manage_line" | "manage_users" | "view_audit";

export interface Me {
  kind: "user" | "service" | "dev";
  id: string | null;
  username: string | null;
  display_name: string;
  role: Role | null;
  role_label: string;
  permissions: Permission[];
  must_change_password: boolean;
}

export interface LoginResponse {
  token: string;
  expires_at: string;
  user: Me;
}

export interface UserItem {
  id: string;
  username: string;
  display_name: string;
  role: Role;
  role_label: string;
  active: boolean;
  locked: boolean;
  must_change_password: boolean;
  last_login_at: string | null;
  created_at: string;
}

// ── LINE group / notifications ─────────────────────────────────────────
export interface LineStatus {
  token_configured: boolean;
  webhook_enabled: boolean;
  bound: boolean;
  group_id_masked: string | null;
  bound_at: string | null;
  /** only for roles that may bind groups */
  bind_code: string | null;
  webhook_path: string;
}

export interface NotificationLogItem {
  id: string;
  channel: "line" | "email";
  kind: string;
  recipient: string | null;
  status: "sent" | "simulated" | "failed" | "skipped" | "queued";
  detail: string | null;
  case_id: string | null;
  created_at: string;
}

export interface HealthResponse {
  status: string;
  service: string;
  auth_required: boolean;
  // operational detail: only returned to a signed-in console user
  version?: string;
  demo_mode?: boolean;
  channels?: { line: boolean; email: boolean; emic: "manual" | "api" };
}
