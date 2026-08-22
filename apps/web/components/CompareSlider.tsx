"use client";

// Before / after photo comparison: drag the handle (or use arrow keys) to
// reveal the "after" image over the "before" one.

import { useRef, useState } from "react";

export default function CompareSlider({ before, after, beforeLabel = "處理前", afterLabel = "處理後", className = "" }: { before: string; after: string; beforeLabel?: string; afterLabel?: string; className?: string }) {
  const [pos, setPos] = useState(50);
  const boxRef = useRef<HTMLDivElement | null>(null);
  const dragging = useRef(false);

  const update = (clientX: number) => {
    const box = boxRef.current?.getBoundingClientRect();
    if (!box) return;
    setPos(Math.max(2, Math.min(98, ((clientX - box.left) / box.width) * 100)));
  };

  return (
    <div
      ref={boxRef}
      className={`af-compare relative select-none overflow-hidden rounded border ${className}`}
      style={{ borderColor: "var(--line)", aspectRatio: "4 / 3" }}
      onPointerDown={(e) => {
        dragging.current = true;
        (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
        update(e.clientX);
      }}
      onPointerMove={(e) => dragging.current && update(e.clientX)}
      onPointerUp={() => (dragging.current = false)}
      onPointerCancel={() => (dragging.current = false)}
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={before} alt={beforeLabel} className="absolute inset-0 h-full w-full object-cover" draggable={false} />
      <div className="absolute inset-0 overflow-hidden" style={{ width: `${pos}%` }}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={after} alt={afterLabel} className="absolute inset-0 h-full object-cover" style={{ width: boxRef.current?.clientWidth || "100%", maxWidth: "none" }} draggable={false} />
      </div>
      <div className="absolute inset-y-0" style={{ left: `calc(${pos}% - 1px)`, width: 2, background: "#fff", boxShadow: "0 0 0 1px rgba(16,24,40,0.35)" }} />
      <button
        type="button"
        className="absolute top-1/2 grid h-8 w-8 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full border bg-white text-[var(--ink)] shadow"
        style={{ left: `${pos}%`, borderColor: "var(--line-2)" }}
        aria-label="拖曳比較處理前後"
        role="slider"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(pos)}
        onKeyDown={(e) => {
          if (e.key === "ArrowLeft") setPos((p) => Math.max(2, p - 4));
          if (e.key === "ArrowRight") setPos((p) => Math.min(98, p + 4));
        }}
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M9 6 3 12l6 6M15 6l6 6-6 6" />
        </svg>
      </button>
      <span className="absolute left-2 top-2 rounded bg-black/55 px-1.5 py-0.5 text-[10.5px] font-medium text-white">{afterLabel}</span>
      <span className="absolute right-2 top-2 rounded bg-black/55 px-1.5 py-0.5 text-[10.5px] font-medium text-white">{beforeLabel}</span>
    </div>
  );
}
