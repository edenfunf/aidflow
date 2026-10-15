"use client";

// Platform console: severity tiers on top, the LINE notification state, the
// map beside the review queue / case queue, then the working tabs below.
//
// Nothing enters the case queue unreviewed: cases wait in 待審核 (sorted by
// severity) until an officer decides 上報 EMIC／民間可處理／不成案.

import dynamic from "next/dynamic";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ConsoleShell from "@/components/ConsoleShell";
import LayerPanel from "@/components/LayerPanel";
import EventFeed from "@/components/EventFeed";
import IntelPanel from "@/components/console/IntelPanel";
import LinePanel, { LineStatusBanner } from "@/components/console/LinePanel";
import { CategoryBadge } from "@/lib/categoryIcons";
import TrendChart, { BreakdownBars } from "@/components/TrendChart";
import { EmptyState, ErrorBox, SeverityTag, Skeleton, StatusPill } from "@/components/ui";
import { api } from "@/lib/api";
import { useMe } from "@/lib/auth";
import { fmtAgo, fmtDuration, fmtTime } from "@/lib/format";
import { CATEGORY_LABEL, LAYERS, ROLE_LABEL, SEVERITY_HEX, SEVERITY_LABEL, SEVERITY_ORDER } from "@/lib/labels";
import type { AuditEvent, CaseItem, ClusterRow, ConsoleOverview, GeoFeature, LayerStatusItem, LineStatus, MapFeature, MapFeatureCollection, PlatformDetail, ReportInternal, Severity } from "@/lib/types";
import { countsByLayer, keepIfSame, useOfficialLayers, useVisibleLayers } from "@/lib/usePortal";

const TerrainMap = dynamic(() => import("@/components/TerrainMap"), { ssr: false, loading: () => <Skeleton className="h-full w-full" /> });

const WEATHER_LAYERS = ["radar", "rainfall", "official_alert", "water", "reservoir"];

type QueueTab = "pending" | "active" | "community" | "done";
const QUEUE_TABS: { key: QueueTab; label: string }[] = [
  { key: "pending", label: "待審核" },
  { key: "active", label: "EMIC 處理中" },
  { key: "community", label: "民眾協助" },
  { key: "done", label: "已結案" },
];

function actionLabel(c: CaseItem): string {
  if (c.status === "pending_review") return "審核";
  if (c.status === "reported_emic" || c.status === "emic_processing") return "更新 EMIC";
  if (c.status === "community_submitted") return "確認完成";
  return "查看";
}

function SeverityCard({ severity, count, pending, active, onClick }: { severity: Severity; count: number; pending: number; active: boolean; onClick: () => void }) {
  const hex = SEVERITY_HEX[severity];
  return (
    <button type="button" onClick={onClick} title="點選以篩選此嚴重度" className={`af-kpi relative overflow-hidden text-left ${active ? "ring-2" : ""}`} style={{ ["--tw-ring-color" as string]: hex }}>
      <span className="absolute inset-y-0 left-0 w-1.5" style={{ background: hex }} />
      <div className="flex items-baseline justify-between gap-2 pl-1.5">
        <span className="text-[16px] font-semibold" style={{ color: hex }}>
          嚴重度 {SEVERITY_LABEL[severity]}
        </span>
        {pending ? <span className="rounded-full px-2 py-0.5 text-[13px] font-semibold text-white" style={{ background: hex }}>{pending} 待審核</span> : null}
      </div>
      <div className="mt-1 pl-1.5 text-[34px] font-bold leading-none tabular-nums text-[var(--ink)]">{count}</div>
      <div className="mt-1 pl-1.5 text-[14px] text-[var(--muted)]">進行中災情</div>
    </button>
  );
}

