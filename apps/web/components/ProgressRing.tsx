"use client";

// The case-formation rule made visible: a ring that fills one segment per
// distinct reporter until the platform's threshold is reached.

import { useEffect, useState } from "react";

export default function ProgressRing({ value, total, size = 132, color = "var(--st-pending)", doneColor = "var(--st-active)", label }: { value: number; total: number; size?: number; color?: string; doneColor?: string; label?: string }) {
  const [anim, setAnim] = useState(0);
  useEffect(() => {
    const id = window.setTimeout(() => setAnim(value), 60);
    return () => window.clearTimeout(id);
  }, [value]);
  const r = size / 2 - 9;
  const c = 2 * Math.PI * r;
  const segs = Math.max(1, total);
  const gap = segs > 1 ? 10 : 0;
  const segLen = c / segs - gap;
  const reached = value >= total;
  const stroke = reached ? doneColor : color;
  return (
    <div className="relative inline-grid place-items-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90">
        {Array.from({ length: segs }, (_, i) => (
          <circle
            key={i}
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke={i < anim ? stroke : "var(--line)"}
            strokeWidth={10}
            strokeLinecap={segs > 1 ? "butt" : "round"}
            strokeDasharray={`${segLen} ${c - segLen}`}
            strokeDashoffset={-(i * (segLen + gap))}
            style={{ transition: "stroke 0.5s ease" }}
          />
        ))}
      </svg>
      <div className="absolute inset-0 grid place-items-center text-center">
        <div>
          <div className="text-2xl font-semibold leading-none tabular-nums" style={{ color: stroke }}>
            {Math.min(value, total)}
            <span className="text-sm text-[var(--muted)]"> / {total}</span>
          </div>
          {label ? <div className="mt-1 text-[10.5px] text-[var(--muted)]">{label}</div> : null}
        </div>
      </div>
    </div>
  );
}
