"use client";

// The AidFlow mark: a beacon on a contour — the same stem-and-badge form the
// map uses for cases, so the logo and the data speak one language.

export function BrandMark({ size = 28, inverted = false, className = "" }: { size?: number; inverted?: boolean; className?: string }) {
  const bg = inverted ? "#ffffff" : "#0b2545";
  const fg = inverted ? "#0b2545" : "#ffffff";
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" className={className} aria-hidden="true">
      <rect width="32" height="32" rx="7" fill={bg} />
      <path d="M6 24c3-2.2 5-2.2 8 0s5 2.2 8 0 4-2 4-2" fill="none" stroke={fg} strokeOpacity="0.45" strokeWidth="1.6" strokeLinecap="round" />
      <path d="M16 21V12" stroke={fg} strokeWidth="1.8" strokeLinecap="round" />
      <circle cx="16" cy="9.5" r="4.2" fill={fg} />
      <circle cx="16" cy="21.5" r="1.4" fill={fg} />
    </svg>
  );
}

export function BrandLockup({ subtitle, inverted = false, size = 28 }: { subtitle?: string; inverted?: boolean; size?: number }) {
  return (
    <span className="inline-flex items-center gap-2.5">
      <BrandMark size={size} inverted={inverted} />
      <span className="leading-none">
        <span className={`block text-[15px] font-semibold tracking-[-0.01em] ${inverted ? "text-white" : "text-[var(--ink)]"}`}>AidFlow</span>
        {subtitle ? <span className={`mt-0.5 block text-[10px] tracking-[0.12em] ${inverted ? "text-white/60" : "text-[var(--muted)]"}`}>{subtitle}</span> : null}
      </span>
    </span>
  );
}