export default function PlatformConsolePage() {
  const { id } = useParams<{ id: string }>();
  const { can } = useMe();
  const [platform, setPlatform] = useState<PlatformDetail | null>(null);
  const [overview, setOverview] = useState<ConsoleOverview | null>(null);
  const [map, setMap] = useState<MapFeatureCollection | null>(null);
  const [cases, setCases] = useState<CaseItem[]>([]);
  const [queueCounts, setQueueCounts] = useState<Record<QueueTab, number>>({ pending: 0, active: 0, community: 0, done: 0 });
  const [clusters, setClusters] = useState<ClusterRow[]>([]);
  const [reports, setReports] = useState<ReportInternal[]>([]);
  const [statuses, setStatuses] = useState<LayerStatusItem[]>([]);
  const [line, setLine] = useState<LineStatus | null>(null);
  const [audit, setAudit] = useState<AuditEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [tab, setTab] = useState<"clusters" | "reports" | "line" | "layers" | "policy" | "intel" | "feed">("clusters");
  const tabsRef = useRef<HTMLDivElement | null>(null);
  const [layerPanel, setLayerPanel] = useState(false);
  // the LINE banner lives at the top of the page, the tabs far below it:
  // switch and scroll, otherwise the click looks like it did nothing
  const openTab = (next: typeof tab) => {
    setTab(next);
    requestAnimationFrame(() => tabsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
  };
  const [busy, setBusy] = useState<string | null>(null);
  const [threeD, setThreeD] = useState(false);

  const [queue, setQueue] = useState<QueueTab>("pending");
  const [category, setCategory] = useState("");
  const [town, setTown] = useState("");
  const [severity, setSeverity] = useState<Severity | "">("");

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
      .consoleCases(id, { phase: queue, sort: queue === "done" ? "updated_desc" : "severity_desc", category: category || undefined, town: town || undefined, severity: severity || undefined, limit: 200 })
      .then((r) => setCases(r.items))
      .catch(() => undefined);
    // tab badges
    Promise.all(QUEUE_TABS.map((t) => api.consoleCases(id, { phase: t.key, limit: 1 }).then((r) => [t.key, r.total] as const)))
      .then((pairs) => setQueueCounts(Object.fromEntries(pairs) as Record<QueueTab, number>))
      .catch(() => undefined);
  }, [id, queue, category, town, severity]);
  const loadSide = useCallback(() => {
    api.consoleClusters(id, { status: "open" }).then((r) => setClusters(r.items)).catch(() => undefined);
    api.consoleReports(id, { limit: 60 }).then((r) => setReports(r.items)).catch(() => undefined);
    api.consoleLayerStatuses(id).then((r) => setStatuses(r.items)).catch(() => undefined);
    api.lineStatus(id).then(setLine).catch(() => undefined);
  }, [id]);

  useEffect(() => {
    load();
    loadSide();
    const a = window.setInterval(() => {
      if (!document.hidden) load();
    }, 20000);
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
    if (tab !== "feed") return;
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

  async function promote(clusterId: string) {
    setBusy(clusterId);
    try {
      await api.promoteCluster(id, clusterId);
      await Promise.all([load(), loadSide()]);
      setQueue("pending");
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
  const pendingBySev = Object.fromEntries((overview?.pending_by_severity || []).map((s) => [s.key, s.count]));
  const openBySev = Object.fromEntries((overview?.by_severity || []).map((s) => [s.key, s.count]));

  return (
    <ConsoleShell wide crumbs={[{ href: "/console", label: "災害平台" }, { label: platform?.name || "…" }]}>
      {error ? (
        <div className="mb-3">
          <ErrorBox message={error} onRetry={load} />
        </div>
      ) : null}
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[28px] font-bold text-[var(--ink)]">{platform?.name || <Skeleton className="inline-block h-7 w-64" />}</h1>
          {platform ? (
            <div className="mt-0.5 text-[15px] text-[var(--muted)]">
              {platform.county} {platform.towns.join("、")} · {platform.configuration?.hazard_labels?.join("、")} · {platform.status === "published" ? "已發布" : "未發布"}
              {overview ? ` · 更新 ${fmtTime(overview.generated_at)}` : ""}
            </div>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {platform ? (
            <>
              <a href={`/p/${platform.slug}`} target="_blank" rel="noreferrer" className="af-btn af-btn-secondary">
                民眾通報網站 ↗
              </a>
              <a href={`/p/${platform.slug}/wall`} target="_blank" rel="noreferrer" className="af-btn af-btn-secondary" title="全螢幕戰情牆（自動輪播）">
                戰情牆 ↗
              </a>
              <button
                type="button"
                className="af-btn af-btn-secondary"
                title="縣府網站嵌入用的地圖語法"
                onClick={() => {
                  const code = `<iframe src="${platform.embed_url}" width="100%" height="560" style="border:0" loading="lazy" title="災情地圖"></iframe>`;
                  navigator.clipboard?.writeText(code);
                  window.alert(`已複製嵌入語法：\n\n${code}`);
                }}
              >
                複製嵌入地圖語法
              </button>
            </>
          ) : null}
          {platform && can("manage_platforms") ? (
            <button
              type="button"
              className="af-btn af-btn-ghost"
              disabled={busy === "demo"}
              title="把南投豪雨示範情境帶入這個平台（標示為示範）"
              onClick={async () => {
                const has = (overview?.cases_total ?? 0) > 0;
                if (has && !window.confirm("此平台已有案件。要清除現有通報與案件，重新帶入示範資料嗎？")) return;
                setBusy("demo");
                try {
                  await api.seedPlatformDemo(id, has);
                  await load();
                  loadCases();
                  loadSide();
                } catch (e) {
                  setError((e as Error).message);
                } finally {
                  setBusy(null);
                }
              }}
            >
              {busy === "demo" ? "帶入中…" : (overview?.cases_total ?? 0) > 0 ? "重新帶入示範資料" : "帶入示範資料"}
            </button>
          ) : null}
        </div>
      </div>

      <div className="mb-4">
        <LineStatusBanner status={line} onOpen={() => openTab("line")} />
      </div>

      {/* severity tiers first: what matters most is what is most severe */}
      <div className="af-kpi-row mb-4 flex gap-3 overflow-x-auto pb-1 md:grid md:grid-cols-3 md:overflow-visible md:pb-0 xl:grid-cols-6">
        {overview ? (
          <>
            {SEVERITY_ORDER.map((s) => (
              <SeverityCard key={s} severity={s} count={openBySev[s] || 0} pending={pendingBySev[s] || 0} active={severity === s} onClick={() => setSeverity(severity === s ? "" : s)} />
            ))}
            <button type="button" onClick={() => setQueue("pending")} className="af-kpi text-left" style={{ borderColor: overview.cases_pending ? "var(--st-pending)" : undefined }}>
              <div className="text-[16px] font-semibold text-[var(--st-pending)]">待審核</div>
              <div className="mt-1 text-[34px] font-bold leading-none tabular-nums text-[var(--ink)]">{overview.cases_pending}</div>
              <div className="mt-1 text-[14px] text-[var(--muted)]">{overview.median_review_minutes != null ? `審核中位 ${fmtDuration(overview.median_review_minutes)}` : "需決定處理方式"}</div>
            </button>
            <button type="button" onClick={() => setQueue("community")} className="af-kpi text-left" style={{ borderColor: overview.cases_community_submitted ? "var(--st-community)" : undefined }}>
              <div className="text-[16px] font-semibold text-[var(--st-community)]">待確認完成</div>
              <div className="mt-1 text-[34px] font-bold leading-none tabular-nums text-[var(--ink)]">{overview.cases_community_submitted}</div>
              <div className="mt-1 text-[14px] text-[var(--muted)]">民眾已上傳處理照片</div>
            </button>
          </>
        ) : (
          [0, 1, 2, 3, 4, 5].map((i) => <Skeleton key={i} className="h-[112px]" />)
        )}
      </div>

      <div className="grid gap-4 xl:grid-cols-12">
        {/* queue */}
        <aside className="af-panel flex min-w-0 flex-col xl:order-2 xl:col-span-5">
          <div className="border-b p-3" style={{ borderColor: "var(--line)" }}>
            <div className="flex flex-wrap items-center gap-1.5">
              {QUEUE_TABS.map((t) => (
                <button key={t.key} type="button" onClick={() => setQueue(t.key)} className={`inline-flex items-center gap-1.5 rounded-md px-3 py-2 text-[16px] font-medium transition ${queue === t.key ? "bg-[var(--brand)] text-white" : "bg-[var(--surface-3)] text-[var(--ink-2)] hover:text-[var(--ink)]"}`}>
                  {t.label}
                  <span className={`rounded-full px-1.5 text-[13px] ${queue === t.key ? "bg-white/20" : "bg-white text-[var(--muted)]"}`}>{queueCounts[t.key]}</span>
                </button>
              ))}
            </div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              <select className="af-input !w-auto !py-1.5 !text-[15px]" value={severity} onChange={(e) => setSeverity(e.target.value as Severity | "")}>
                <option value="">所有嚴重度</option>
                {SEVERITY_ORDER.map((s) => (
                  <option key={s} value={s}>
                    嚴重度 {SEVERITY_LABEL[s]}
                  </option>
                ))}
              </select>
              <select className="af-input !w-auto !py-1.5 !text-[15px]" value={town} onChange={(e) => setTown(e.target.value)}>
                <option value="">所有鄉鎮</option>
                {(platform?.towns || []).map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
              <select className="af-input !w-auto !py-1.5 !text-[15px]" value={category} onChange={(e) => setCategory(e.target.value)}>
                <option value="">所有類別</option>
                {((platform?.scenario?.report_categories as { key: string; label: string }[]) || []).map((c) => (
                  <option key={c.key} value={c.key}>
                    {c.label}
                  </option>
                ))}
              </select>
            </div>
            {queue === "pending" ? <div className="mt-2 text-[14px] text-[var(--muted)]">依嚴重程度排序。審核後才會進入案件佇列。</div> : null}
          </div>
          <ul className="max-h-[640px] flex-1 divide-y overflow-y-auto xl:max-h-[calc(100vh-360px)]" style={{ borderColor: "var(--line)" }}>
            {cases.length === 0 ? (
              <li className="p-6 text-center text-[16px] text-[var(--muted)]">{queue === "pending" ? "目前沒有待審核的災情。" : "沒有符合條件的案件。"}</li>
            ) : (
              cases.map((c) => (
                <li key={c.id} className={`af-row-hover relative cursor-pointer py-3 pl-5 pr-3 ${selectedId === `case:${c.id}` ? "bg-[var(--surface-2)]" : ""}`} onClick={() => setSelectedId(`case:${c.id}`)}>
                  <span className="absolute inset-y-0 left-0 w-1.5" style={{ background: SEVERITY_HEX[c.severity] }} />
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2 text-[13px] text-[var(--muted)]">
                        <span className="font-mono">{c.case_number}</span>
                        <SeverityTag severity={c.severity} />
                      </div>
                      <Link href={`/console/platforms/${id}/cases/${c.id}`} className="mt-0.5 flex items-center gap-2 text-[17px] font-semibold text-[var(--ink)] hover:underline" onClick={(e) => e.stopPropagation()}>
                        <CategoryBadge category={c.category} size={28} />
                        <span className="truncate">{c.title}</span>
                      </Link>
                      <div className="mt-0.5 text-[14px] text-[var(--muted)]">
                        {c.town} · {c.unique_reporter_count} 人回報 · {fmtAgo(c.created_at)}
                        {c.emic_status ? ` · EMIC：${c.emic_status}` : ""}
                      </div>
                    </div>
                    <div className="flex flex-none flex-col items-end gap-1.5">
                      <StatusPill status={c.status} phase={c.phase} console />
                      <Link href={`/console/platforms/${id}/cases/${c.id}`} className={`af-btn ${c.status === "pending_review" || c.status === "community_submitted" ? "af-btn-primary" : "af-btn-secondary"}`} onClick={(e) => e.stopPropagation()}>
                        {actionLabel(c)}
                      </Link>
                    </div>
                  </div>
                </li>
              ))
            )}
          </ul>
        </aside>

        {/* map */}
        <section className="af-panel relative min-w-0 overflow-hidden xl:order-1 xl:col-span-7">
          <div className="h-[560px] xl:h-[calc(100vh-240px)] xl:min-h-[620px]">
            {platform ? (
              <TerrainMap center={center} zoom={platform.configuration?.map?.zoom ?? 11} features={features} officialLayers={official} visible={visible} enabledLayers={layers} selectedId={selectedId} onSelect={onSelect} threeD={threeD} fitToData fitPadding={{ top: 80, bottom: 60, left: 260, right: 40 }} />
            ) : (
              <Skeleton className="h-full w-full" />
            )}
          </div>
          <div className="absolute left-2 top-2 z-[5] w-[240px] max-w-[calc(100%-1rem)]">
            {/* on a phone the panel would cover the map, so it folds away behind a toggle */}
            <button type="button" onClick={() => setLayerPanel((v) => !v)} className="af-btn af-btn-secondary mb-1 w-full justify-center sm:hidden">
              圖層與圖例 {layerPanel ? "▲" : "▼"}
            </button>
            <div className={`af-panel max-h-[620px] overflow-y-auto p-3 shadow-md ${layerPanel ? "" : "hidden sm:block"}`}>
              <div className="mb-2 flex items-center gap-1.5">
                <button type="button" className={`af-hud-chip ${threeD ? "af-hud-chip-on" : ""}`} onClick={() => setThreeD((v) => !v)}>
                  {threeD ? "3D 地形" : "2D"}
                </button>
              </div>
              <div className="mb-2 border-b pb-2" style={{ borderColor: "var(--line)" }}>
                <div className="af-eyebrow mb-1">天氣</div>
                <div className="flex flex-wrap items-center gap-1">
                  {WEATHER_LAYERS.filter((k) => layers.includes(k)).map((k) => {
                    const meta = LAYERS[k];
                    const data = official[k];
                    const st = statuses.find((x) => x.layer === k);
                    const on = visible[k] === true;
                    const disabled = st?.status === "disabled";
                    return (
                      <button key={k} type="button" disabled={disabled} onClick={() => toggle(k)} aria-pressed={on} className={`af-hud-chip ${on ? "af-hud-chip-on" : ""}`} title={disabled ? st?.detail || "尚未設定資料來源" : meta?.label}>
                        <span className="inline-block h-2 w-2 rounded-sm" style={{ background: disabled ? "var(--line-2)" : meta?.hex }} />
                        {meta?.label}
                        {on && !data ? <span className="af-spinner !h-2.5 !w-2.5" /> : null}
                        {disabled ? <span className="opacity-60">·未設定</span> : null}
                      </button>
                    );
                  })}
                </div>
              </div>
              <LayerPanel enabledLayers={layers} visible={visible} onToggle={toggle} counts={counts} officialLayers={official} statuses={statuses} compact />
            </div>
          </div>
        </section>
      </div>

      {/* lower section */}
      <div ref={tabsRef} className="mt-4 grid gap-4 xl:grid-cols-12">
        <section className="af-panel min-w-0 xl:col-span-8">
          <div className="flex flex-wrap items-center gap-1 border-b px-2 py-2" style={{ borderColor: "var(--line)" }}>
            {(
              [
                ["clusters", `未成案地點 (${clusters.length})`],
                ["reports", "最新通報"],
                ["line", "LINE 通知"],
                ["policy", "成案規則"],
                ["layers", "圖層狀態"],
                ["intel", "官方情資"],
                ["feed", "事件紀錄"],
              ] as const
            ).map(([k, label]) => (
              <button key={k} type="button" onClick={() => setTab(k)} className={`rounded px-3 py-2 text-[15px] ${tab === k ? "bg-[var(--surface-3)] font-semibold text-[var(--ink)]" : "text-[var(--muted)] hover:text-[var(--ink)]"}`}>
                {label}
              </button>
            ))}
          </div>
          <div className="max-h-[560px] overflow-auto">
            {tab === "clusters" ? (
              clusters.length === 0 ? (
                <div className="p-5 text-[15px] text-[var(--muted)]">目前沒有尚未成案的回報地點。</div>
              ) : (
                <div className="overflow-x-auto">
                <table className="af-table min-w-[640px]">
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
                        <td>{c.town || "—"}</td>
                        <td className="tabular-nums">
                          {c.unique_reporter_count} 人 / {c.report_count} 筆
                        </td>
                        <td>
                          <SeverityTag severity={c.severity} withLabel={false} />
                        </td>
                        <td className="text-[var(--muted)]">{fmtAgo(c.last_reported_at)}</td>
                        <td className="text-right">
                          {can("review_cases") ? (
                            <button type="button" className="af-btn af-btn-secondary" disabled={busy === c.cluster_id} onClick={(e) => { e.stopPropagation(); promote(c.cluster_id); }} title="未達多人回報門檻，但判斷可信：直接送入審核">
                              人工成案
                            </button>
                          ) : null}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                </div>
              )
            ) : null}
            {tab === "reports" ? (
              <div className="overflow-x-auto">
              <table className="af-table min-w-[720px]">
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
                      <td className="whitespace-nowrap font-mono text-[13px] text-[var(--muted)]">{fmtTime(r.created_at)}</td>
                      <td>
                        <div className="font-medium">{CATEGORY_LABEL[r.category] || r.category}</div>
                        <div className="max-w-xs truncate text-[14px] text-[var(--muted)]">{r.description}</div>
                      </td>
                      <td className="text-[15px]">
                        {r.town}
                        <div className="text-[13px] text-[var(--muted)]">{r.address}</div>
                      </td>
                      <td className="text-[15px]">
                        {ROLE_LABEL[r.reporter_role] || r.reporter_role}
                        <div className="text-[13px] text-[var(--muted)]">
                          {r.pii_hidden ? "已留聯絡資料（開啟案件查看）" : r.has_identity ? "已留識別" : "匿名"}
                          {r.notify_opt_in ? " · 訂閱進度" : ""}
                        </div>
                      </td>
                      <td>
                        <SeverityTag severity={r.triage_severity} withLabel={false} />
                      </td>
                      <td className="text-[15px]">
                        {r.case_id ? (
                          <Link href={`/console/platforms/${id}/cases/${r.case_id}`} className="text-[var(--focus)] hover:underline">
                            已成案
                          </Link>
                        ) : r.status === "rejected" ? (
                          "已排除"
                        ) : r.cluster_id ? (
                          "未達門檻"
                        ) : (
                          "無座標"
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
            ) : null}
            {tab === "line" ? (
              <div className="p-4">
                <LinePanel platformId={id} canManage={can("manage_line")} onChange={setLine} />
              </div>
            ) : null}
            {tab === "layers" ? (
              <div className="overflow-x-auto">
              <table className="af-table min-w-[560px]">
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
                      <td>{s.kind === "official" ? "官方資料" : "平台資料"}</td>
                      <td className="font-mono text-[13px] text-[var(--muted)]">{s.source || "—"}</td>
                      <td>
                        <span className="inline-flex items-center gap-1.5">
                          <span className="h-2 w-2 rounded-full" style={{ background: s.status === "ok" || s.status === "ready" ? "var(--st-done)" : s.status === "unavailable" ? "var(--sev-high)" : "var(--st-pending)" }} />
                          {s.status === "ok" ? "正常" : s.status === "ready" ? "可介接" : s.status === "unavailable" ? "上游無法取得" : "未設定金鑰"}
                        </span>
                        {s.detail ? <div className="text-[13px] text-[var(--muted)]">{s.detail}</div> : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
            ) : null}
            {tab === "policy" && policyDraft ? (
              <div className="p-5">
                <div className="grid max-w-2xl grid-cols-1 gap-3 sm:grid-cols-3">
                  {(
                    [
                      ["required_unique_reporters", "不同回報者門檻（人）"],
                      ["radius_meters", "同地點半徑（公尺）"],
                      ["time_window_minutes", "時間窗（分鐘）"],
                    ] as const
                  ).map(([k, label]) => (
                    <label key={k}>
                      <span className="af-label">{label}</span>
                      <input type="number" className="af-input mt-1" value={policyDraft[k]} disabled={!can("manage_platforms")} onChange={(e) => setPolicyDraft({ ...policyDraft, [k]: Number(e.target.value) })} />
                    </label>
                  ))}
                </div>
                <div className="mt-3 flex flex-wrap items-center gap-3">
                  {can("manage_platforms") ? (
                    <button type="button" className="af-btn af-btn-primary" disabled={busy === "policy"} onClick={savePolicy}>
                      儲存規則
                    </button>
                  ) : (
                    <span className="text-[14px] text-[var(--muted)]">成案規則由系統管理者設定。</span>
                  )}
                  <span className="text-[14px] text-[var(--muted)]">同一地點達門檻會自動成案並進入待審核；同一人重複送出只計一次。變更只影響之後的通報。</span>
                </div>
              </div>
            ) : null}
            {tab === "intel" ? <IntelPanel platformId={id} enabledLayers={layers} cases={cases} selectedCase={cases.find((c) => `case:${c.id}` === selectedId) || null} active={tab === "intel"} /> : null}
            {tab === "feed" ? (
              audit.length === 0 ? (
                <div className="p-5 text-[15px] text-[var(--muted)]">尚無事件。</div>
              ) : (
                <ul className="divide-y text-[15px]" style={{ borderColor: "var(--line)" }}>
                  {audit.map((e) => (
                    <li key={e.id} className="flex gap-3 px-3 py-2">
                      <span className="w-28 flex-none font-mono text-[13px] text-[var(--muted)]">{fmtTime(e.created_at)}</span>
                      <span className="w-48 flex-none font-mono text-[13px] text-[var(--ink-2)]">{e.event_type}</span>
                      <span className="truncate text-[var(--muted)]">
                        {e.payload.case_number ? `${e.payload.case_number} ` : ""}
                        {e.payload.to_status ? `→ ${e.payload.to_status} ` : ""}
                        {e.payload.actor_name ? `(${e.payload.actor_name})` : ""}
                      </span>
                    </li>
                  ))}
                </ul>
              )
            ) : null}
          </div>
        </section>

        <section className="af-panel min-w-0 p-4 xl:col-span-4">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="af-h2">即時動態</h2>
            <span className="inline-flex items-center gap-1.5 text-[13px] text-[var(--muted)]">
              <span className="af-live-dot" /> 每 8 秒更新
            </span>
          </div>
          <EventFeed platformId={id} className="mb-4 max-h-[320px] overflow-y-auto pr-1" />
          <h2 className="af-h2 mb-2">趨勢與分布</h2>
          {overview ? (
            <>
              <TrendChart trend={overview.trend} height={120} />
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
              <div className="mt-3 text-[14px] text-[var(--muted)]">
                結案中位時間 {fmtDuration(overview.median_close_minutes)} · 近 1 小時 {overview.reports_last_hour} 筆通報 · 訂閱進度 {overview.reports_subscribed} 人 · 已排除 {overview.reports_rejected}
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
