"use client";

// Heads-up overlays for the map-first public portal: status strip, layer
// chips, case panel (list + selected case), time scrubber.

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { ProgressSteps } from "@/components/CaseTimeline";
import LayerPanel from "@/components/LayerPanel";
import Spark from "@/components/Spark";
import { CategoryBadge } from "@/lib/categoryIcons";
import { SeverityTag, StatusPill } from "@/components/ui";
import { api } from "@/lib/api";
import { fmtAgo, fmtClock, fmtTime } from "@/lib/format";
import { LAYERS, PHASE_HEX, PHASE_LABEL, TREND_LABEL, categoryHex } from "@/lib/labels";
import type { LayerResponse, LayerStatusItem, Phase, PublicCase, PublicCaseDetail, Situation, TrendBucket } from "@/lib/types";

// ── status strip ─────────────────────────────────────────────────────
export function StatusStrip({ situation, county }: { situation: Situation | null; county: string | null }) {
  const items: { v: number; label: string; color?: string }[] = situation
    ? [
        { v: situation.cases_open, label: "目前災情" },
        { v: situation.cases_pending, label: "待派工", color: PHASE_HEX.pending },
        { v: situation.cases_active, label: "處理中", color: PHASE_HEX.active },
        { v: situation.cases_done, label: "已完成", color: PHASE_HEX.done },
        { v: situation.cases_high_risk, label: "高風險", color: "#d92d20" },
      ]
    : [];
  return (
    <div className="af-hud flex flex-wrap items-center gap-x-4 gap-y-1 px-3 py-1.5 sm:gap-x-5 sm:px-4 sm:py-2">
      {situation ? (
        <div className="hidden flex-none items-end gap-2 lg:flex" title="近 24 小時每小時通報數">
          <Spark values={situation.trend.map((b) => b.reports)} width={96} height={26} color={situation.trend_direction === "rising" ? "#b42318" : "var(--brand)"} />
        </div>
      ) : null}
      <div className="mr-1">
        <div className="text-[10px] tracking-[0.14em] text-[var(--muted)]">{county ? `${county}災情即時態勢` : "災情即時態勢"}</div>
        <div className="text-[11px] text-[var(--ink-2)]">
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
          <span className="text-[22px] font-semibold leading-none tabular-nums" style={{ color: it.color || "var(--ink)" }}>
            {it.v}
          </span>
          <span className="text-[11px] text-[var(--muted)]">{it.label}</span>
        </div>
      ))}
      {situation ? <div className="ml-auto hidden text-[11px] text-[var(--muted)] md:block">近 1 小時 {situation.reports_last_hour} 筆 · 24 小時 {situation.reports_last_24h} 筆通報 · {situation.clusters_open} 處多人回報待確認</div> : null}
    </div>
  );
}

// ── layer chips ──────────────────────────────────────────────────────
const QUICK_CATEGORIES = ["trapped_people", "road_damage", "landslide", "flooding", "building_damage", "lifeline"];

