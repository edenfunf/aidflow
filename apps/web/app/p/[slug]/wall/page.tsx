"use client";

// Wall / kiosk mode: full-screen situation map that runs itself — slow
// camera orbit and a side column that cycles through the latest cases, the
// township breakdown and the 24-hour trend. Meant for an EOC wall display;
// no interaction needed.

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
import { SEVERITY_HEX } from "@/lib/labels";
import type { MapFeature, PublicCase } from "@/lib/types";
import { usePublicPlatform } from "@/lib/usePortal";

const TerrainMap = dynamic(() => import("@/components/TerrainMap"), { ssr: false, loading: () => <Skeleton className="h-full w-full !rounded-none" /> });

const PANEL_MS = 9000;
const PANELS = ["cases", "towns", "trend"] as const;
type Panel = (typeof PANELS)[number];
const PANEL_TITLE: Record<Panel, string> = { cases: "最新災情", towns: "各鄉鎮災情", trend: "24 小時趨勢" };
const WALL_PHASE: Record<string, string> = { pending: "#f0a04b", active: "#8fb4ff", community: "#4fc3d9", done: "#3ccf8e", dismissed: "#8b99ad" };

function PhaseBar({ pending, active, community }: { pending: number; active: number; community: number }) {
  const total = Math.max(1, pending + active + community);
  const segs = [
    ["審核中", pending, WALL_PHASE.pending],
    ["處理中（EMIC）", active, WALL_PHASE.active],
    ["民眾可協助", community, WALL_PHASE.community],
  ] as const;
  return (
    <div>
      <div className="flex h-2.5 overflow-hidden rounded-full bg-white/10">
        {segs.map(([label, n, color]) => (n ? <span key={label} style={{ width: `${(n / total) * 100}%`, background: color }} /> : null))}
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[14px] text-white/65">
        {segs.map(([label, n, color]) => (
          <span key={label} className="inline-flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm" style={{ background: color }} />
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
  const [panel, setPanel] = useState<Panel>("cases");
  const [clock, setClock] = useState("");

  useEffect(() => {
    const loadCases = () => api.publicCases(slug, { phase: "open", sort: "updated_desc", limit: 6 }).then((r) => setCases(r.items)).catch(() => undefined);
    loadCases();
    const a = window.setInterval(loadCases, 20000);
    return () => window.clearInterval(a);
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
  const wallVisible = useMemo(() => ({ ...visible, heatmap: false }), [visible]);

  return (
    <div className="af-wall">
      <header className="flex items-center justify-between px-5" style={{ borderBottom: "1px solid rgba(255,255,255,0.08)" }}>
        <div className="flex items-center gap-4">
          <BrandMark size={36} inverted />
          <div>
            <div className="text-[13px] tracking-[0.14em] text-white/50">{platform?.county ? `${platform.county}政府 · 災害應變中心` : "AidFlow"}</div>
            <div className="text-[19px] font-semibold leading-tight">{platform?.name || "災情態勢"}</div>
          </div>
          {situation ? (
            <div className="ml-6 hidden items-center gap-6 md:flex">
              {[
                ["目前災情", situation.cases_open, "#f1f5f9"],
                ["審核中", situation.cases_pending, "#f0a04b"],
                ["處理中", situation.cases_active, "#8fb4ff"],
                ["民眾可協助", situation.cases_community, "#4fc3d9"],
                ["高風險", situation.cases_high_risk, "#ff7a6e"],
              ].map(([label, value, color]) => (
                <div key={String(label)} className="text-center">
                  <div className="text-[28px] font-semibold leading-none" style={{ color: String(color) }}>
                    <CountUp value={Number(value)} />
                  </div>
                  <div className="mt-0.5 text-[13px] text-white/55">{label}</div>
                </div>
              ))}
            </div>
          ) : null}
        </div>
        <div className="flex items-center gap-4 text-right">
          <div>
            <div className="font-mono text-[24px] font-semibold leading-none tabular-nums">{clock}</div>
            <div className="mt-0.5 text-[13px] text-white/55">近 1 小時 {situation?.reports_last_hour ?? 0} 筆通報</div>
          </div>
          <Link href={`/p/${slug}`} className="rounded border border-white/15 px-2.5 py-1.5 text-[14px] text-white/70 hover:bg-white/10">
            離開
          </Link>
        </div>
      </header>

      <div className="relative min-h-0">
        {platform ? (
          <TerrainMap center={platform.map.center} zoom={platform.map.zoom} features={features} visible={wallVisible} enabledLayers={layers} threeD orbit minimal fitToData className="absolute inset-0" />
        ) : (
          <Skeleton className="absolute inset-0 !rounded-none" />
        )}

        <aside className="pointer-events-none absolute bottom-4 right-4 top-4 flex w-[400px] flex-col gap-3">
          {situation ? (
            <div className="af-wall-panel pointer-events-auto p-4">
              <div className="mb-2 flex items-baseline justify-between">
                <div className="text-[13px] tracking-[0.14em] text-white/50">態勢摘要</div>
                <div className="text-[14px] text-white/55">
                  {situation.trend_direction === "rising" ? "通報增加中" : situation.trend_direction === "falling" ? "通報趨緩" : "通報平穩"} · 近 24 小時 {situation.reports_last_24h} 筆
                </div>
              </div>
              <PhaseBar pending={situation.cases_pending} active={situation.cases_active} community={situation.cases_community} />
              {situation.cases_high_risk ? (
                <div className="mt-2 inline-flex items-center gap-1.5 rounded px-2 py-0.5 text-[14px] font-medium" style={{ background: "rgba(255,92,92,0.16)", color: "#ff8a80" }}>
                  <span className="h-2 w-2 rounded-full bg-current" /> {situation.cases_high_risk} 處高風險
                </div>
              ) : null}
            </div>
          ) : null}

          <div className="af-wall-panel pointer-events-auto flex min-h-0 flex-col p-4">
            <div className="mb-3 flex items-center gap-1 border-b border-white/10 pb-2">
              {PANELS.map((p) => (
                <button key={p} type="button" onClick={() => setPanel(p)} className={`rounded px-2.5 py-1 text-[15px] transition ${p === panel ? "bg-white/12 font-semibold text-white" : "text-white/55 hover:text-white/80"}`}>
                  {PANEL_TITLE[p]}
                </button>
              ))}
            </div>
            <div key={panel} className="af-wall-enter min-h-0 overflow-hidden">
              {panel === "cases" ? (
                <ul className="space-y-1.5">
                  {cases.map((c) => (
                    <li key={c.id} className="relative overflow-hidden rounded-md bg-white/[0.05] py-2.5 pl-4 pr-3">
                      <span className="absolute inset-y-0 left-0 w-[3px]" style={{ background: SEVERITY_HEX[c.severity] }} />
                      <div className="flex items-center gap-3">
                        <CategoryBadge category={c.category} size={38} />
                        <div className="min-w-0 flex-1">
                          <div className="flex items-baseline justify-between gap-2">
                            <div className="truncate text-[17px] font-semibold">{c.title}</div>
                            <div className="flex-none text-[13px] text-white/45">{fmtAgo(c.updated_at)}</div>
                          </div>
                          <div className="mt-1 flex flex-wrap items-center gap-2 text-[14px] text-white/65">
                            <span className="inline-flex items-center gap-1 rounded px-1.5 py-[1px] font-medium" style={{ background: `${WALL_PHASE[c.phase]}22`, color: WALL_PHASE[c.phase] }}>
                              <span className="h-1.5 w-1.5 rounded-full bg-current" />
                              {c.status_label}
                            </span>
                            <span>{c.unique_reporter_count} 人回報</span>
                            <span>·</span>
                            <span>{c.town}</span>
                          </div>
                          {c.emic_status || c.assigned_unit ? <div className="mt-0.5 truncate text-[13px] text-white/50">{[c.emic_status && `EMIC：${c.emic_status}`, c.assigned_unit].filter(Boolean).join(" · ")}</div> : null}
                        </div>
                      </div>
                    </li>
                  ))}
                </ul>
              ) : null}
              {panel === "towns" && situation ? (
                <div>
                  <BreakdownBars items={situation.by_town} max={8} />
                  <div className="mt-4 text-[13px] tracking-[0.14em] text-white/50">依災情類別</div>
                  <div className="mt-1">
                    <BreakdownBars items={situation.by_category} max={6} />
                  </div>
                </div>
              ) : null}
              {panel === "trend" && situation ? (
                <div>
                  <TrendChart trend={situation.trend} height={200} />
                  <div className="mt-3 grid grid-cols-2 gap-3 text-[15px] text-white/70">
                    <div>
                      近 24 小時通報 <span className="text-xl font-semibold text-white">{situation.reports_last_24h}</span>
                    </div>
                    <div>
                      未達門檻地點 <span className="text-xl font-semibold text-white">{situation.clusters_open}</span>
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
