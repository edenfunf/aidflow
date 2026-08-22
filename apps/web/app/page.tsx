"use client";

// System console — the product's front door.
//
//   描述災害背景 → 系統理解並規劃 → 人工確認 → 生成兩套系統
//                                                ├ 民眾通報網站  /p/{slug}
//                                                └ 政府管理後台  /console/platforms/{id}
//
// Everything here serves that one narrative: the generator input sits on the
// live 3D map of the most recent platform, and every platform below is shown
// as a pair of doors, never as a single ambiguous link.

import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import CountUp from "@/components/CountUp";
import Spark from "@/components/Spark";
import { BrandLockup } from "@/components/Brand";
import { CategoryIcon } from "@/lib/categoryIcons";
import { EmptyState, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { HAZARD_LABEL } from "@/lib/labels";
import { fmtAgo, fmtTime } from "@/lib/format";
import type { PlatformItem, PublicPlatform, Situation } from "@/lib/types";

const TerrainMap = dynamic(() => import("@/components/TerrainMap"), { ssr: false, loading: () => <Skeleton className="h-full w-full !rounded-none" /> });

const EXAMPLE =
  "南投縣仁愛鄉因颱風帶來連續豪雨，多處山區道路可能發生坍方、土石流與積淹水，部分偏遠部落可能交通中斷，希望民眾、村里長、防災士與志工都可以共同回報災情。";

// No disaster is declared at console level: the map is simply Taiwan, framed
// so the island is the subject and the generator card covers the mainland.
const TAIWAN_CENTER: [number, number] = [23.45, 121.05];
/** Wide screens can hold the island at a closer zoom; phones need to pull back. */
function taiwanZoom(width: number): number {
  if (width >= 1600) return 7.6;
  if (width >= 1280) return 7.3;
  if (width >= 900) return 7.0;
  return 6.4;
}

const STEPS: [string, string, string, string, string][] = [
  ["1", "描述災害背景", "地區、災害類型、可能災情與希望誰能回報。", "trapped_person", "#be123c"],
  ["2", "系統理解並規劃", "辨識災害與行政區，挑出通報類別、官方圖層與成案規則。", "landslide", "#ca8a04"],
  ["3", "人工確認", "每項建議都可改；成案規則永遠是確定性規則。", "road_collapse", "#ea580c"],
  ["4", "生成兩套系統", "民眾通報網站與政府管理後台同時產生。", "flooding", "#2563eb"],
];

/** The generation flow as a connected column — sits beside the island on wide
 * screens, and folds under the hero on small ones. */
function FlowSteps({ compact = false }: { compact?: boolean }) {
  return (
    <ol className="relative">
      <span className="absolute bottom-4 left-[17px] top-4 w-px" style={{ background: "var(--line-2)" }} aria-hidden="true" />
      {STEPS.map(([n, t, d, cat, hex], i) => (
        <li key={n} className={`af-rise relative flex gap-3 ${i ? "mt-4" : ""}`} style={{ animationDelay: `${(i + 1) * 90}ms` }}>
          <span className="relative z-10 grid h-[35px] w-[35px] flex-none place-items-center rounded-full text-white ring-4" style={{ background: hex, boxShadow: "0 2px 8px -4px rgba(16,24,40,.5)", ["--tw-ring-color" as string]: "rgba(255,255,255,.85)" }}>
            <CategoryIcon category={cat} size={17} />
          </span>
          <div className="min-w-0 pt-0.5">
            <div className="af-eyebrow !text-[10px]">STEP {n}</div>
            <div className="mt-0.5 text-[14px] font-semibold leading-tight text-[var(--ink)]">{t}</div>
            {compact ? null : <p className="mt-1 text-[11.5px] leading-snug text-[var(--muted)]">{d}</p>}
          </div>
        </li>
      ))}
    </ol>
  );
}

function CitizenIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.1" strokeLinecap="round" aria-hidden="true">
      <circle cx="12" cy="8" r="3.2" />
      <path d="M5.5 20v-1.5a6.5 6.5 0 0 1 13 0V20" />
    </svg>
  );
}

function GovIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M4 20V9l8-5 8 5v11" />
      <path d="M9 20v-6h6v6" />
    </svg>
  );
}