export function LayerChips({ enabledLayers, visible, onToggle, statuses, official, threeD, onToggle3D, legendOpen, onToggleLegend, vehicleCount = 0, hasLive = false, orbit = false, onToggleOrbit, counts = {} }: { enabledLayers: string[]; visible: Record<string, boolean>; onToggle: (k: string) => void; statuses: LayerStatusItem[]; official: Record<string, LayerResponse | undefined>; threeD: boolean; onToggle3D: () => void; legendOpen: boolean; onToggleLegend: () => void; vehicleCount?: number; hasLive?: boolean; orbit?: boolean; onToggleOrbit?: () => void; counts?: Record<string, number> }) {
  const [open, setOpen] = useState(false);
  const quick = QUICK_CATEGORIES.filter((k) => enabledLayers.includes(k));
  const officialKeys = enabledLayers.filter((k) => LAYERS[k]?.kind === "official");
  const officialOn = officialKeys.filter((k) => visible[k] === true);
  const alerts = officialOn.reduce((n, k) => n + (official[k]?.features.filter((f) => f.properties?.alert || f.layer === "official_alert").length || 0), 0);
  return (
    <div className="relative">
      <div className="flex flex-nowrap items-center gap-1 lg:flex-wrap">
        <button type="button" className={`af-hud-chip ${threeD ? "af-hud-chip-on" : ""}`} onClick={onToggle3D} title="切換 3D 地形">
          {threeD ? "3D 地形" : "2D"}
        </button>
        <button type="button" className={`af-hud-chip ${legendOpen ? "af-hud-chip-on" : ""}`} onClick={onToggleLegend} aria-pressed={legendOpen}>
          圖例
        </button>
        {onToggleOrbit ? (
          <button type="button" className={`af-hud-chip ${orbit ? "af-hud-chip-on" : ""}`} onClick={onToggleOrbit} aria-pressed={orbit} disabled={!threeD} title="鏡頭慢速環繞（觸碰地圖時暫停）">
            環繞
          </button>
        ) : null}
        <span className="mx-0.5 h-4 w-px bg-[var(--line-2)]" />
        <button
          type="button"
          className={`af-hud-chip ${visible.dispatch === true ? "af-hud-chip-on" : ""}`}
          onClick={() => onToggle("dispatch")}
          aria-pressed={visible.dispatch === true}
          title={hasLive ? "政府出勤情形：即時車輛位置（AVL）" : "政府出勤情形：路徑與車輛（模擬）"}
        >
          <span className="inline-block h-2 w-2 rounded-full" style={{ background: "#be123c" }} />
          政府出勤{visible.dispatch === true ? <span className="text-[var(--faint)]">{vehicleCount}</span> : null}
        </button>
        {quick.map((k) => {
          const meta = LAYERS[k];
          const on = visible[k] !== false;
          return (
            <button key={k} type="button" onClick={() => onToggle(k)} className={`af-hud-chip ${on ? "af-hud-chip-on" : ""}`} aria-pressed={on} title={`${meta?.label}：顯示／隱藏此類案件`}>
              <span className="inline-block h-2 w-2 rounded-sm" style={{ background: meta?.hex }} />
              {meta?.label}
              {counts[k] ? <span className="text-[var(--faint)]">{counts[k]}</span> : null}
            </button>
          );
        })}
        <span className="mx-0.5 h-4 w-px bg-[var(--line-2)]" />
        <button type="button" className={`af-hud-chip ${open ? "af-hud-chip-on" : ""}`} onClick={() => setOpen((v) => !v)} aria-expanded={open} title="資料圖層與官方情資">
          圖層 <span className="text-[var(--faint)]">{officialOn.length}/{officialKeys.length}</span>
          {alerts > 0 ? <span className="ml-0.5 rounded-full bg-[#dc2626] px-1.5 text-[10px] text-white">{alerts} 警戒</span> : null}
          <span aria-hidden="true">{open ? "▴" : "▾"}</span>
        </button>
      </div>
      {open ? (
        <div className="af-hud mt-1.5 w-[300px] max-h-[min(70vh,560px)] overflow-y-auto p-2.5">
          <LayerPanel enabledLayers={enabledLayers} visible={visible} onToggle={onToggle} counts={counts} officialLayers={official} statuses={statuses} compact />
          <div className="mt-2 border-t pt-1.5 text-[10.5px] leading-snug text-[var(--faint)]" style={{ borderColor: "var(--line)" }}>
            潛勢溪流、潛勢區與影響範圍在放大到鄉鎮尺度後才會完整顯示；警戒中的永遠顯示。
          </div>
        </div>
      ) : null}
    </div>
  );
}

