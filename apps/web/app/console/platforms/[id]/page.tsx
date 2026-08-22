"use client";

// Command centre: KPIs, the big map and the case queue side by side, then
// clusters below threshold, recent reports, layer health and the audit log.

import dynamic from "next/dynamic";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import ConsoleShell from "@/components/ConsoleShell";
import LayerPanel from "@/components/LayerPanel";
import EventFeed from "@/components/EventFeed";
import IntelPanel from "@/components/console/IntelPanel";
import { CategoryBadge } from "@/lib/categoryIcons";
import TrendChart, { BreakdownBars } from "@/components/TrendChart";
import { EmptyState, ErrorBox, Kpi, SeverityTag, Skeleton, StatusPill } from "@/components/ui";
import { api } from "@/lib/api";
import { fmtAgo, fmtDuration, fmtTime } from "@/lib/format";
import { CATEGORY_LABEL, LAYERS, PHASE_LABEL, ROLE_LABEL, SEVERITY_LABEL, SEVERITY_ORDER } from "@/lib/labels";
import type { AuditEvent, CaseItem, ClusterRow, ConsoleOverview, GeoFeature, LayerStatusItem, MapFeature, MapFeatureCollection, Phase, PlatformDetail, ReportInternal, RouteFeature, Severity, VehicleItem } from "@/lib/types";
import { countsByLayer, keepIfSame, useOfficialLayers, useVisibleLayers } from "@/lib/usePortal";

const TerrainMap = dynamic(() => import("@/components/TerrainMap"), { ssr: false, loading: () => <Skeleton className="h-full w-full" /> });

const WEATHER_LAYERS = ["radar", "rainfall", "official_alert", "water", "reservoir"];

