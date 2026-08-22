"use client";

import { PHASE_HEX, PHASE_OF } from "@/lib/labels";
import { fmtClock, fmtTime } from "@/lib/format";
import { EventIcon } from "@/lib/categoryIcons";
import type { CaseStatus, ProgressStep, PublicTimelineItem } from "@/lib/types";

function dotColor(item: { event_type: string; to_status: string | null }): string {
  if (item.to_status) return PHASE_HEX[PHASE_OF[item.to_status as CaseStatus]] || "#667085";
  if (item.event_type === "report.received") return "#98a2b3";
  if (item.event_type === "public_update") return "#1d4ed8";
  return "#475467";
}

export function ProgressSteps({ steps }: { steps: ProgressStep[] }) {
  return (
    <ol className="flex w-full items-start">
      {steps.map((s, i) => {
        const color = s.reached ? PHASE_HEX[PHASE_OF[s.key]] : "var(--line-2)";
        return (
          <li key={s.key} className="relative flex-1">
            {i < steps.length - 1 ? (
              <span className="absolute left-1/2 top-2 h-0.5 w-full" style={{ background: steps[i + 1].reached ? PHASE_HEX[PHASE_OF[steps[i + 1].key]] : "var(--line)" }} />
            ) : null}
            <div className="relative flex flex-col items-center text-center">
              <span
                className="z-10 grid h-4 w-4 place-items-center rounded-full border-2 bg-white"
                style={{ borderColor: color, background: s.reached ? color : "#fff", boxShadow: s.current ? `0 0 0 3px ${color}33` : undefined }}
              />
              <span className={`mt-1.5 text-[10.5px] leading-tight ${s.reached ? "font-medium text-[var(--ink)]" : "text-[var(--faint)]"}`}>{s.label}</span>
              {s.at ? <span className="text-[10px] tabular-nums text-[var(--faint)]">{fmtClock(s.at)}</span> : null}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

export default function CaseTimeline({ items, dense = false }: { items: PublicTimelineItem[]; dense?: boolean }) {
  if (!items.length) return <div className="text-xs text-[var(--muted)]">尚無處理紀錄。</div>;
  let lastDay = "";
  return (
    <ol className="relative ml-2.5 border-l border-[var(--line)]">
      {items.map((it, i) => {
        const day = new Date(it.at).toLocaleDateString("zh-TW", { month: "2-digit", day: "2-digit" });
        const showDay = day !== lastDay;
        lastDay = day;
        return (
          <li key={i} className={`relative pl-6 ${dense ? "pb-2.5" : "pb-4"} last:pb-0`}>
            <span className="af-tl-icon" style={{ color: dotColor(it), borderColor: dotColor(it) }}>
              <EventIcon type={it.event_type} size={11} />
            </span>
            {showDay ? <div className="mb-0.5 text-[10px] font-medium tracking-wide text-[var(--faint)]">{day}</div> : null}
            <div className="flex items-baseline gap-2">
              <span className="font-mono text-[11px] tabular-nums text-[var(--muted)]">{fmtClock(it.at)}</span>
              <span className={`text-sm ${it.to_status ? "font-semibold" : "font-medium"} text-[var(--ink)]`}>{it.label}</span>
            </div>
            {it.note && it.note !== it.label ? <p className="mt-0.5 text-xs leading-relaxed text-[var(--ink-2)]">{it.note}</p> : null}
          </li>
        );
      })}
    </ol>
  );
}

export function CompactTimeline({ items, limit = 4 }: { items: PublicTimelineItem[]; limit?: number }) {
  const shown = items.slice(-limit);
  return (
    <ul className="space-y-0.5 text-[11px]">
      {shown.map((it, i) => (
        <li key={i} className="flex gap-2 text-[var(--ink-2)]">
          <span className="font-mono tabular-nums text-[var(--muted)]">{fmtTime(it.at)}</span>
          <span>{it.label}</span>
        </li>
      ))}
    </ul>
  );
}