// ── case panel ───────────────────────────────────────────────────────
export function CasePanel({ slug, cases, phase, onPhase, selectedId, onSelect, detail, onClose }: { slug: string; cases: PublicCase[]; phase: Phase | "all"; onPhase: (p: Phase | "all") => void; selectedId: string | null; onSelect: (id: string | null) => void; detail: PublicCaseDetail | null; onClose: () => void }) {
  const selected = cases.find((c) => `case:${c.id}` === selectedId) || detail?.case || null;
  return (
    <div className="af-hud flex h-full flex-col overflow-hidden">
      {selected ? (
        <SelectedCase slug={slug} c={selected} detail={detail} onClose={onClose} />
      ) : (
        <>
          <div className="flex items-center gap-1 border-b px-3 py-2" style={{ borderColor: "var(--line)" }}>
            <span className="mr-1 text-[12px] font-semibold text-[var(--ink)]">最新災情</span>
            {(["all", "pending", "active", "done"] as const).map((p) => (
              <button key={p} type="button" onClick={() => onPhase(p)} className={`af-hud-chip ${phase === p ? "af-hud-chip-on" : ""}`}>
                {p === "all" ? "進行中" : PHASE_LABEL[p]}
              </button>
            ))}
          </div>
          <ul className="flex-1 divide-y overflow-y-auto" style={{ borderColor: "var(--line)" }}>
            {cases.length === 0 ? (
              <li className="p-4 text-xs text-[var(--muted)]">目前沒有符合條件的案件。</li>
            ) : (
              cases.map((c) => (
                <li key={c.id}>
                  <button type="button" onClick={() => onSelect(`case:${c.id}`)} className="af-row-hover flex w-full items-start gap-2.5 px-3 py-2 text-left">
                    <CategoryBadge category={c.category} size={30} />
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center justify-between gap-2">
                        <span className="truncate text-[13px] font-semibold text-[var(--ink)]">{c.title}</span>
                        <span className="flex-none text-[10.5px] text-[var(--muted)]">{fmtAgo(c.updated_at)}</span>
                      </span>
                      <span className="mt-0.5 flex items-center gap-2 text-[11px] text-[var(--muted)]">
                        <StatusPill status={c.status} phase={c.phase} />
                        <span>{c.unique_reporter_count} 人回報</span>
                        <span className="truncate">{c.town}</span>
                      </span>
                    </span>
                  </button>
                </li>
              ))
            )}
          </ul>
          <div className="border-t px-3 py-1.5 text-right" style={{ borderColor: "var(--line)" }}>
            <Link href={`/p/${slug}/cases`} className="text-[11px] font-medium text-[var(--focus)] hover:underline">
              全部案件 →
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
      <div className="flex items-start justify-between gap-2 border-b px-3 py-2" style={{ borderColor: "var(--line)" }}>
        <div className="min-w-0">
          <div className="font-mono text-[10.5px] text-[var(--muted)]">{c.case_number}</div>
          <div className="truncate text-[14px] font-semibold text-[var(--ink)]">{c.title}</div>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px]">
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
            {c.assigned_unit ? <div className="mt-3 text-[11px] text-[var(--ink-2)]">處理單位：{c.assigned_unit}</div> : null}
            {c.public_summary ? (
              <div className="mt-2 rounded border-l-2 bg-[var(--surface-2)] px-2 py-1.5 text-[12px] text-[var(--ink-2)]" style={{ borderColor: "var(--st-active)" }}>
                {c.public_summary}
              </div>
            ) : null}
            <div className="mt-3 text-[10px] tracking-[0.12em] text-[var(--muted)]">處理時間軸</div>
            <ol className="mt-1 space-y-1">
              {timeline.slice(-7).map((t, i) => (
                <li key={i} className="flex items-baseline gap-2 text-[11.5px]">
                  <span className="w-10 flex-none font-mono text-[var(--muted)]">{fmtClock(t.at)}</span>
                  <span className="text-[var(--ink)]">{t.label}</span>
                  {t.note && t.note !== t.label ? <span className="truncate text-[var(--muted)]">— {t.note}</span> : null}
                </li>
              ))}
            </ol>
            {detail.photos.length ? (
              <div className="mt-3 flex gap-1.5 overflow-x-auto">
                {detail.photos.slice(0, 4).map((p) => (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img key={p.id} src={api.mediaUrl(p.url)} alt={p.kind} className="h-14 w-20 flex-none rounded object-cover" />
                ))}
              </div>
            ) : null}
          </>
        ) : (
          <div className="text-xs text-[var(--muted)]">載入中…</div>
        )}
      </div>
      <div className="border-t px-3 py-1.5 text-right" style={{ borderColor: "var(--line)" }}>
        <Link href={`/p/${slug}/cases/${c.id}`} className="text-[11px] font-medium text-[var(--focus)] hover:underline">
          完整處理過程與照片 →
        </Link>
      </div>
    </div>
  );
}


