"use client";

// 24-hour trend: reports per hour as columns (one hue, thin, 4px rounded
// data-ends, 2px surface gap) with resolved cases as a 2px line on the same
// axis. Hover shows a tooltip; the legend names both series.

import { useMemo, useState } from "react";
import type { TrendBucket } from "@/lib/types";

export default function TrendChart({ trend, height = 120 }: { trend: TrendBucket[]; height?: number }) {
  const [hover, setHover] = useState<number | null>(null);
  const W = 600;
  const H = height;
  const padL = 28;
  const padB = 18;
  const padT = 8;
  const innerW = W - padL - 6;
  const innerH = H - padB - padT;
  const max = useMemo(() => Math.max(3, ...trend.map((b) => Math.max(b.reports, b.cases_resolved, b.cases_created))), [trend]);
  const n = trend.length || 1;
  const slot = innerW / n;
  const barW = Math.min(16, Math.max(4, slot - 2));
  const y = (v: number) => padT + innerH - (v / max) * innerH;
  const ticks = [0, Math.ceil(max / 2), max];

  const line = trend
    .map((b, i) => `${i === 0 ? "M" : "L"}${padL + i * slot + slot / 2},${y(b.cases_resolved)}`)
    .join(" ");

  const hourLabel = (iso: string) => {
    try {
      return new Date(iso).toLocaleTimeString("zh-TW", { hour: "2-digit", hour12: false }).replace(/:.*$/, "");
    } catch {
      return "";
    }
  };

  if (!trend.length) return <div className="text-xs text-[var(--muted)]">尚無趨勢資料</div>;

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label="近 24 小時通報與完成案件趨勢">
        {ticks.map((t) => (
          <g key={t}>
            <line x1={padL} x2={W - 4} y1={y(t)} y2={y(t)} stroke="var(--line)" strokeWidth={1} />
            <text x={padL - 6} y={y(t) + 3} fontSize={9} textAnchor="end" fill="var(--muted)">
              {t}
            </text>
          </g>
        ))}
        {trend.map((b, i) => {
          const x = padL + i * slot + (slot - barW) / 2;
          const h = Math.max(0, y(0) - y(b.reports));
          const isHover = hover === i;
          return (
            <g key={b.start} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
              <rect x={padL + i * slot} y={padT} width={slot} height={innerH} fill="transparent" />
              {h > 0 ? (
                <path
                  d={`M${x},${y(0)} V${y(b.reports) + 4} a4,4 0 0 1 4,-4 h${barW - 8} a4,4 0 0 1 4,4 V${y(0)} Z`}
                  fill={isHover ? "#13315c" : "#5b7ba6"}
                />
              ) : null}
              {i % 4 === 0 ? (
                <text x={padL + i * slot + slot / 2} y={H - 4} fontSize={9} textAnchor="middle" fill="var(--muted)">
                  {hourLabel(b.start)}
                </text>
              ) : null}
            </g>
          );
        })}
        <path d={line} fill="none" stroke="#067647" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        {hover !== null ? (
          <circle cx={padL + hover * slot + slot / 2} cy={y(trend[hover].cases_resolved)} r={4} fill="#067647" stroke="var(--surface)" strokeWidth={2} />
        ) : null}
      </svg>
      {hover !== null ? (
        <div className="pointer-events-none absolute -top-1 left-1/2 -translate-x-1/2 rounded border bg-white px-2 py-1 text-[11px] shadow-sm" style={{ borderColor: "var(--line)" }}>
          <span className="text-[var(--muted)]">{hourLabel(trend[hover].start)}:00　</span>
          通報 {trend[hover].reports} · 成案 {trend[hover].cases_created} · 完成 {trend[hover].cases_resolved}
        </div>
      ) : null}
      <div className="mt-1 flex items-center gap-4 text-[11px] text-[var(--muted)]">
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: "#5b7ba6" }} /> 每小時通報
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-3" style={{ background: "#067647" }} /> 處理完成案件
        </span>
      </div>
    </div>
  );
}

export function BreakdownBars({ items, total, max = 6 }: { items: { key: string; label: string; count: number }[]; total?: number; max?: number }) {
  const top = items.slice(0, max);
  const denom = Math.max(1, ...top.map((i) => i.count));
  if (!top.length) return <div className="text-xs text-[var(--muted)]">尚無資料</div>;
  return (
    <ul className="space-y-1.5">
      {top.map((i) => (
        <li key={i.key} className="grid grid-cols-[5.5rem_1fr_2.5rem] items-center gap-2 text-xs">
          <span className="truncate text-[var(--ink-2)]">{i.label}</span>
          <span className="h-2 overflow-hidden rounded-sm bg-[var(--surface-3)]">
            <span className="block h-full rounded-sm" style={{ width: `${(i.count / denom) * 100}%`, background: "#5b7ba6" }} />
          </span>
          <span className="text-right tabular-nums text-[var(--ink)]">{i.count}</span>
        </li>
      ))}
      {total !== undefined && items.length > max ? (
        <li className="text-[11px] text-[var(--faint)]">其他 {items.slice(max).reduce((a, b) => a + b.count, 0)} 件</li>
      ) : null}
    </ul>
  );
}