export default function CommandCenterPage() {
  const { id } = useParams<{ id: string }>();
  const [platform, setPlatform] = useState<PlatformDetail | null>(null);
  const [overview, setOverview] = useState<ConsoleOverview | null>(null);
  const [map, setMap] = useState<MapFeatureCollection | null>(null);
  const [cases, setCases] = useState<CaseItem[]>([]);
  const [clusters, setClusters] = useState<ClusterRow[]>([]);
  const [reports, setReports] = useState<ReportInternal[]>([]);
  const [statuses, setStatuses] = useState<LayerStatusItem[]>([]);
  const [audit, setAudit] = useState<AuditEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [tab, setTab] = useState<"clusters" | "reports" | "layers" | "intel" | "audit" | "policy">("clusters");
  const [busy, setBusy] = useState<string | null>(null);
  const [routes, setRoutes] = useState<RouteFeature[]>([]);
  const [vehicles, setVehicles] = useState<VehicleItem[]>([]);
  const [threeD, setThreeD] = useState(true);

  const [phase, setPhase] = useState<Phase | "open">("open");
  const [sort, setSort] = useState("severity_desc");
  const [category, setCategory] = useState("");
  const [town, setTown] = useState("");
  const [severity, setSeverity] = useState<Severity | "">("");
  const [sinceHours, setSinceHours] = useState<number | "">("");

  const load = useCallback(async () => {
    try {
      const [p, o, m] = await Promise.all([api.getPlatform(id), api.consoleOverview(id), api.consoleMap(id)]);
      setPlatform(p);
      setOverview(o);
      setMap((prev) => keepIfSame(prev, m));
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [id]);
  const loadCases = useCallback(() => {
    api
      .consoleCases(id, { phase: phase === "open" ? "open" : phase, sort, category: category || undefined, town: town || undefined, severity: severity || undefined, since_hours: sinceHours || undefined, limit: 200 })
      .then((r) => setCases(r.items))
      .catch(() => undefined);
  }, [id, phase, sort, category, town, severity, sinceHours]);
  const loadSide = useCallback(() => {
    api.consoleClusters(id, { status: "open" }).then((r) => setClusters(r.items)).catch(() => undefined);
    api.consoleReports(id, { limit: 60 }).then((r) => setReports(r.items)).catch(() => undefined);
    api.consoleLayerStatuses(id).then((r) => setStatuses(r.items)).catch(() => undefined);
  }, [id]);

  useEffect(() => {
    load();
    loadSide();
    const a = window.setInterval(() => {
      if (!document.hidden) load();
    }, 20000);
    // side panels are not time-critical: half the rate, offset so the two
    // never land in the same frame
    const b = window.setInterval(() => {
      if (!document.hidden) loadSide();
    }, 40000);
    return () => {
      window.clearInterval(a);
      window.clearInterval(b);
    };
  }, [load, loadSide]);
  useEffect(() => {
    loadCases();
    const t = window.setInterval(() => {
      if (!document.hidden) loadCases();
    }, 20000);
    return () => window.clearInterval(t);
  }, [loadCases]);
  useEffect(() => {
    const loadRoutes = () => api.consoleRoutes(id).then((r) => setRoutes(r.features)).catch(() => undefined);
    const loadVehicles = () => api.consoleVehicles(id).then((r) => setVehicles(r.items)).catch(() => undefined);
    loadRoutes();
    loadVehicles();
    const a = window.setInterval(() => {
      if (!document.hidden) loadRoutes();
    }, 20000);
    const b = window.setInterval(() => {
      if (!document.hidden) loadVehicles();
    }, 3000);
    return () => {
      window.clearInterval(a);
      window.clearInterval(b);
    };
  }, [id]);

  useEffect(() => {
    if (tab !== "audit") return;
    api.audit(id, 120).then((r) => setAudit(r.items)).catch(() => undefined);
  }, [tab, id]);

  const layerKey = (platform?.layers ?? []).join(",");
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const layers = useMemo(() => platform?.layers ?? [], [layerKey]);
  const { visible, toggle } = useVisibleLayers(layers, "console");
  const fetcher = useCallback((layer: string) => api.consoleLayer(id, layer), [id]);
  const official = useOfficialLayers(layers, visible, fetcher);
  const features = useMemo(() => map?.features ?? [], [map]);
  const counts = useMemo(() => countsByLayer(features), [features]);
  const onSelect = useCallback((f: MapFeature | GeoFeature | null) => setSelectedId(f ? (f as MapFeature).id ?? null : null), []);
  const radarNote = useMemo(() => {
    if (visible.radar !== true) return null;
    const r = official.radar;
    if (!r) return "雷達回波載入中…（首次需向氣象署取得影像）";
    if (r.status === "disabled") return "雷達回波需設定 CWA_API_KEY";
    if (r.status !== "ok") return r.detail || "雷達回波暫時無法取得";
    const latest = r.features[r.features.length - 1]?.properties;
    return `雷達回波 ${latest?.time ? fmtTime(String(latest.time)) : ""}　共 ${r.features.length} 幀自動回放`;
  }, [visible.radar, official.radar]);

  async function promote(clusterId: string) {
    setBusy(clusterId);
    try {
      await api.promoteCluster(id, clusterId, "值班承辦");
      await Promise.all([load(), loadSide()]);
      loadCases();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  const policy = platform?.configuration?.cluster_policy;
  const [policyDraft, setPolicyDraft] = useState<{ required_unique_reporters: number; radius_meters: number; time_window_minutes: number } | null>(null);
  useEffect(() => {
    if (policy && !policyDraft) setPolicyDraft({ required_unique_reporters: policy.required_unique_reporters, radius_meters: policy.radius_meters, time_window_minutes: policy.time_window_minutes });
  }, [policy, policyDraft]);

  async function savePolicy() {
    if (!policyDraft) return;
    setBusy("policy");
    try {
      await api.updatePlatform(id, { cluster_policy: policyDraft });
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  const center: [number, number] = platform?.configuration?.map?.center ?? [platform?.center_lat ?? 23.91, platform?.center_lon ?? 120.69];

  return (
    <ConsoleShell wide crumbs={[{ href: "/", label: "系統控制台" }, { href: "/console", label: "平台管理" }, { label: platform?.name || "…" }]}>
      {error ? (
        <div className="mb-3">
          <ErrorBox message={error} onRetry={load} />
        </div>
      ) : null}
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
        <div>
          <div className="af-eyebrow">災害應變指揮中心</div>
          <h1 className="af-h1">{platform?.name || <Skeleton className="inline-block h-6 w-56" />}</h1>
          {platform ? (
            <div className="mt-0.5 text-xs text-[var(--muted)]">
              {platform.county} {platform.towns.join("、")} · {platform.configuration?.hazard_labels?.join("、")} · 狀態 {platform.status === "published" ? "已發布" : platform.status}
            </div>
          ) : null}
        </div>
        <div className="flex items-center gap-2">
          {platform ? (
            <a href={`/p/${platform.slug}`} target="_blank" rel="noreferrer" className="af-btn af-btn-secondary text-xs">
              民眾通報網站 ↗
            </a>
          ) : null}
          {platform ? (
            <a href={`/p/${platform.slug}/wall`} target="_blank" rel="noreferrer" className="af-btn af-btn-secondary text-xs" title="全螢幕戰情牆（自動輪播）">
              戰情牆 ↗
            </a>
          ) : null}
          {platform ? (
            <button
              type="button"
              className="af-btn af-btn-ghost text-xs"
              disabled={busy === "demo"}
              title="把南投豪雨示範情境的通報、成案、派遣帶入這個平台（標示為示範）"
              onClick={async () => {
                const has = (overview?.cases_total ?? 0) > 0;
                if (has && !window.confirm("此平台已有案件。要清除現有通報與案件，重新帶入示範資料嗎？")) return;
                setBusy("demo");
                try {
                  await api.seedPlatformDemo(id, has);
                  await load();
                  loadCases();
                } catch (e) {
                  setError((e as Error).message);
                } finally {
                  setBusy(null);
                }
              }}
            >
              {busy === "demo" ? "帶入中…" : (overview?.cases_total ?? 0) > 0 ? "重新帶入示範資料" : "一鍵帶入示範資料"}
            </button>
          ) : null}
          {overview ? <span className="text-[11px] text-[var(--muted)]">更新 {fmtTime(overview.generated_at)}</span> : null}
        </div>
      </div>

      <div className="mb-3 grid grid-cols-3 gap-2 lg:grid-cols-8">
        {overview ? (
          <>
            <Kpi value={overview.cases_open} label="目前事件" small spark={overview.trend.map((b) => b.cases_created)} />
            <Kpi value={overview.cases_pending} label="待派工" tone="pending" small />
            <Kpi value={overview.cases_active} label="處理中" tone="active" small />
            <Kpi value={overview.by_severity.find((s) => s.key === "critical")?.count ?? 0} label="危急案件" tone="risk" small />
            <Kpi value={overview.cases_new_last_hour} label="近 1 小時新增案件" small spark={overview.trend.map((b) => b.reports)} hint={`${overview.reports_last_hour} 筆通報 / 1 小時`} />
            <Kpi value={overview.cases_done} label="已完成" tone="done" small />
            <Kpi value={fmtDuration(overview.median_dispatch_minutes)} label="派工中位時間" small />
            <Kpi value={overview.clusters_open} label="未達門檻聚類" small hint={`${overview.reports_last_hour} 筆 / 1 小時`} />
          </>
        ) : (
          [0, 1, 2, 3, 4, 5, 6, 7].map((i) => <Skeleton key={i} className="h-[60px]" />)
        )}
      </div>

      <div className="grid gap-3 xl:grid-cols-12">
        <section className="af-panel relative overflow-hidden xl:col-span-8">
          <div className="h-[560px] xl:h-[calc(100vh-268px)] xl:min-h-[600px]">
            {platform ? (
              <TerrainMap center={center} zoom={platform.configuration?.map?.zoom ?? 11} features={features} officialLayers={official} visible={visible} enabledLayers={layers} selectedId={selectedId} onSelect={onSelect} routes={routes} vehicles={vehicles} threeD={threeD} fitToData />
            ) : (
              <Skeleton className="h-full w-full" />
            )}
          </div>
          <div className="absolute left-2 top-2 z-[1000] w-[220px]">
            <div className="af-panel max-h-[600px] overflow-y-auto p-2.5 shadow-md">
              <div className="mb-2 flex items-center gap-1">
                <button type="button" className={`af-hud-chip ${threeD ? "af-hud-chip-on" : ""}`} onClick={() => setThreeD((v) => !v)}>
                  {threeD ? "3D 地形" : "2D"}
                </button>
                <button type="button" className={`af-hud-chip ${visible.dispatch !== false ? "af-hud-chip-on" : ""}`} onClick={() => toggle("dispatch")}>
                  出勤 {vehicles.length}
                </button>
              </div>
              {/* weather: the first thing an operator looks at, so it stays in reach */}
              <div className="mb-2 border-b pb-2" style={{ borderColor: "var(--line)" }}>
                <div className="af-eyebrow mb-1">天氣</div>
                <div className="flex flex-wrap items-center gap-1">
                  {WEATHER_LAYERS.filter((k) => layers.includes(k)).map((k) => {
                    const meta = LAYERS[k];
                    const data = official[k];
                    const st = statuses.find((x) => x.layer === k);
                    const on = visible[k] === true;
                    const disabled = st?.status === "disabled";
                    const loading = on && !data;
                    return (
                      <button
                        key={k}
                        type="button"
                        disabled={disabled}
                        onClick={() => toggle(k)}
                        aria-pressed={on}
                        className={`af-hud-chip ${on ? "af-hud-chip-on" : ""}`}
                        title={disabled ? st?.detail || "尚未設定資料來源" : data?.status === "unavailable" ? data.detail || "暫時無法取得" : meta?.label}
                      >
                        <span className="inline-block h-2 w-2 rounded-sm" style={{ background: disabled ? "var(--line-2)" : meta?.hex }} />
                        {meta?.label}
                        {loading ? <span className="af-spinner !h-2.5 !w-2.5" /> : null}
                        {data?.status === "ok" && k !== "radar" ? <span className="text-[var(--faint)]">{data.count}</span> : null}
                        {disabled ? <span className="text-[var(--faint)]">·未設定</span> : null}
                      </button>
                    );
                  })}
                </div>
                {radarNote ? <div className="mt-1 text-[10.5px] text-[var(--muted)]">{radarNote}</div> : null}
              </div>
              <LayerPanel enabledLayers={layers} visible={visible} onToggle={toggle} counts={counts} officialLayers={official} statuses={statuses} compact />
            </div>
          </div>
        </section>

        <aside className="af-panel flex flex-col xl:col-span-4">
          <div className="border-b p-2" style={{ borderColor: "var(--line)" }}>
            <div className="flex flex-wrap items-center gap-1.5">
              <h2 className="af-h2 mr-1">案件佇列</h2>
              {(["open", "pending", "active", "done"] as const).map((p) => (
                <button key={p} type="button" onClick={() => setPhase(p)} className={`af-chip ${phase === p ? "af-chip-on" : ""}`}>
                  {p === "open" ? "進行中" : PHASE_LABEL[p]}
                </button>
              ))}
              <span className="ml-auto text-[11px] text-[var(--muted)]">{cases.length} 件</span>
            </div>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              <select className="af-input !w-auto !py-0.5 text-[11px]" value={sort} onChange={(e) => setSort(e.target.value)}>
                <option value="severity_desc">依嚴重度</option>
                <option value="created_desc">依時間（新→舊）</option>
                <option value="created_asc">依時間（舊→新）</option>
                <option value="reports_desc">依回報人數</option>
                <option value="updated_desc">依最近更新</option>
              </select>
              <select className="af-input !w-auto !py-0.5 text-[11px]" value={town} onChange={(e) => setTown(e.target.value)}>
                <option value="">所有鄉鎮</option>
                {(platform?.towns || []).map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
              <select className="af-input !w-auto !py-0.5 text-[11px]" value={category} onChange={(e) => setCategory(e.target.value)}>
                <option value="">所有類別</option>
                {((platform?.scenario?.report_categories as { key: string; label: string }[]) || []).map((c) => (
                  <option key={c.key} value={c.key}>
                    {c.label}
                  </option>
                ))}
              </select>
              <select className="af-input !w-auto !py-0.5 text-[11px]" value={severity} onChange={(e) => setSeverity(e.target.value as Severity | "")}>
                <option value="">所有嚴重度</option>
                {SEVERITY_ORDER.map((s) => (
                  <option key={s} value={s}>
                    {SEVERITY_LABEL[s]}
                  </option>
                ))}
              </select>
              <select className="af-input !w-auto !py-0.5 text-[11px]" value={sinceHours} onChange={(e) => setSinceHours(e.target.value ? Number(e.target.value) : "")}>
                <option value="">全部時間</option>
                <option value="1">近 1 小時</option>
                <option value="6">近 6 小時</option>
                <option value="24">近 24 小時</option>
              </select>
            </div>
          </div>
          <ul className="max-h-[560px] flex-1 divide-y overflow-y-auto xl:max-h-[calc(100vh-430px)]" style={{ borderColor: "var(--line)" }}>
            {cases.length === 0 ? (
              <li className="p-4 text-xs text-[var(--muted)]">沒有符合條件的案件。</li>
            ) : (
              cases.map((c) => (
                <li key={c.id} className={`af-row-hover cursor-pointer px-3 py-2 ${selectedId === `case:${c.id}` ? "bg-[var(--surface-2)]" : ""}`} onClick={() => setSelectedId(`case:${c.id}`)} style={{ borderLeft: `3px solid ${selectedId === `case:${c.id}` ? "var(--brand)" : "transparent"}` }}>
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-[10.5px] text-[var(--muted)]">{c.case_number}</span>
                        <SeverityTag severity={c.severity} withLabel={false} />
                      </div>
                      <Link href={`/console/platforms/${id}/cases/${c.id}`} className="flex items-center gap-2 truncate text-sm font-semibold text-[var(--ink)] hover:underline" onClick={(e) => e.stopPropagation()}>
                        <CategoryBadge category={c.category} size={22} />
                        {c.title}
                      </Link>
                      <div className="text-[11px] text-[var(--muted)]">
                        {c.town} · {c.location_label} · {c.unique_reporter_count} 人回報 · {fmtAgo(c.created_at)}
                        {c.assigned_unit ? ` · ${c.assigned_unit}` : ""}
                      </div>
                    </div>
                    <div className="flex flex-col items-end gap-1">
                      <StatusPill status={c.status} phase={c.phase} />
                      <Link href={`/console/platforms/${id}/cases/${c.id}`} className="af-btn af-btn-secondary !px-2 !py-0.5 text-[11px]" onClick={(e) => e.stopPropagation()}>
                        {c.status === "awaiting_dispatch" ? "派工" : "處理"}
                      </Link>
                    </div>
                  </div>
                </li>
              ))
            )}
          </ul>
        </aside>
      </div>

      {/* lower section */}
      <div className="mt-3 grid gap-3 xl:grid-cols-12">
        <section className="af-panel xl:col-span-8">
          <div className="flex items-center gap-1 border-b px-2 py-1.5" style={{ borderColor: "var(--line)" }}>
            {(
              [
                ["clusters", `未達門檻聚類 (${clusters.length})`],
                ["reports", "最新通報"],
                ["layers", "圖層狀態"],
                ["policy", "成案規則"],
                ["intel", "官方情資"],
                ["audit", "稽核軌跡"],
              ] as const
            ).map(([k, label]) => (
              <button key={k} type="button" onClick={() => setTab(k)} className={`rounded px-2.5 py-1 text-xs ${tab === k ? "bg-[var(--surface-3)] font-medium text-[var(--ink)]" : "text-[var(--muted)] hover:text-[var(--ink)]"}`}>
                {label}
              </button>
            ))}
          </div>
          <div className="max-h-[420px] overflow-auto">
            {tab === "clusters" ? (
              clusters.length === 0 ? (
                <div className="p-4 text-xs text-[var(--muted)]">目前沒有未達門檻的多人回報聚類。</div>
              ) : (
                <table className="af-table">
                  <thead>
                    <tr>
                      <th>災情</th>
                      <th>鄉鎮</th>
                      <th>回報者／筆數</th>
                      <th>嚴重度</th>
                      <th>最近回報</th>
                      <th className="text-right">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {clusters.map((c) => (
                      <tr key={c.cluster_id} className={`af-row-hover cursor-pointer ${selectedId === `cluster:${c.cluster_id}` ? "bg-[var(--surface-2)]" : ""}`} onClick={() => setSelectedId(`cluster:${c.cluster_id}`)}>
                        <td className="font-medium">{c.category_label || CATEGORY_LABEL[c.category]}</td>
                        <td className="text-xs">{c.town || "—"}</td>
                        <td className="text-xs tabular-nums">
                          {c.unique_reporter_count} 人 / {c.report_count} 筆
                        </td>
                        <td>
                          <SeverityTag severity={c.severity} withLabel={false} />
                        </td>
                        <td className="text-xs text-[var(--muted)]">{fmtAgo(c.last_reported_at)}</td>
                        <td className="text-right">
                          <button type="button" className="af-btn af-btn-secondary !py-0.5 text-[11px]" disabled={busy === c.cluster_id} onClick={(e) => { e.stopPropagation(); promote(c.cluster_id); }}>
                            人工成案
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )
            ) : null}
            {tab === "reports" ? (
              <table className="af-table">
                <thead>
                  <tr>
                    <th>時間</th>
                    <th>災情</th>
                    <th>地點</th>
                    <th>回報者</th>
                    <th>分級</th>
                    <th>狀態</th>
                  </tr>
                </thead>
                <tbody>
                  {reports.map((r) => (
                    <tr key={r.id} className="af-row-hover">
                      <td className="font-mono text-[11px] text-[var(--muted)]">{fmtTime(r.created_at)}</td>
                      <td>
                        <div className="font-medium">{CATEGORY_LABEL[r.category] || r.category}</div>
                        <div className="max-w-xs truncate text-[11px] text-[var(--muted)]">{r.description}</div>
                      </td>
                      <td className="text-xs">
                        {r.town}
                        <div className="text-[11px] text-[var(--muted)]">{r.address}</div>
                      </td>
                      <td className="text-xs">
                        {ROLE_LABEL[r.reporter_role] || r.reporter_role}
                        <div className="text-[11px] text-[var(--muted)]">{r.reporter_name || (r.has_identity ? "已留識別" : "匿名")}</div>
                      </td>
                      <td>
                        <SeverityTag severity={r.triage_severity} withLabel={false} />
                      </td>
                      <td className="text-xs">
                        {r.case_id ? (
                          <Link href={`/console/platforms/${id}/cases/${r.case_id}`} className="text-[var(--focus)] hover:underline">
                            已成案
                          </Link>
                        ) : r.status === "rejected" ? (
                          "已排除"
                        ) : r.cluster_id ? (
                          "聚類中"
                        ) : (
                          "無座標"
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : null}
            {tab === "layers" ? (
              <table className="af-table">
                <thead>
                  <tr>
                    <th>圖層</th>
                    <th>類型</th>
                    <th>來源</th>
                    <th>狀態</th>
                  </tr>
                </thead>
                <tbody>
                  {statuses.map((s) => (
                    <tr key={s.layer}>
                      <td className="font-medium">{s.name}</td>
                      <td className="text-xs">{s.kind === "official" ? "官方資料" : "平台資料"}</td>
                      <td className="font-mono text-[11px] text-[var(--muted)]">{s.source || "—"}</td>
                      <td className="text-xs">
                        <span className="inline-flex items-center gap-1.5">
                          <span className="h-1.5 w-1.5 rounded-full" style={{ background: s.status === "ok" || s.status === "ready" ? "var(--st-done)" : s.status === "unavailable" ? "var(--sev-high)" : "var(--st-pending)" }} />
                          {s.status === "ok" ? "正常" : s.status === "ready" ? "可介接" : s.status === "unavailable" ? "上游無法取得" : "未設定金鑰"}
                        </span>
                        {s.detail ? <div className="text-[11px] text-[var(--muted)]">{s.detail}</div> : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : null}
            {tab === "policy" && policyDraft ? (
              <div className="p-4">
                <div className="grid max-w-xl grid-cols-3 gap-3">
                  {(
                    [
                      ["required_unique_reporters", "不同回報者門檻（人）"],
                      ["radius_meters", "聚類半徑（公尺）"],
                      ["time_window_minutes", "時間窗（分鐘）"],
                    ] as const
                  ).map(([k, label]) => (
                    <label key={k}>
                      <span className="af-label">{label}</span>
                      <input type="number" className="af-input mt-1" value={policyDraft[k]} onChange={(e) => setPolicyDraft({ ...policyDraft, [k]: Number(e.target.value) })} />
                    </label>
                  ))}
                </div>
                <div className="mt-3 flex items-center gap-3">
                  <button type="button" className="af-btn af-btn-primary" disabled={busy === "policy"} onClick={savePolicy}>
                    儲存規則
                  </button>
                  <span className="text-[11px] text-[var(--muted)]">變更只影響之後的通報；同一人重複送出只計一次。</span>
                </div>
              </div>
            ) : null}
            {tab === "intel" ? (
              <IntelPanel platformId={id} enabledLayers={layers} cases={cases} selectedCase={cases.find((c) => `case:${c.id}` === selectedId) || null} active={tab === "intel"} />
            ) : null}
            {tab === "audit" ? (
              <ul className="divide-y text-xs" style={{ borderColor: "var(--line)" }}>
                {audit.map((e) => (
                  <li key={e.id} className="flex gap-3 px-3 py-1.5">
                    <span className="w-24 flex-none font-mono text-[11px] text-[var(--muted)]">{fmtTime(e.created_at)}</span>
                    <span className="w-44 flex-none font-mono text-[11px] text-[var(--ink-2)]">{e.event_type}</span>
                    <span className="truncate text-[var(--muted)]">
                      {e.payload.case_number ? `${e.payload.case_number} ` : ""}
                      {e.payload.to_status ? `→ ${e.payload.to_status} ` : ""}
                      {e.payload.category ? `${CATEGORY_LABEL[e.payload.category] || e.payload.category} ` : ""}
                      {e.payload.actor_role ? `(${e.payload.actor_role})` : ""}
                    </span>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        </section>

        <section className="af-panel p-3 xl:col-span-4">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="af-h2">即時事件流</h2>
            <span className="inline-flex items-center gap-1 text-[10.5px] text-[var(--muted)]">
              <span className="af-live-dot" /> 每 8 秒更新
            </span>
          </div>
          <EventFeed platformId={id} className="mb-4 max-h-[300px] overflow-y-auto pr-1" />
          <h2 className="af-h2 mb-2">趨勢與分布</h2>
          {overview ? (
            <>
              <TrendChart trend={overview.trend} height={110} />
              <div className="mt-3 grid grid-cols-2 gap-3">
                <div>
                  <div className="af-eyebrow mb-1">依鄉鎮</div>
                  <BreakdownBars items={overview.by_town} max={5} />
                </div>
                <div>
                  <div className="af-eyebrow mb-1">回報者身分</div>
                  <BreakdownBars items={overview.by_reporter_role} max={5} />
                </div>
              </div>
              <div className="mt-3 text-[11px] text-[var(--muted)]">
                完成中位時間 {fmtDuration(overview.median_resolve_minutes)} · 未聚類通報 {overview.reports_unclustered} · 已排除 {overview.reports_rejected}
              </div>
            </>
          ) : (
            <Skeleton className="h-40" />
          )}
        </section>
      </div>
      {!platform && !error ? <EmptyState title="載入中…" /> : null}
    </ConsoleShell>
  );
}
