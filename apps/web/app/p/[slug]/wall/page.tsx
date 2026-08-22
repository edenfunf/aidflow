"use client";

// Wall / kiosk mode: full-screen situation map that runs itself — slow
// camera orbit, live vehicles, and a side column that cycles through the
// latest cases, responding units, township breakdown and the 24-hour trend.
// Meant for an EOC wall display or an exhibition screen; no interaction needed.

import dynamic from "next/dynamic";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import CountUp from "@/components/CountUp";
import { BrandMark } from "@/components/Brand";
import TrendChart, { BreakdownBars } from "@/components/TrendChart";
import { Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { CategoryBadge } from "@/lib/categoryIcons";
import { fmtAgo } from "@/lib/format";
import { SEVERITY_HEX, VEHICLE_HEX, VEHICLE_LABEL, VEHICLE_STATUS_LABEL } from "@/lib/labels";
import type { CaseStatus, MapFeature, PublicCase, RouteFeature, VehicleItem } from "@/lib/types";
import { usePublicPlatform } from "@/lib/usePortal";

const TerrainMap = dynamic(() => import("@/components/TerrainMap"), { ssr: false, loading: () => <Skeleton className="h-full w-full !rounded-none" /> });

const PANEL_MS = 9000;
const PANELS = ["cases", "vehicles", "towns", "trend"] as const;
type Panel = (typeof PANELS)[number];
const PANEL_TITLE: Record<Panel, string> = { cases: "最新案件", vehicles: "出勤車輛", towns: "各鄉鎮災情", trend: "24 小時趨勢" };
const WALL_PHASE: Record<string, string> = { pending: "#f0a04b", active: "#8fb4ff", done: "#3ccf8e", dismissed: "#8b99ad" };
// how far along the handling path a status is (for the five progress dots)
const STEP_ORDER: CaseStatus[] = ["reported", "threshold_reached", "awaiting_dispatch", "assigned", "en_route", "on_site", "processing", "resolved", "closed"];
const STEPS: { label: string; from: CaseStatus }[] = [
  { label: "成案", from: "awaiting_dispatch" },
  { label: "派員", from: "assigned" },
  { label: "抵達", from: "on_site" },
  { label: "處理", from: "processing" },
  { label: "完成", from: "resolved" },
];
function stepsReached(status: CaseStatus): number {
  const i = STEP_ORDER.indexOf(status);
  return STEPS.filter((st) => STEP_ORDER.indexOf(st.from) <= i).length;
}

function PhaseBar({ pending, active, done }: { pending: number; active: number; done: number }) {
  const total = Math.max(1, pending + active + done);
  const segs = [
    ["待派工", pending, WALL_PHASE.pending],
    ["處理中", active, WALL_PHASE.active],
    ["已完成", done, WALL_PHASE.done],
  ] as const;
  return (
    <div>
      <div className="flex h-2 overflow-hidden rounded-full bg-white/10">
        {segs.map(([label, n, color]) => (n ? <span key={label} style={{ width: `${(n / total) * 100}%`, background: color }} /> : null))}
      </div>
      <div className="mt-1.5 flex gap-4 text-[11px] text-white/65">
        {segs.map(([label, n, color]) => (
          <span key={label} className="inline-flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-sm" style={{ background: color }} />
            {label} <span className="font-semibold text-white">{n}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

export default function WallPage() {
  const { slug } = useParams<{ slug: string }>();
  const { platform, situation, map, layers, visible } = usePublicPlatform(slug, 15000);
  const [cases, setCases] = useState<PublicCase[]>([]);
  const [routes, setRoutes] = useState<RouteFeature[]>([]);
  const [vehicles, setVehicles] = useState<VehicleItem[]>([]);
  const [panel, setPanel] = useState<Panel>("cases");
  const [clock, setClock] = useState("");

  useEffect(() => {
    const loadCases = () => api.publicCases(slug, { phase: "open", sort: "updated_desc", limit: 6 }).then((r) => setCases(r.items)).catch(() => undefined);
    const loadLive = () => {
      api.publicRoutes(slug).then((r) => setRoutes(r.features)).catch(() => undefined);
      api.publicVehicles(slug).then((r) => setVehicles(r.items)).catch(() => undefined);
    };
    loadCases();
    loadLive();
    const a = window.setInterval(loadCases, 20000);
    const b = window.setInterval(loadLive, 3000);
    return () => {
      window.clearInterval(a);
      window.clearInterval(b);
    };
  }, [slug]);

  useEffect(() => {
    const tick = () => setClock(new Date().toLocaleTimeString("zh-TW", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }));
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    const id = window.setInterval(() => setPanel((p) => PANELS[(PANELS.indexOf(p) + 1) % PANELS.length]), PANEL_MS);
    return () => window.clearInterval(id);
  }, []);

  const features = useMemo<MapFeature[]>(() => (map?.features || []).filter((f) => f.properties.layer === "incident_cases" || f.properties.layer === "report_clusters"), [map]);
  // the wall hangs in an operations centre, not on a public web page
  const wallVisible = useMemo(() => ({ ...visible, heatmap: false, dispatch: true }), [visible]);
  const moving = vehicles.filter((v) => v.status === "en_route" || v.status === "returning" || v.status === "live");

  return (
    <div className="af-wall">
      <header className="flex items-center justify-between px-5" style={{ borderBottom: "1px solid rgba(255,255,255,0.08)" }}>
        <div className="flex items-center gap-4">
          <BrandMark size={34} inverted />
          <div>
            <div className="text-[10.5px] uppercase tracking-[0.16em] text-white/50">{platform?.county ? `${platform.county}政府 · 災害應變中心` : "AidFlow"}</div>
            <div className="text-[17px] font-semibold leading-tight">{platform?.name || "災情態勢"}</div>
          </div>
          {situation ? (
            <div className="ml-6 hidden items-center gap-6 md:flex">
              {[
                ["目前災情", situation.cases_open, "#f1f5f9"],
                ["待派工", situation.cases_pending, "#f0a04b"],
                ["處理中", situation.cases_active, "#8fb4ff"],
                ["已完成", situation.cases_done, "#3ccf8e"],
                ["高風險", situation.cases_high_risk, "#ff7a6e"],
              ].map(([label, value, color]) => (
                <div key={String(label)} className="text-center">
                  <div className="text-2xl font-semibold leading-none" style={{ color: String(color) }}>
                    <CountUp value={Number(value)} />
                  </div>
                  <div className="mt-0.5 text-[10.5px] text-white/55">{label}</div>
                </div>
              ))}
            </div>
          ) : null}
        </div>
        <div className="flex items-center gap-4 text-right">
          <div>
            <div className="font-mono text-[22px] font-semibold leading-none tabular-nums">{clock}</div>
            <div className="mt-0.5 text-[10.5px] text-white/55">
              近 1 小時 {situation?.reports_last_hour ?? 0} 筆通報 · 出勤 {vehicles.length} 車
              {vehicles.some((v) => v.source === "avl") ? "" : "（模擬）"}
            </div>
          </div>
          <Link href={`/p/${slug}`} className="rounded border border-white/15 px-2 py-1 text-[11px] text-white/70 hover:bg-white/10">
            離開
          </Link>
        </div>
      </header>

      <div className="relative min-h-0">
        {platform ? (
          <TerrainMap center={platform.map.center} zoom={platform.map.zoom} features={features} visible={wallVisible} enabledLayers={[...layers, "dispatch"]} routes={routes} vehicles={vehicles} threeD orbit minimal fitToData className="absolute inset-0" />
        ) : (
          <Skeleton className="absolute inset-0 !rounded-none" />
        )}

        {/* side column: situation summary + rotating board */}
        <aside className="pointer-events-none absolute bottom-4 right-4 top-4 flex w-[380px] flex-col gap-3">
          {situation ? (
            <div className="af-wall-panel pointer-events-auto p-4">
              <div className="mb-2 flex items-baseline justify-between">
                <div className="text-[10.5px] uppercase tracking-[0.16em] text-white/50">態勢摘要</div>
                <div className="text-[11px] text-white/55">
                  {situation.trend_direction === "rising" ? "通報增加中" : situation.trend_direction === "falling" ? "通報趨緩" : "通報平穩"} · 近 24 小時 {situation.reports_last_24h} 筆
                </div>
              </div>
              <PhaseBar pending={situation.cases_pending} active={situation.cases_active} done={situation.cases_done} />
              {situation.cases_high_risk ? (
                <div className="mt-2 inline-flex items-center gap-1.5 rounded px-2 py-0.5 text-[11px] font-medium" style={{ background: "rgba(255,92,92,0.16)", color: "#ff8a80" }}>
                  <span className="h-1.5 w-1.5 rounded-full bg-current" /> {situation.cases_high_risk} 處高風險
                </div>
              ) : null}
            </div>
          ) : null}

          <div className="af-wall-panel pointer-events-auto flex min-h-0 flex-col p-4">
            <div className="mb-3 flex items-center gap-1 border-b border-white/10 pb-2">
              {PANELS.map((p) => (
                <button key={p} type="button" onClick={() => setPanel(p)} className={`rounded px-2 py-1 text-[12px] transition ${p === panel ? "bg-white/12 font-semibold text-white" : "text-white/55 hover:text-white/80"}`}>
                  {PANEL_TITLE[p]}
                </button>
              ))}
            </div>
            <div key={panel} className="af-wall-enter min-h-0 overflow-hidden">
              {panel === "cases" ? (
                <ul className="space-y-1.5">
                  {cases.map((c) => {
                    const reached = stepsReached(c.status);
                    const open = c.phase !== "done";
                    return (
                      <li key={c.id} className="relative overflow-hidden rounded-md bg-white/[0.05] py-2 pl-4 pr-3">
                        <span className="absolute inset-y-0 left-0 w-[3px]" style={{ background: SEVERITY_HEX[c.severity] }} />
                        <div className="flex items-center gap-3">
                          <CategoryBadge category={c.category} size={34} />
                          <div className="min-w-0 flex-1">
                            <div className="flex items-baseline justify-between gap-2">
                              <div className="truncate text-[14.5px] font-semibold">{c.title}</div>
                              <div className="flex-none text-[10.5px] text-white/45">{fmtAgo(c.updated_at)}</div>
                            </div>
                            <div className="mt-1 flex items-center gap-2 text-[11px] text-white/65">
                              <span className="inline-flex items-center gap-1 rounded px-1.5 py-[1px] font-medium" style={{ background: `${WALL_PHASE[c.phase]}22`, color: WALL_PHASE[c.phase] }}>
                                <span className="h-1.5 w-1.5 rounded-full bg-current" />
                                {c.status_label}
                              </span>
                              <span>{c.unique_reporter_count} 人回報</span>
                              <span>·</span>
                              <span>{c.town}</span>
                            </div>
                            {c.assigned_unit ? <div className="mt-0.5 truncate text-[11px] text-white/50">{c.assigned_unit}</div> : null}
                          </div>
                        </div>
                        {open ? (
                          <div className="mt-2 flex items-center gap-1 pl-[46px]">
                            {STEPS.map((st, i) => {
                              const on = i < reached;
                              const cur = i === reached - 1;
                              return (
                                <span key={st.label} className="flex items-center gap-1">
                                  <span className="h-1.5 w-1.5 rounded-full" style={{ background: on ? WALL_PHASE[c.phase] : "rgba(255,255,255,0.18)", boxShadow: cur ? `0 0 0 3px ${WALL_PHASE[c.phase]}33` : undefined }} />
                                  <span className={`text-[10px] ${on ? "text-white/75" : "text-white/30"}`}>{st.label}</span>
                                  {i < STEPS.length - 1 ? <span className="mx-0.5 h-px w-3" style={{ background: i < reached - 1 ? WALL_PHASE[c.phase] : "rgba(255,255,255,0.15)" }} /> : null}
                                </span>
                              );
                            })}
                          </div>
                        ) : null}
                      </li>
                    );
                  })}
                </ul>
              ) : null}
              {panel === "vehicles" ? (
                <ul className="space-y-1.5">
                  {vehicles.length === 0 ? <li className="py-4 text-sm text-white/60">目前沒有出勤車輛。</li> : null}
                  {[...moving, ...vehicles.filter((v) => !moving.includes(v))].slice(0, 10).map((v) => {
                    const isMoving = moving.includes(v);
                    return (
                      <li key={v.vehicle_id} className="flex items-center gap-3 rounded-md bg-white/[0.05] px-3 py-2">
                        <span className="grid h-9 w-9 flex-none place-items-center rounded-full text-[12px] font-semibold text-white" style={{ background: VEHICLE_HEX[v.kind] || "#475467", boxShadow: isMoving ? `0 0 0 3px ${VEHICLE_HEX[v.kind] || "#475467"}44` : undefined }}>
                          {(VEHICLE_LABEL[v.kind] || v.kind_label).slice(0, 1)}
                        </span>
                        <div className="min-w-0 flex-1">
                          <div className="truncate text-[13.5px] font-medium">{v.unit_name || "—"}</div>
                          <div className="truncate text-[11px] text-white/55">
                            {VEHICLE_LABEL[v.kind] || v.kind_label} → {v.case_title || "待命"}
                          </div>
                        </div>
                        <div className="flex-none text-right">
                          {v.status === "en_route" && v.eta_minutes ? (
                            <div className="text-[18px] font-semibold leading-none tabular-nums" style={{ color: "#8fb4ff" }}>
                              {v.eta_minutes}
                              <span className="text-[10.5px] font-normal text-white/55"> 分</span>
                            </div>
                          ) : (
                            <div className="text-[12px] font-medium" style={{ color: v.status === "on_site" ? "#3ccf8e" : "#d2dae5" }}>
                              {VEHICLE_STATUS_LABEL[v.status] || v.status}
                            </div>
                          )}
                          <div className="text-[10px] text-white/40">{v.source === "avl" ? "即時" : "模擬"}</div>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              ) : null}
              {panel === "towns" && situation ? (
                <div>
                  <BreakdownBars items={situation.by_town} max={8} />
                  <div className="mt-4 text-[10.5px] uppercase tracking-[0.16em] text-white/50">依災情類別</div>
                  <div className="mt-1">
                    <BreakdownBars items={situation.by_category} max={6} />
                  </div>
                </div>
              ) : null}
              {panel === "trend" && situation ? (
                <div>
                  <TrendChart trend={situation.trend} height={200} />
                  <div className="mt-3 grid grid-cols-2 gap-3 text-[12px] text-white/70">
                    <div>
                      近 24 小時通報 <span className="text-lg font-semibold text-white">{situation.reports_last_24h}</span>
                    </div>
                    <div>
                      未達門檻聚類 <span className="text-lg font-semibold text-white">{situation.clusters_open}</span>
                    </div>
                  </div>
                </div>
              ) : null}
            </div>
            <div className="af-wall-bar mt-3">
              <span key={panel} style={{ animationDuration: `${PANEL_MS}ms` }} />
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
