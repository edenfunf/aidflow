"use client";

// Tiny bar sparkline — one hue, thin bars, no axes. Used for "reports per
// hour" wherever a number needs its recent shape beside it.

export default function Spark({ values, width = 120, height = 28, color = "var(--brand)", className = "" }: { values: number[]; width?: number; height?: number; color?: string; className?: string }) {
  const max = Math.max(1, ...values);
  const n = Math.max(1, values.length);
  const slot = width / n;
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className={className} aria-hidden="true">
      {values.map((v, i) => {
        const h = Math.max(1.5, (v / max) * (height - 3));
        return <rect key={i} x={i * slot + 0.5} y={height - h} width={Math.max(1, slot - 1.5)} height={h} rx={1} fill={color} opacity={v ? 0.85 : 0.22} />;
      })}
    </svg>
  );
}
