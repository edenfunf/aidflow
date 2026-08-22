"use client";

// A number that counts to its value when it first appears or changes.
// Respects prefers-reduced-motion (renders the final value directly).

import { useEffect, useRef, useState } from "react";

export default function CountUp({ value, duration = 900, className = "" }: { value: number; duration?: number; className?: string }) {
  const [shown, setShown] = useState(0);
  const fromRef = useRef(0);
  const raf = useRef<number | null>(null);

  useEffect(() => {
    const reduced = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduced || !Number.isFinite(value)) {
      setShown(value);
      fromRef.current = value;
      return;
    }
    const from = fromRef.current;
    const t0 = performance.now();
    const step = (now: number) => {
      const k = Math.min(1, (now - t0) / duration);
      const e = 1 - Math.pow(1 - k, 3);
      setShown(Math.round(from + (value - from) * e));
      if (k < 1) raf.current = requestAnimationFrame(step);
      else fromRef.current = value;
    };
    if (raf.current) cancelAnimationFrame(raf.current);
    raf.current = requestAnimationFrame(step);
    return () => {
      if (raf.current) cancelAnimationFrame(raf.current);
    };
  }, [value, duration]);

  return <span className={`tabular-nums ${className}`}>{shown}</span>;
}
