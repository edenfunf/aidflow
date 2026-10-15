"use client";

// Heads-up overlays for the map-first public portal: status strip, layer
// chips, case panel (list + selected case) and the legend.

import Link from "next/link";
import { useState } from "react";
import { ProgressSteps } from "@/components/CaseTimeline";
import LayerPanel from "@/components/LayerPanel";
import { CategoryBadge } from "@/lib/categoryIcons";
import { SeverityTag, StatusPill } from "@/components/ui";
import { api } from "@/lib/api";
import { fmtAgo, fmtClock } from "@/lib/format";
import { LAYERS, PHASE_HEX, PHASE_LABEL, TREND_LABEL } from "@/lib/labels";
import type { LayerResponse, LayerStatusItem, Phase, PublicCase, PublicCaseDetail, Situation } from "@/lib/types";

// ── status strip ─────────────────────────────────────────────────────
export function StatusStrip({ situation, county }: { situation: Situation | null; county: string | null }) {
  const items: { v: number; label: string; color?: string }[] = situation
    ? [
        { v: situation.cases_open, label: "目前災情" },
        { v: situation.cases_pending, label: "審核中", color: PHASE_HEX.pending },
        { v: situation.cases_active, label: "處理中", color: PHASE_HEX.active },
        { v: situation.cases_community, label: "民眾可協助", color: PHASE_HEX.community },
        { v: situation.cases_high_risk, label: "高風險", color: "#d92d20" },
      ]
    : [];
  return (
    <div className="af-hud flex flex-wrap items-center gap-x-5 gap-y-1.5 px-4 py-2 sm:gap-x-6 sm:py-2.5">
      <div className="mr-1">
        <div className="text-[12px] tracking-[0.12em] text-[var(--muted)]">{county ? `${county}災情即時態勢` : "災情即時態勢"}</div>
        <div className="text-[14px] text-[var(--ink-2)]">
          {situation ? (
            <>
              更新 <span className="font-mono">{fmtClock(situation.last_update_at || situation.generated_at)}</span>
              {" · "}
              <span className={situation.trend_direction === "rising" ? "font-medium text-[#b42318]" : situation.trend_direction === "falling" ? "font-medium text-[#067647]" : ""}>{TREND_LABEL[situation.trend_direction]}</span>
            </>
          ) : (
            "載入中…"
          )}
        </div>
      </div>
      {items.map((it) => (
        <div key={it.label} className="flex items-baseline gap-1.5">
          <span className="text-[26px] font-semibold leading-none tabular-nums" style={{ color: it.color || "var(--ink)" }}>
            {it.v}
          </span>
          <span className="text-[14px] text-[var(--muted)]">{it.label}</span>
        </div>
      ))}
    </div>
  );
}

// ── layer chips ──────────────────────────────────────────────────────
const QUICK_CATEGORIES = ["trapped_people", "road_damage", "landslide", "flooding", "building_damage", "lifeline"];

export function LayerChips({ enabledLayers, visible, onToggle, statuses, official, threeD, onToggle3D, legendOpen, onToggleLegend, counts = {} }: { enabledLayers: string[]; visible: Record<string, boolean>; onToggle: (k: string) => void; statuses: LayerStatusItem[]; official: Record<string, LayerResponse | undefined>; threeD: boolean; onToggle3D: () => void; legendOpen: boolean; onToggleLegend: () => void; counts?: Record<string, number> }) {
  const [open, setOpen] = useState(false);
  const quick = QUICK_CATEGORIES.filter((k) => enabledLayers.includes(k));
  const officialKeys = enabledLayers.filter((k) => LAYERS[k]?.kind === "official");
  const officialOn = officialKeys.filter((k) => visible[k] === true);
  const alerts = officialOn.reduce((n, k) => n + (official[k]?.features.filter((f) => f.properties?.alert || f.layer === "official_alert").length || 0), 0);
  return (
    <div className="relative">
      <div className="flex flex-nowrap items-center gap-1.5 lg:flex-wrap">
        <button type="button" className={`af-hud-chip ${threeD ? "af-hud-chip-on" : ""}`} onClick={onToggle3D} title="切換 3D 地形">
          {threeD ? "3D 地形" : "2D"}
        </button>
        <button type="button" className={`af-hud-chip ${legendOpen ? "af-hud-chip-on" : ""}`} onClick={onToggleLegend} aria-pressed={legendOpen}>
          圖例
        </button>
        <span className="mx-0.5 h-5 w-px bg-[var(--line-2)]" />
        {quick.map((k) => {
          const meta = LAYERS[k];
          const on = visible[k] !== false;
          return (
            <button key={k} type="button" onClick={() => onToggle(k)} className={`af-hud-chip ${on ? "af-hud-chip-on" : ""}`} aria-pressed={on} title={`${meta?.label}：顯示／隱藏此類災情`}>
              <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: meta?.hex }} />
              {meta?.label}
              {counts[k] ? <span className="opacity-70">{counts[k]}</span> : null}
            </button>
          );
        })}
        <span className="mx-0.5 h-5 w-px bg-[var(--line-2)]" />
        <button type="button" className={`af-hud-chip ${open ? "af-hud-chip-on" : ""}`} onClick={() => setOpen((v) => !v)} aria-expanded={open} title="選擇要顯示的資料圖層">
          資料圖層 <span className="opacity-70">{officialOn.length}/{officialKeys.length}</span>
          {alerts > 0 ? <span className="ml-0.5 rounded-full bg-[#dc2626] px-1.5 text-[12px] text-white">{alerts} 警戒</span> : null}
          <span aria-hidden="true">{open ? "▴" : "▾"}</span>
        </button>
      </div>
      {open ? (
        <div className="af-hud mt-1.5 w-[320px] max-h-[min(70vh,560px)] overflow-y-auto p-3">
          <LayerPanel enabledLayers={enabledLayers} visible={visible} onToggle={onToggle} counts={counts} officialLayers={official} statuses={statuses} compact />
          <div className="mt-2 border-t pt-1.5 text-[12.5px] leading-snug text-[var(--faint)]" style={{ borderColor: "var(--line)" }}>
            圖層資料來自政府開放資料；未提供資料的來源會標示，不以假資料替代。
          </div>
        </div>
      ) : null}
    </div>
  );
}

