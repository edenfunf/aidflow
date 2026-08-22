// API client. Base URL from NEXT_PUBLIC_API_BASE_URL, falling back to
// api.<same-domain> on deployed hosts and localhost:8000 in development.
// Console calls attach X-API-Key from localStorage when the operator set one.

import type {
  AgentExecuteResponse,
  AgentPlan,
  AuditEvent,
  CaseDetail,
  CaseItem,
  CaseStatus,
  ClusterRow,
  DispatchResponse,
  ResponderSuggestion,
  ResponderUnit,
  RouteCollection,
  VehicleListResponse,
  ConnectorStatusItem,
  ConsoleOverview,
  DomainItem,
  GlobalOverview,
  HealthResponse,
  LayerResponse,
  LayerStatusItem,
  MapFeatureCollection,
  ModuleSpecItem,
  PhotoItem,
  PlatformDetail,
  PlatformDraft,
  PlatformItem,
  PublicCase,
  PublicCaseDetail,
  PublicPlatform,
  ReportInternal,
  ReportPublic,
  Situation,
  SubmitReportPayload,
  SubmitReportResponse,
} from "./types";

function resolveApiBase(): string {
  if (process.env.NEXT_PUBLIC_API_BASE_URL) return process.env.NEXT_PUBLIC_API_BASE_URL;
  if (typeof window !== "undefined") {
    const host = window.location.hostname;
    if (host !== "localhost" && host !== "127.0.0.1") {
      return `${window.location.protocol}//api.${host.replace(/^www\./, "")}`;
    }
  }
  return "http://localhost:8000";
}

export const API_BASE = resolveApiBase().replace(/\/$/, "");

const API_KEY_STORAGE = "aidflow.apiKey";

export function getApiKey(): string {
  if (typeof window === "undefined") return "";
  try {
    return window.localStorage.getItem(API_KEY_STORAGE) || "";
  } catch {
    return "";
  }
}