// ── legend ───────────────────────────────────────────────────────────
export function MapLegend() {
  return (
    <div className="af-hud w-[230px] px-3 py-2 text-[11px] text-[var(--ink-2)]">
      <div className="mb-1.5 text-[10px] tracking-[0.12em] text-[var(--muted)]">圖例</div>
      <ul className="space-y-1.5">
        <li className="flex items-center gap-2">
          <svg width="16" height="26" viewBox="0 0 40 64" aria-hidden="true"><path d="M20 62V33" stroke="#1d2939" strokeWidth="2.4" strokeLinecap="round" /><circle cx="20" cy="18" r="16" fill="none" stroke="#1d4ed8" strokeWidth="3" /><circle cx="20" cy="18" r="13" fill="#ea580c" /><circle cx="31.5" cy="6.5" r="6.5" fill="#101828" /></svg>
          <span>正式案件：標竿立在災點，圖示＝災情類別，外圈＝處理狀態，黑底數字＝回報人數</span>
        </li>
        <li className="flex items-center gap-2">
          <span className="inline-block h-4 w-5 flex-none rounded-full border-2" style={{ background: "rgba(234,88,12,0.22)", borderColor: "#1d4ed8" }} />
          <span>地面影響圈：範圍隨回報人數放大，邊框＝狀態</span>
        </li>
        <li className="flex items-center gap-2">
          <span className="inline-block h-4 w-4 flex-none rounded-full border-2 bg-white" style={{ borderColor: "#ca8a04" }} />
          <span>多人回報、尚未成案的災點</span>
        </li>
        <li className="flex items-center gap-2">
          <span className="inline-block h-2 w-2 flex-none rounded-full" style={{ background: "#667085" }} />
          <span>單筆民眾通報（位置已粗化）</span>
        </li>
        <li className="flex items-center gap-2">
          <span className="inline-block h-0 w-5 flex-none border-t-2 border-dashed" style={{ borderColor: "#be123c" }} />
          <span>出勤路徑（真實道路）：顏色＝權責單位（紅消防／橘工務／藍警察／青水利）</span>
        </li>
        <li className="flex items-center gap-2">
          <svg width="10" height="18" viewBox="0 0 24 44" aria-hidden="true"><rect x="4" y="2" width="16" height="40" rx="3" fill="#b91c1c" /><rect x="10.5" y="17" width="3" height="21" fill="#f8fafc" /></svg>
          <span>出勤車輛（消防車／救護車／警車／工程車）：無車隊 GPS 時以派遣時間推算並標示「模擬」</span>
        </li>
        <li className="flex items-center gap-2">
          <span className="inline-block h-0 w-5 flex-none border-t-[3px]" style={{ borderColor: "#dc2626" }} />
          <span>土石流潛勢溪流：粗紅＝紅色警戒、粗黃＝黃色警戒、細褐＝潛勢（水保署）</span>
        </li>
        <li className="flex items-center gap-2">
          <span className="inline-block h-3.5 w-5 flex-none rounded-sm" style={{ background: "linear-gradient(90deg,#93c5fd,#22c55e,#facc15,#ef4444)" }} />
          <span>雷達回波（氣象署）：自動回放最近兩小時；需設定 CWA_API_KEY</span>
        </li>
        <li className="flex items-center gap-2">
          <span className="inline-block h-4 w-4 flex-none rounded-full" style={{ background: "rgba(100,116,139,0.35)", border: "1.5px solid #64748b" }} />
          <span>人口分布：圓圈大小＝鄉鎮人口（戶政司）；水庫＝蓄水狀態色</span>
        </li>
        <li className="flex flex-wrap gap-x-2.5 gap-y-0.5 pt-0.5">
          {(["pending", "active", "done"] as const).map((p) => (
            <span key={p} className="inline-flex items-center gap-1">
              <span className="h-2 w-2 rounded-full" style={{ background: PHASE_HEX[p] }} />
              {PHASE_LABEL[p]}
            </span>
          ))}
        </li>
      </ul>
    </div>
  );
}