// ── case panel ───────────────────────────────────────────────────────
export const PORTAL_PHASES: (Phase | "all")[] = ["all", "pending", "active", "community"];

export function CasePanel({ slug, cases, phase, onPhase, selectedId, onSelect, detail, onClose }: { slug: string; cases: PublicCase[]; phase: Phase | "all"; onPhase: (p: Phase | "all") => void; selectedId: string | null; onSelect: (id: string | null) => void; detail: PublicCaseDetail | null; onClose: () => void }) {
  const selected = cases.find((c) => `case:${c.id}` === selectedId) || detail?.case || null;
  return (
    <div className="af-hud flex h-full flex-col overflow-hidden">
      {selected ? (
        <SelectedCase slug={slug} c={selected} detail={detail} onClose={onClose} />
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-1.5 border-b px-3 py-2.5" style={{ borderColor: "var(--line)" }}>
            <span className="mr-1 text-[16px] font-semibold text-[var(--ink)]">最新災情</span>
            {PORTAL_PHASES.map((p) => (
              <button key={p} type="button" onClick={() => onPhase(p)} className={`af-hud-chip ${phase === p ? "af-hud-chip-on" : ""}`}>
                {p === "all" ? "全部" : p === "active" ? "處理中" : PHASE_LABEL[p]}
              </button>
            ))}
          </div>
          <ul className="flex-1 divide-y overflow-y-auto" style={{ borderColor: "var(--line)" }}>
            {cases.length === 0 ? (
              <li className="p-4 text-sm text-[var(--muted)]">目前沒有符合條件的災情。</li>
            ) : (
              cases.map((c) => (
                <li key={c.id}>
                  <button type="button" onClick={() => onSelect(`case:${c.id}`)} className="af-row-hover flex w-full items-start gap-3 px-3 py-2.5 text-left">
                    <CategoryBadge category={c.category} size={36} />
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center justify-between gap-2">
                        <span className="truncate text-[16px] font-semibold text-[var(--ink)]">{c.title}</span>
                        <span className="flex-none text-[13px] text-[var(--muted)]">{fmtAgo(c.updated_at)}</span>
                      </span>
                      <span className="mt-1 flex flex-wrap items-center gap-2 text-[13px] text-[var(--muted)]">
                        <StatusPill status={c.status} phase={c.phase} />
                        <span>{c.unique_reporter_count} 人回報</span>
                        <span className="truncate">{c.town}</span>
                      </span>
                      {c.status === "community_open" ? <span className="mt-1 block text-[13px] font-medium text-[var(--st-community)]">歡迎鄰近民眾協助處理 →</span> : null}
                    </span>
                  </button>
                </li>
              ))
            )}
          </ul>
          <div className="border-t px-3 py-2 text-right" style={{ borderColor: "var(--line)" }}>
            <Link href={`/p/${slug}/cases`} className="text-[14px] font-medium text-[var(--focus)] hover:underline">
              全部災情與處理進度 →
            </Link>
          </div>
        </>
      )}
    </div>
  );
}