export function setApiKey(value: string): void {
  try {
    if (value) window.localStorage.setItem(API_KEY_STORAGE, value);
    else window.localStorage.removeItem(API_KEY_STORAGE);
  } catch {
    /* storage unavailable */
  }
}

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(path: string, init?: RequestInit & { rawBody?: boolean }): Promise<T> {
  const headers: Record<string, string> = { ...((init?.headers as Record<string, string>) || {}) };
  if (init?.body && !init.rawBody && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
  const key = getApiKey();
  if (key && !path.startsWith("/v1/public")) headers["X-API-Key"] = key;

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, { ...init, headers, cache: "no-store" });
  } catch (err) {
    throw new ApiError(0, `無法連線到 API（${API_BASE}），請確認後端是否啟動。`, err);
  }
  if (!res.ok) {
    let detail: unknown = `${res.status} ${res.statusText}`;
    let message = String(detail);
    try {
      const body = await res.json();
      detail = body?.detail ?? body;
      message =
        typeof body?.detail === "string"
          ? body.detail
          : body?.detail?.message || JSON.stringify(body?.detail ?? body);
    } catch {
      /* non-JSON error */
    }
    throw new ApiError(res.status, message, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

function qs(params: Record<string, string | number | boolean | undefined | null>): string {
  const search = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") search.set(k, String(v));
  }
  const s = search.toString();
  return s ? `?${s}` : "";
}

export const api = {
  health: () => request<HealthResponse>("/v1/health"),
  overview: () => request<GlobalOverview>("/v1/overview"),

  // ── public portal ──
  publicPlatforms: () => request<{ items: PublicPlatform[]; total: number }>("/v1/public/platforms"),
  publicPlatform: (slug: string) => request<PublicPlatform>(`/v1/public/platforms/${encodeURIComponent(slug)}`),
  situation: (slug: string) => request<Situation>(`/v1/public/platforms/${encodeURIComponent(slug)}/situation`),
  publicMap: (slug: string, params: { since_hours?: number; include_reports?: boolean } = {}) =>
    request<MapFeatureCollection>(`/v1/public/platforms/${encodeURIComponent(slug)}/map${qs(params)}`),
  publicCases: (
    slug: string,
    params: {
      phase?: string;
      status?: string;
      category?: string;
      town?: string;
      severity?: string;
      since_hours?: number;
      sort?: string;
      limit?: number;
      offset?: number;
    } = {}
  ) => request<{ items: PublicCase[]; total: number }>(`/v1/public/platforms/${encodeURIComponent(slug)}/cases${qs(params)}`),
  publicCase: (slug: string, caseId: string) =>
    request<PublicCaseDetail>(`/v1/public/platforms/${encodeURIComponent(slug)}/cases/${caseId}`),
  publicReports: (slug: string, params: { limit?: number; category?: string; town?: string } = {}) =>
    request<{ items: ReportPublic[]; total: number }>(`/v1/public/platforms/${encodeURIComponent(slug)}/reports${qs(params)}`),
  submitReport: (slug: string, payload: SubmitReportPayload) =>
    request<SubmitReportResponse>(`/v1/public/platforms/${encodeURIComponent(slug)}/reports`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  uploadReportPhoto: (reportId: string, file: File, caption?: string) => {
    const form = new FormData();
    form.append("file", file);
    if (caption) form.append("caption", caption);
    return request<PhotoItem>(`/v1/public/reports/${reportId}/photos`, { method: "POST", body: form, rawBody: true });
  },
  publicLayerStatuses: (slug: string) =>
    request<{ items: LayerStatusItem[] }>(`/v1/public/platforms/${encodeURIComponent(slug)}/layers`),
  publicLayer: (slug: string, layer: string) =>
    request<LayerResponse>(`/v1/public/platforms/${encodeURIComponent(slug)}/layers/${layer}`),
  mediaUrl: (path: string) => `${API_BASE}${path}`,
  publicVehicles: (slug: string) => request<VehicleListResponse>(`/v1/public/platforms/${encodeURIComponent(slug)}/vehicles`),
  publicRoutes: (slug: string) => request<RouteCollection>(`/v1/public/platforms/${encodeURIComponent(slug)}/routes`),

  // ── agent ──
  agentPlan: (message: string) =>
    request<AgentPlan>("/v1/agent/plan", { method: "POST", body: JSON.stringify({ message }) }),
  agentExecute: (draft: PlatformDraft) =>
    request<AgentExecuteResponse>("/v1/agent/execute", { method: "POST", body: JSON.stringify(draft) }),

  // ── console ──
  listPlatforms: (params: { status?: string } = {}) =>
    request<{ items: PlatformItem[]; total: number }>(`/v1/platforms${qs(params)}`),
  getPlatform: (id: string) => request<PlatformDetail>(`/v1/platforms/${id}`),
  setPlatformStatus: (id: string, status: string) =>
    request<PlatformDetail>(`/v1/platforms/${id}/status`, { method: "POST", body: JSON.stringify({ status }) }),
  updatePlatform: (id: string, body: { name?: string; cluster_policy?: Record<string, number | boolean> }) =>
    request<PlatformDetail>(`/v1/platforms/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  consoleOverview: (id: string) => request<ConsoleOverview>(`/v1/platforms/${id}/overview`),
  consoleMap: (id: string, params: { since_hours?: number; include_reports?: boolean } = {}) =>
    request<MapFeatureCollection>(`/v1/platforms/${id}/map${qs(params)}`),
  consoleCases: (
    id: string,
    params: {
      phase?: string;
      status?: string;
      category?: string;
      town?: string;
      severity?: string;
      since_hours?: number;
      sort?: string;
      limit?: number;
      offset?: number;
    } = {}
  ) => request<{ items: CaseItem[]; total: number }>(`/v1/platforms/${id}/cases${qs(params)}`),
  consoleReports: (id: string, params: { category?: string; town?: string; status?: string; limit?: number } = {}) =>
    request<{ items: ReportInternal[]; total: number }>(`/v1/platforms/${id}/reports${qs(params)}`),
  consoleClusters: (id: string, params: { status?: string } = {}) =>
    request<{ items: ClusterRow[]; total: number }>(`/v1/platforms/${id}/clusters${qs(params)}`),
  promoteCluster: (id: string, clusterId: string, actorName?: string) =>
    request<CaseItem>(`/v1/platforms/${id}/clusters/${clusterId}/promote${qs({ actor_name: actorName })}`, { method: "POST" }),
  consoleLayerStatuses: (id: string) => request<{ items: LayerStatusItem[] }>(`/v1/platforms/${id}/layers`),
  consoleLayer: (id: string, layer: string) => request<LayerResponse>(`/v1/platforms/${id}/layers/${layer}`),
  audit: (id: string, limit = 200) => request<{ items: AuditEvent[] }>(`/v1/platforms/${id}/audit${qs({ limit })}`),
  consoleVehicles: (id: string) => request<VehicleListResponse>(`/v1/platforms/${id}/vehicles`),
  consoleRoutes: (id: string) => request<RouteCollection>(`/v1/platforms/${id}/routes`),
  consoleUnits: (id: string) => request<{ items: ResponderUnit[]; total: number }>(`/v1/platforms/${id}/units`),
  caseResponders: (caseId: string) => request<{ case_id: string; category: string; items: ResponderSuggestion[] }>(`/v1/cases/${caseId}/responders`),
  dispatchCase: (caseId: string, body: { unit_id: string; note?: string; actor_name?: string; notify?: boolean }) =>
    request<DispatchResponse>(`/v1/cases/${caseId}/dispatch`, { method: "POST", body: JSON.stringify(body) }),

  getCase: (caseId: string) => request<CaseDetail>(`/v1/cases/${caseId}`),
  transitionCase: (caseId: string, body: { status: CaseStatus; note?: string; public?: boolean; actor_name?: string }) =>
    request<{ case: CaseItem }>(`/v1/cases/${caseId}/transition`, { method: "POST", body: JSON.stringify(body) }),
  assignCase: (
    caseId: string,
    body: { unit_name: string; team_lead?: string; contact?: string; note?: string; actor_name?: string }
  ) => request<{ case: CaseItem }>(`/v1/cases/${caseId}/assign`, { method: "POST", body: JSON.stringify(body) }),
  addCaseUpdate: (caseId: string, body: { note: string; public: boolean; actor_name?: string }) =>
    request<{ case: CaseItem }>(`/v1/cases/${caseId}/updates`, { method: "POST", body: JSON.stringify(body) }),
  uploadCasePhoto: (caseId: string, file: File, kind: "before" | "scene" | "after", caption?: string) => {
    const form = new FormData();
    form.append("file", file);
    form.append("kind", kind);
    if (caption) form.append("caption", caption);
    return request<PhotoItem>(`/v1/cases/${caseId}/photos`, { method: "POST", body: form, rawBody: true });
  },
  rejectReport: (reportId: string, note?: string) =>
    request<ReportInternal>(`/v1/reports/${reportId}/reject${qs({ note })}`, { method: "POST" }),

  // ── registry ──
  listModules: (params: { hazard?: string; domain?: string; module_type?: string } = {}) =>
    request<{ items: ModuleSpecItem[]; total: number }>(`/v1/modules${qs(params)}`),
  listDomains: () => request<{ items: DomainItem[] }>("/v1/modules/domains"),
  listConnectors: () => request<{ items: ConnectorStatusItem[] }>("/v1/connectors"),

  // ── demo ──
  prunePlatforms: (keep = 0) => request<{ removed: string[]; count: number }>(`/v1/platforms/prune${qs({ keep })}`, { method: "POST" }),
  seedPlatformDemo: (id: string, replace = false) => request<{ seeded: boolean; cases: number; reports: number; translated: boolean }>(`/v1/platforms/${id}/demo${qs({ replace })}`, { method: "POST" }),
  seedDemo: (force = false) => request<Record<string, any>>(`/v1/demo/nantou${qs({ force })}`, { method: "POST" }),
  getDemo: () => request<{ exists: boolean; platform_id?: string; slug?: string; status?: string }>("/v1/demo/nantou"),
};