// ── time scrubber ────────────────────────────────────────────────────
export function TimeScrubber({ trend, cutoff, onCutoff, nowMs }: { trend: TrendBucket[]; cutoff: number | null; onCutoff: (v: number | null) => void; nowMs: number }) {
  const start = useMemo(() => (trend.length ? new Date(trend[0].start).getTime() : nowMs - 24 * 3600e3), [trend, nowMs]);
  const end = nowMs;
  const value = cutoff ?? end;
  const [playing, setPlaying] = useState(false);
  const raf = useRef<number | null>(null);
  useEffect(() => {
    if (!playing) return;
    let last = performance.now();
    let v = cutoff && cutoff < end ? cutoff : start;
    const step = (now: number) => {
      const dt = now - last;
      last = now;
      v += dt * 60 * 60; // 1 real second ≈ 1 hour
      if (v >= end) {
        onCutoff(null);
        setPlaying(false);
        return;
      }
      onCutoff(v);
      raf.current = requestAnimationFrame(step);
    };
    raf.current = requestAnimationFrame(step);
    return () => {
      if (raf.current) cancelAnimationFrame(raf.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing]);

  const max = Math.max(1, ...trend.map((b) => b.reports));
  const pct = ((value - start) / Math.max(1, end - start)) * 100;
  return (
    <div className="af-hud px-3 py-2">
      <div className="flex items-center gap-2">
        <button type="button" className="af-hud-chip !px-2" onClick={() => setPlaying((p) => !p)} aria-label={playing ? "暫停回放" : "回放 24 小時"}>
          {playing ? "❚❚" : "▶"}
        </button>
        <span className="w-24 text-[11px] text-[var(--ink-2)]">{cutoff ? `回放 ${fmtTime(new Date(value).toISOString())}` : "現在"}</span>
        <div className="relative h-9 flex-1">
          {/* sparkline */}
          <svg viewBox="0 0 100 24" preserveAspectRatio="none" className="absolute inset-x-0 bottom-3 h-5 w-full">
            {trend.map((b, i) => {
              const x = (i / Math.max(1, trend.length)) * 100;
              const h = (b.reports / max) * 22;
              const bx = (i + 0.5) / Math.max(1, trend.length);
              const active = start + bx * (end - start) <= value;
              return <rect key={b.start} x={x + 0.3} y={24 - h} width={100 / Math.max(1, trend.length) - 0.6} height={h} fill={active ? "#5b7ba6" : "#d0d5dd"} />;
            })}
          </svg>
          <input type="range" min={start} max={end} step={60e3} value={value} onChange={(e) => { setPlaying(false); const v = Number(e.target.value); onCutoff(v >= end - 60e3 ? null : v); }} className="af-range absolute inset-x-0 bottom-0 w-full" aria-label="時間回放" />
          <span className="pointer-events-none absolute bottom-0 h-1 rounded bg-[var(--brand)]" style={{ left: 0, width: `${pct}%` }} />
        </div>
        <span className="hidden text-[10.5px] text-[var(--muted)] sm:block">每格 1 小時通報數 · 立柱高度＝回報人數 · 公開位置已粗化</span>
      </div>
    </div>
  );
}
