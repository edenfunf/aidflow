"use client";

// Small presentational primitives shared by portal and console.

import Link from "next/link";
import CountUp from "@/components/CountUp";
import Spark from "@/components/Spark";
import { PHASE_COLOR, PHASE_LABEL, PHASE_OF, SEVERITY_COLOR, SEVERITY_LABEL, STATUS_LABEL } from "@/lib/labels";
import type { CaseStatus, Phase, Severity } from "@/lib/types";

export function StatusPill({ status, phase }: { status: CaseStatus | string; phase?: Phase }) {
  const ph = phase || PHASE_OF[status as CaseStatus] || "pending";
  const color = PHASE_COLOR[ph];
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap rounded px-1.5 py-0.5 text-[11px] font-medium" style={{ color, background: "var(--surface-2)", border: "1px solid var(--line)" }}>
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: color }} />
      {STATUS_LABEL[status as CaseStatus] || status}
    </span>
  );
}

export function PhasePill({ phase }: { phase: Phase }) {
  const color = PHASE_COLOR[phase];
  return (
    <span className="inline-flex items-center gap-1.5 rounded px-1.5 py-0.5 text-[11px] font-medium" style={{ color, background: "var(--surface-2)", border: "1px solid var(--line)" }}>
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: color }} />
      {PHASE_LABEL[phase]}
    </span>
  );
}

export function SeverityTag({ severity, withLabel = true }: { severity: Severity; withLabel?: boolean }) {
  return (
    <span className="inline-flex items-center gap-1 whitespace-nowrap text-[11px] font-medium text-[var(--ink-2)]">
      <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: SEVERITY_COLOR[severity] }} />
      {withLabel ? `嚴重度 ${SEVERITY_LABEL[severity]}` : SEVERITY_LABEL[severity]}
    </span>
  );
}

export function Kpi({ value, label, tone, hint, small, spark }: { value: number | string; label: string; tone?: Phase | "risk" | "neutral"; hint?: string; small?: boolean; spark?: number[] }) {
  const accent =
    tone === "risk" ? "var(--sev-high)" : tone && tone !== "neutral" ? PHASE_COLOR[tone as Phase] : undefined;
  return (
    <div className="af-kpi af-rise relative overflow-hidden">
      {accent ? <span className="absolute inset-y-0 left-0 w-[3px]" style={{ background: accent }} /> : null}
      <div className="flex items-end justify-between gap-2">
        <div className={`${small ? "text-xl" : "af-kpi-value"} font-semibold tabular-nums leading-none`} style={{ color: accent || "var(--ink)" }}>
          {typeof value === "number" ? <CountUp value={value} /> : value}
        </div>
        {spark && spark.length ? <Spark values={spark} width={72} height={22} color={accent || "var(--brand)"} className="flex-none opacity-80" /> : null}
      </div>
      <div className="af-kpi-label">{label}</div>
      {hint ? <div className="mt-0.5 text-[11px] text-[var(--faint)]">{hint}</div> : null}
    </div>
  );
}

export function EmptyState({ title, detail, action }: { title: string; detail?: string; action?: React.ReactNode }) {
  return (
    <div className="af-subtle flex flex-col items-center justify-center gap-1.5 px-4 py-10 text-center">
      <svg width="72" height="44" viewBox="0 0 72 44" aria-hidden="true" className="mb-1 text-[var(--line-2)]">
        <path d="M4 38c8-6 14-6 22 0s14 6 22 0 14-6 20-2" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        <path d="M36 30V16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        <circle cx="36" cy="11" r="6" fill="none" stroke="currentColor" strokeWidth="2" />
        <circle cx="36" cy="31" r="2" fill="currentColor" />
      </svg>
      <div className="text-sm font-medium text-[var(--ink-2)]">{title}</div>
      {detail ? <div className="max-w-sm text-xs text-[var(--muted)]">{detail}</div> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex items-start justify-between gap-3 rounded border px-3 py-2 text-sm" style={{ borderColor: "#f4b8b3", background: "#fef3f2", color: "#912018" }}>
      <span>{message}</span>
      {onRetry ? (
        <button type="button" className="af-btn af-btn-secondary !py-0.5 text-xs" onClick={onRetry}>
          重試
        </button>
      ) : null}
    </div>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`af-skeleton ${className}`} aria-hidden />;
}

export function SectionHeader({ title, eyebrow, right }: { title: string; eyebrow?: string; right?: React.ReactNode }) {
  return (
    <div className="mb-2 flex items-end justify-between gap-2">
      <div>
        {eyebrow ? <div className="af-eyebrow">{eyebrow}</div> : null}
        <h2 className="af-h2">{title}</h2>
      </div>
      {right}
    </div>
  );
}

export function BackLink({ href, label }: { href: string; label: string }) {
  return (
    <Link href={href} className="inline-flex items-center gap-1 text-xs text-[var(--muted)] hover:text-[var(--ink)]">
      ← {label}
    </Link>
  );
}
