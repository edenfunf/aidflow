// API client. Base URL from NEXT_PUBLIC_API_BASE_URL, falling back to
// api.<same-domain> on deployed hosts and localhost:8000 in development.
// Console calls carry the staff login token (sessionStorage); a 401 on a
// console call clears it and sends the operator to /login.

import type {
  AuditEvent,
  CaseActionResponse,
  CaseDetail,
  CaseItem,
  CaseStatus,
  ClusterRow,
  CommunitySubmitResponse,
  ConnectorStatusItem,
  ConsoleOverview,
  DomainItem,
  GlobalOverview,
  HealthResponse,
  LayerResponse,
  LayerStatusItem,
  LineStatus,
  LoginResponse,
  MapFeatureCollection,
  Me,
  ModuleSpecItem,
  NotificationLogItem,
  PhotoItem,
  PlatformDetail,
  PlatformDraft,
  PlatformItem,
  PlatformOptions,
  PlatformPreview,
  PublicCase,
  PublicCaseDetail,
  PublicPlatform,
  ReportInternal,
  ReportPublic,
  ReviewDecision,
  Role,
  Situation,
  SubmitReportPayload,
  SubmitReportResponse,
  UserItem,
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

// ── session token ──────────────────────────────────────────────────────
// sessionStorage: a closed browser tab ends the session on a shared EOC PC
const TOKEN_STORAGE = "aidflow.session";

export function getToken(): string {
  if (typeof window === "undefined") return "";
  try {
    return window.sessionStorage.getItem(TOKEN_STORAGE) || "";
  } catch {
    return "";
  }
}

export function setToken(value: string): void {
  try {
    if (value) window.sessionStorage.setItem(TOKEN_STORAGE, value);
    else window.sessionStorage.removeItem(TOKEN_STORAGE);
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

function isPublicPath(path: string): boolean {
  return path.startsWith("/v1/public") || path === "/v1/auth/login";
}

function redirectToLogin(): void {
  if (typeof window === "undefined") return;
  const here = window.location.pathname + window.location.search;
  if (window.location.pathname.startsWith("/login")) return;
  window.location.assign(`/login?next=${encodeURIComponent(here)}`);
}

async function request<T>(path: string, init?: RequestInit & { rawBody?: boolean }): Promise<T> {
  const headers: Record<string, string> = { ...((init?.headers as Record<string, string>) || {}) };
  if (init?.body && !init.rawBody && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
  const token = getToken();
  if (token && !path.startsWith("/v1/public")) headers.Authorization = `Bearer ${token}`;

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
    if (res.status === 401 && !isPublicPath(path)) {
      setToken("");
      redirectToLogin();
    }
    // 4xx carries our own wording and tells the user what to do; a 5xx body can
    // carry internals, so the screens only ever show a generic sentence
    // (Fortify: System Information Leak: External).
    if (res.status >= 500) {
      throw new ApiError(res.status, "系統暫時無法處理這個操作，請稍後再試；若持續發生請聯繫系統管理者。", detail);
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

type CaseQuery = {
  phase?: string;
  status?: string;
  track?: string;
  category?: string;
  town?: string;
  severity?: string;
  since_hours?: number;
  sort?: string;
  limit?: number;
  offset?: number;
};

export const api = {
  health: () => request<HealthResponse>("/v1/health"),
  overview: () => request<GlobalOverview>("/v1/overview"),

  // ── auth ──
  login: (username: string, password: string) =>
    request<LoginResponse>("/v1/auth/login", { method: "POST", body: JSON.stringify({ username, password }) }),
  me: () => request<Me>("/v1/auth/me"),
  logout: () => request<{ ok: boolean }>("/v1/auth/logout", { method: "POST" }),
  changePassword: (current_password: string, new_password: string) =>
    request<{ token: string; expires_at: string }>("/v1/auth/password", { method: "POST", body: JSON.stringify({ current_password, new_password }) }),
  listUsers: () => request<UserItem[]>("/v1/users"),
  createUser: (body: { username: string; display_name: string; role: Role; password: string }) =>
    request<UserItem>("/v1/users", { method: "POST", body: JSON.stringify(body) }),
  updateUser: (id: string, body: { display_name?: string; role?: Role; active?: boolean; password?: string }) =>
    request<UserItem>(`/v1/users/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  securityAudit: (params: { kind?: string; limit?: number } = {}) => request<{ items: AuditEvent[] }>(`/v1/admin/audit${qs(params)}`),

  // ── public portal ──
  publicPlatforms: () => request<{ items: PublicPlatform[]; total: number }>("/v1/public/platforms"),
  publicPlatform: (slug: string) => request<PublicPlatform>(`/v1/public/platforms/${encodeURIComponent(slug)}`),
  situation: (slug: string) => request<Situation>(`/v1/public/platforms/${encodeURIComponent(slug)}/situation`),
  publicMap: (slug: string, params: { since_hours?: number; include_reports?: boolean } = {}) =>
    request<MapFeatureCollection>(`/v1/public/platforms/${encodeURIComponent(slug)}/map${qs(params)}`),
  publicCases: (slug: string, params: CaseQuery = {}) =>
    request<{ items: PublicCase[]; total: number }>(`/v1/public/platforms/${encodeURIComponent(slug)}/cases${qs(params)}`),
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
  submitCommunityReport: (slug: string, caseId: string, body: { files: File[]; note?: string; helper_name?: string }) => {
    const form = new FormData();
    body.files.forEach((f) => form.append("files", f));
    if (body.note) form.append("note", body.note);
    if (body.helper_name) form.append("helper_name", body.helper_name);
    return request<CommunitySubmitResponse>(`/v1/public/platforms/${encodeURIComponent(slug)}/cases/${caseId}/community-report`, {
      method: "POST",
      body: form,
      rawBody: true,
    });
  },
  unsubscribe: (token: string) => request<{ ok: boolean; message: string }>(`/v1/public/unsubscribe${qs({ token })}`, { method: "POST" }),
  publicLayerStatuses: (slug: string) =>
    request<{ items: LayerStatusItem[] }>(`/v1/public/platforms/${encodeURIComponent(slug)}/layers`),
  publicLayer: (slug: string, layer: string) =>
    request<LayerResponse>(`/v1/public/platforms/${encodeURIComponent(slug)}/layers/${layer}`),
  mediaUrl: (path: string) => `${API_BASE}${path}`,

  // ── platforms ──
  listPlatforms: (params: { status?: string } = {}) =>
    request<{ items: PlatformItem[]; total: number }>(`/v1/platforms${qs(params)}`),
  getPlatform: (id: string) => request<PlatformDetail>(`/v1/platforms/${id}`),
  platformOptions: () => request<PlatformOptions>("/v1/platforms/options"),
  previewPlatform: (body: { name: string; hazards?: string[] | null; county?: string | null; towns?: string[] }) =>
    request<PlatformPreview>("/v1/platforms/preview", { method: "POST", body: JSON.stringify(body) }),
  createPlatform: (draft: PlatformDraft) => request<PlatformDetail>("/v1/platforms", { method: "POST", body: JSON.stringify(draft) }),
  setPlatformStatus: (id: string, status: string) =>
    request<PlatformDetail>(`/v1/platforms/${id}/status`, { method: "POST", body: JSON.stringify({ status }) }),
  updatePlatform: (id: string, body: { name?: string; cluster_policy?: Record<string, number | boolean> }) =>
    request<PlatformDetail>(`/v1/platforms/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  consoleOverview: (id: string) => request<ConsoleOverview>(`/v1/platforms/${id}/overview`),
  consoleMap: (id: string, params: { since_hours?: number; include_reports?: boolean } = {}) =>
    request<MapFeatureCollection>(`/v1/platforms/${id}/map${qs(params)}`),
  consoleCases: (id: string, params: CaseQuery = {}) => request<{ items: CaseItem[]; total: number }>(`/v1/platforms/${id}/cases${qs(params)}`),
  consoleReports: (id: string, params: { category?: string; town?: string; status?: string; limit?: number } = {}) =>
    request<{ items: ReportInternal[]; total: number }>(`/v1/platforms/${id}/reports${qs(params)}`),
  consoleClusters: (id: string, params: { status?: string } = {}) =>
    request<{ items: ClusterRow[]; total: number }>(`/v1/platforms/${id}/clusters${qs(params)}`),
  promoteCluster: (id: string, clusterId: string) =>
    request<CaseItem>(`/v1/platforms/${id}/clusters/${clusterId}/promote`, { method: "POST" }),
  consoleLayerStatuses: (id: string) => request<{ items: LayerStatusItem[] }>(`/v1/platforms/${id}/layers`),
  consoleLayer: (id: string, layer: string) => request<LayerResponse>(`/v1/platforms/${id}/layers/${layer}`),
  audit: (id: string, limit = 200) => request<{ items: AuditEvent[] }>(`/v1/platforms/${id}/audit${qs({ limit })}`),
  lineStatus: (id: string) => request<LineStatus>(`/v1/platforms/${id}/line`),
  lineRegenerateCode: (id: string) => request<LineStatus>(`/v1/platforms/${id}/line/code`, { method: "POST" }),
  lineBind: (id: string, group_id: string) => request<LineStatus>(`/v1/platforms/${id}/line`, { method: "PUT", body: JSON.stringify({ group_id }) }),
  lineUnbind: (id: string) => request<LineStatus>(`/v1/platforms/${id}/line`, { method: "DELETE" }),
  lineTest: (id: string) => request<{ result: string }>(`/v1/platforms/${id}/line/test`, { method: "POST" }),
  notifications: (id: string, limit = 50) => request<{ items: NotificationLogItem[] }>(`/v1/platforms/${id}/notifications${qs({ limit })}`),

  // ── cases ──
  getCase: (caseId: string) => request<CaseDetail>(`/v1/cases/${caseId}`),
  reviewCase: (caseId: string, body: { decision: ReviewDecision; note?: string }) =>
    request<CaseActionResponse>(`/v1/cases/${caseId}/review`, { method: "POST", body: JSON.stringify(body) }),
  updateEmic: (caseId: string, body: { emic_case_no?: string; emic_status?: string; assigned_unit?: string; note?: string; status?: "emic_processing" | "closed" }) =>
    request<CaseActionResponse>(`/v1/cases/${caseId}/emic`, { method: "POST", body: JSON.stringify(body) }),
  confirmCommunity: (caseId: string, body: { approve: boolean; note?: string }) =>
    request<CaseActionResponse>(`/v1/cases/${caseId}/community/confirm`, { method: "POST", body: JSON.stringify(body) }),
  transitionCase: (caseId: string, body: { status: CaseStatus; note?: string; public?: boolean }) =>
    request<CaseActionResponse>(`/v1/cases/${caseId}/transition`, { method: "POST", body: JSON.stringify(body) }),
  addCaseUpdate: (caseId: string, body: { note: string; public: boolean }) =>
    request<CaseActionResponse>(`/v1/cases/${caseId}/updates`, { method: "POST", body: JSON.stringify(body) }),
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