function SelectedCase({ slug, c, detail, onClose }: { slug: string; c: PublicCase; detail: PublicCaseDetail | null; onClose: () => void }) {
  const timeline = detail?.timeline || [];
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-start justify-between gap-2 border-b px-3 py-2.5" style={{ borderColor: "var(--line)" }}>
        <div className="min-w-0">
          <div className="font-mono text-[13px] text-[var(--muted)]">{c.case_number}</div>
          <div className="truncate text-[17px] font-semibold text-[var(--ink)]">{c.title}</div>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-[13px]">
            <StatusPill status={c.status} phase={c.phase} />
            <SeverityTag severity={c.severity} />
            <span className="text-[var(--muted)]">{c.unique_reporter_count} 人回報</span>
          </div>
        </div>
        <button type="button" onClick={onClose} className="af-hud-chip" aria-label="回到清單">
          ← 清單
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-3 py-3">
        {detail ? (
          <>
            <ProgressSteps steps={detail.progress} />
            {c.emic_status ? <div className="mt-3 text-[14px] text-[var(--ink-2)]">EMIC 處理狀態：<b>{c.emic_status}</b></div> : null}
            {c.assigned_unit ? <div className="mt-1 text-[14px] text-[var(--ink-2)]">處理單位：{c.assigned_unit}</div> : null}
            {c.public_summary ? (
              <div className="mt-2 rounded border-l-2 bg-[var(--surface-2)] px-2.5 py-2 text-[14px] text-[var(--ink-2)]" style={{ borderColor: "var(--st-active)" }}>
                {c.public_summary}
              </div>
            ) : null}
            {detail.can_assist ? (
              <Link href={`/p/${slug}/cases/${c.id}#assist`} className="af-btn af-btn-lg mt-3 w-full text-white" style={{ background: "var(--st-community)" }}>
                我來協助處理
              </Link>
            ) : null}
            {c.status === "community_submitted" ? <div className="mt-3 rounded bg-[var(--surface-2)] px-2.5 py-2 text-[14px] text-[var(--ink-2)]">已有民眾回報處理完成，等待承辦人員確認。</div> : null}
            <div className="mt-3 text-[12px] tracking-[0.1em] text-[var(--muted)]">處理時間軸</div>
            <ol className="mt-1 space-y-1.5">
              {timeline.slice(-7).map((t, i) => (
                <li key={i} className="flex items-baseline gap-2 text-[14px]">
                  <span className="w-11 flex-none font-mono text-[var(--muted)]">{fmtClock(t.at)}</span>
                  <span className="text-[var(--ink)]">{t.label}</span>
                  {t.note && t.note !== t.label ? <span className="truncate text-[var(--muted)]">— {t.note}</span> : null}
                </li>
              ))}
            </ol>
            {detail.photos.length ? (
              <div className="mt-3 flex gap-1.5 overflow-x-auto">
                {detail.photos.slice(0, 4).map((p) => (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img key={p.id} src={api.mediaUrl(p.url)} alt={p.kind} className="h-16 w-24 flex-none rounded object-cover" />
                ))}
              </div>
            ) : null}
          </>
        ) : (
          <div className="text-sm text-[var(--muted)]">載入中…</div>
        )}
      </div>
      <div className="border-t px-3 py-2 text-right" style={{ borderColor: "var(--line)" }}>
        <Link href={`/p/${slug}/cases/${c.id}`} className="text-[14px] font-medium text-[var(--focus)] hover:underline">
          完整處理過程與照片 →
        </Link>
      </div>
    </div>
  );
}

// ── legend ───────────────────────────────────────────────────────────
export function MapLegend() {
  return (
    <div className="af-hud w-[260px] px-3 py-2.5 text-[13px] text-[var(--ink-2)]">
      <div className="mb-1.5 text-[12px] tracking-[0.1em] text-[var(--muted)]">圖例</div>
      <ul className="space-y-2">
        <li className="flex items-center gap-2">
          <svg width="18" height="28" viewBox="0 0 40 64" aria-hidden="true"><path d="M20 62V33" stroke="#1d2939" strokeWidth="2.4" strokeLinecap="round" /><circle cx="20" cy="18" r="16" fill="none" stroke="#1d4ed8" strokeWidth="3" /><circle cx="20" cy="18" r="13" fill="#ea580c" /><circle cx="31.5" cy="6.5" r="6.5" fill="#101828" /></svg>
          <span>災情案件：圖示＝災情類別，外圈＝處理狀態，黑底數字＝回報人數</span>
        </li>
        <li className="flex items-center gap-2">
          <span className="inline-block h-4 w-4 flex-none rounded-full border-2 bg-white" style={{ borderColor: "#ca8a04" }} />
          <span>已有民眾回報、尚未成案的地點</span>
        </li>
        <li className="flex items-center gap-2">
          <span className="inline-block h-2.5 w-2.5 flex-none rounded-full" style={{ background: "#667085" }} />
          <span>單筆民眾通報（位置已粗化）</span>
        </li>
        <li className="flex items-center gap-2">
          <span className="inline-block h-0 w-5 flex-none border-t-[3px]" style={{ borderColor: "#dc2626" }} />
          <span>土石流潛勢溪流：粗紅＝紅色警戒、粗黃＝黃色警戒（水保署）</span>
        </li>
        <li className="flex items-center gap-2">
          <span className="inline-block h-3.5 w-5 flex-none rounded-sm" style={{ background: "linear-gradient(90deg,#93c5fd,#22c55e,#facc15,#ef4444)" }} />
          <span>雷達回波（氣象署）</span>
        </li>
        <li className="flex flex-wrap gap-x-3 gap-y-1 pt-0.5">
          {(["pending", "active", "community"] as const).map((p) => (
            <span key={p} className="inline-flex items-center gap-1">
              <span className="h-2.5 w-2.5 rounded-full" style={{ background: PHASE_HEX[p] }} />
              {PHASE_LABEL[p]}
            </span>
          ))}
        </li>
        <li className="text-[12px] text-[var(--faint)]">已結案的災情會自地圖撤除。</li>
      </ul>
    </div>
  );
}