export default function SystemConsolePage() {
  const router = useRouter();
  const [brief, setBrief] = useState("");
  const [items, setItems] = useState<PublicPlatform[] | null>(null);
  const [admin, setAdmin] = useState<Record<string, PlatformItem>>({});
  const [error, setError] = useState<string | null>(null);
  const [situations, setSituations] = useState<Record<string, Situation>>({});

  useEffect(() => {
    api
      .publicPlatforms()
      .then((r) => setItems(r.items))
      .catch((e) => setError((e as Error).message));
    // the admin listing carries each platform's id — the door to its console
    api
      .listPlatforms()
      .then((r) => setAdmin(Object.fromEntries(r.items.map((p) => [p.slug, p]))))
      .catch(() => undefined);
  }, []);

  const heroVisible = useMemo(() => ({}), []);
  const noLayers = useMemo<string[]>(() => [], []);
  // decided after mount: the map is created once with this zoom
  const [heroZoom, setHeroZoom] = useState<number | null>(null);
  useEffect(() => setHeroZoom(taiwanZoom(window.innerWidth)), []);
  const generate = () => router.push(`/console/new${brief.trim() ? `?brief=${encodeURIComponent(brief.trim())}` : ""}`);

  return (
    <div className="min-h-screen">
      {/* the map owns the top of the page; the header floats on it */}
      <section className="relative" style={{ height: "min(94vh, 960px)", background: "#dfe6ee" }}>
        {heroZoom !== null ? (
          <TerrainMap
            center={TAIWAN_CENTER}
            zoom={heroZoom}
            features={[]}
            visible={heroVisible}
            enabledLayers={noLayers}
            threeD
            orbit
            minimal
            className="absolute inset-0"
          />
        ) : null}
        <div className="af-topfade pointer-events-none absolute inset-x-0 top-0 h-28" />

        <header className="absolute inset-x-0 top-0 z-20">
          <div className="mx-auto flex max-w-[1200px] items-center justify-between px-4 py-3.5">
            <BrandLockup subtitle="災情平台生成系統" />
            <nav className="flex items-center gap-2">
              <Link href="/console" className="af-btn af-btn-secondary text-xs">
                平台管理
              </Link>
              <Link href="/console/new" className="af-btn af-btn-primary text-xs">
                建立平台
              </Link>
            </nav>
          </div>
        </header>

        <div className="pointer-events-none absolute inset-0 flex items-center justify-between gap-6 px-5 sm:px-8 xl:px-12">
          <div className="af-hero-card pointer-events-auto w-full max-w-[500px] p-6">
            <div className="af-eyebrow">系統控制台</div>
            <h1 className="mt-1.5 text-[26px] font-semibold leading-tight text-[var(--ink)]">輸入災害背景，生成一整套災情平台</h1>
            <p className="mt-2 text-[13px] leading-relaxed text-[var(--muted)]">
              系統理解情境後提出規劃，經人工確認即產生<b className="text-[var(--ink-2)]">民眾通報網站</b>與<b className="text-[var(--ink-2)]">政府管理後台</b>兩套系統：民眾回報災情，政府在同一份資料上派工。
            </p>
            <textarea
              className="af-input mt-3 min-h-[104px] text-[13px]"
              value={brief}
              onChange={(e) => setBrief(e.target.value)}
              placeholder={EXAMPLE}
              maxLength={4000}
              onKeyDown={(e) => {
                if ((e.metaKey || e.ctrlKey) && e.key === "Enter") generate();
              }}
            />
            <div className="mt-2.5 flex flex-wrap items-center gap-2">
              <button type="button" className="af-btn af-btn-primary" onClick={generate} disabled={!brief.trim()}>
                分析情境並提出規劃
              </button>
              <button type="button" className="af-btn af-btn-ghost text-xs" onClick={() => setBrief(EXAMPLE)}>
                帶入範例
              </button>
              <span className="text-[11px] text-[var(--faint)]">或 ⌘/Ctrl + Enter</span>
            </div>
            <p className="mt-3 border-t pt-2.5 text-[11px] text-[var(--faint)]" style={{ borderColor: "var(--line)" }}>
              目前尚未指定災害事件，地圖顯示全臺地形；生成平台後會自動聚焦該災區並顯示即時災情。
            </p>
          </div>

          {/* the flow, over the sea east of the island */}
          <div className="af-hero-card pointer-events-auto hidden w-[300px] flex-none p-5 xl:block">
            <div className="af-eyebrow mb-3">生成流程</div>
            <FlowSteps />
          </div>
        </div>
      </section>

      {/* small screens: the same flow, folded under the hero */}
      <section className="border-b xl:hidden" style={{ background: "var(--surface)", borderColor: "var(--line)" }}>
        <div className="mx-auto max-w-[520px] px-4 py-6">
          <div className="af-eyebrow mb-3">生成流程</div>
          <FlowSteps />
        </div>
      </section>

      {/* every generated platform, shown as its two systems */}
      <main className="af-page mx-auto max-w-[1200px] px-4 py-8">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-2">
          <div>
            <div className="af-eyebrow">已生成的平台</div>
            <h2 className="af-h1 mt-1">目前運作中的災情事件</h2>
            <p className="mt-1 text-sm text-[var(--muted)]">每個平台對應一場災害，同時包含民眾通報網站與政府管理後台。</p>
          </div>
          {items?.length ? <div className="text-xs text-[var(--muted)]">{items.length} 個平台</div> : null}
        </div>
        {error ? <div className="mb-4 text-sm text-[var(--sev-high)]">{error}</div> : null}
        {items === null ? (
          <div className="grid gap-3 lg:grid-cols-2">
            <Skeleton className="h-52" />
            <Skeleton className="h-52" />
          </div>
        ) : items.length === 0 ? (
          <EmptyState
            title="尚未生成任何災情平台"
            detail="在上方輸入災害背景，系統會提出規劃；確認後即生成民眾通報網站與政府管理後台。"
            action={
              <button type="button" className="af-btn af-btn-primary" onClick={() => setBrief(EXAMPLE)}>
                帶入範例背景
              </button>
            }
          />
        ) : (
          <ul className="grid gap-3 lg:grid-cols-2">
            {items.map((p) => {
              const s = situations[p.slug];
              const a = admin[p.slug];
              return (
                <li key={p.id} className="af-panel af-panel-hover flex flex-col p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="text-[11px] text-[var(--muted)]">
                        {p.county || "—"} · {p.hazard_labels?.length ? p.hazard_labels.join("、") : p.hazards.map((h) => HAZARD_LABEL[h] || h).join("、")}
                      </div>
                      <h3 className="mt-0.5 truncate text-base font-semibold text-[var(--ink)]">{p.name}</h3>
                      <div className="mt-1 text-xs text-[var(--muted)]">
                        {p.towns.length ? p.towns.join("、") : "全縣"} · 生成於 {fmtTime(p.published_at)}
                        {s?.last_report_at ? ` · 最近通報 ${fmtAgo(s.last_report_at)}` : ""}
                      </div>
                    </div>
                    {s ? (
                      <div className="flex-none text-right">
                        <Spark values={s.trend.map((b) => b.reports)} width={110} height={26} />
                        <div className="mt-0.5 text-[10px] text-[var(--faint)]">近 24 小時 {s.reports_last_24h} 筆</div>
                      </div>
                    ) : null}
                  </div>

                  <div className="mt-3 flex gap-5">
                    {[
                      ["進行中", s?.cases_open, "var(--ink)"],
                      ["待派工", s?.cases_pending, "var(--st-pending)"],
                      ["處理中", s?.cases_active, "var(--st-active)"],
                      ["已完成", s?.cases_done, "var(--st-done)"],
                    ].map(([label, value, color]) => (
                      <div key={String(label)}>
                        <div className="text-lg font-semibold leading-none tabular-nums" style={{ color: String(color) }}>
                          {value === undefined ? "–" : <CountUp value={Number(value)} />}
                        </div>
                        <div className="mt-0.5 text-[10px] text-[var(--muted)]">{label}</div>
                      </div>
                    ))}
                  </div>

                  {/* the two generated systems */}
                  <div className="mt-4 grid gap-2 sm:grid-cols-2">
                    <Link href={`/p/${p.slug}`} className="af-subtle af-panel-hover block rounded p-3 transition">
                      <div className="flex items-center gap-2">
                        <span className="grid h-7 w-7 flex-none place-items-center rounded-full text-white" style={{ background: "var(--st-active)" }}>
                          <CitizenIcon />
                        </span>
                        <span className="text-[13px] font-semibold text-[var(--ink)]">民眾通報網站</span>
                      </div>
                      <p className="mt-1 text-[11px] leading-snug text-[var(--muted)]">3D 災情態勢、我要通報、案件處理進度</p>
                    </Link>
                    {a ? (
                      <Link href={`/console/platforms/${a.id}`} className="af-subtle af-panel-hover block rounded p-3 transition">
                        <div className="flex items-center gap-2">
                          <span className="grid h-7 w-7 flex-none place-items-center rounded-full text-white" style={{ background: "var(--brand)" }}>
                            <GovIcon />
                          </span>
                          <span className="text-[13px] font-semibold text-[var(--ink)]">政府管理後台</span>
                        </div>
                        <p className="mt-1 text-[11px] leading-snug text-[var(--muted)]">案件佇列、一鍵派遣、官方情資、稽核</p>
                      </Link>
                    ) : (
                      <div className="af-subtle rounded p-3 text-[11px] text-[var(--faint)]">政府管理後台（載入中）</div>
                    )}
                  </div>

                  <div className="mt-2 flex flex-wrap gap-3 text-[11px]">
                    <Link href={`/p/${p.slug}/report`} className="text-[var(--focus)] hover:underline">
                      我要通報 →
                    </Link>
                    <Link href={`/p/${p.slug}/wall`} className="text-[var(--focus)] hover:underline">
                      戰情牆 →
                    </Link>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </main>

      {/* official sources: the platform draws only from these */}
      <footer className="border-t" style={{ background: "var(--surface)", borderColor: "var(--line)" }}>
        <div className="mx-auto flex max-w-[1200px] flex-wrap items-center gap-x-5 gap-y-2 px-4 py-4 text-[11px] text-[var(--muted)]">
          <span className="af-eyebrow">官方資料來源</span>
          {["中央氣象署", "經濟部水利署", "農村發展及水土保持署", "內政部消防署", "內政部戶政司", "交通部 TDX", "南投縣政府開放資料", "台灣電力公司", "OpenStreetMap · AWS Terrain"].map((x) => (
            <span key={x} className="inline-flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full" style={{ background: "var(--st-done)" }} />
              {x}
            </span>
          ))}
          <span className="ml-auto">未設定金鑰的來源會標示「無資料」，不以假資料替代。</span>
        </div>
      </footer>
    </div>
  );
}
