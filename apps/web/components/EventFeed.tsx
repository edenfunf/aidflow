"use client";

// Live event stream for the console: the transactional outbox read back as a
// feed — new reports, cases awaiting review, EMIC updates, community
// completions — with new rows sliding in. Polls; nothing is invented.

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { EventIcon } from "@/lib/categoryIcons";
import { api } from "@/lib/api";
import { fmtAgo, fmtClock } from "@/lib/format";
import { PHASE_HEX, PHASE_OF, STATUS_LABEL } from "@/lib/labels";
import type { AuditEvent, CaseStatus } from "@/lib/types";

const FEED_LABEL: Record<string, string> = {
  "report.received": "民眾回報",
  "report.created": "民眾通報",
  "cluster.opened": "新通報地點（未達門檻）",
  "case.threshold_reached": "達到多人回報門檻",
  "case.created": "成案・待審核",
  "case.status_changed": "狀態更新",
  "case.public_update": "處理進度",
  "case.internal_note": "內部備註",
  "case.emic_updated": "EMIC 資訊更新",
  "case.emic_submitted": "已上報 EMIC",
  "case.emic_submit_failed": "EMIC 自動上報失敗",
  "report.rejected": "回報排除",
  "photo.uploaded": "照片上傳",
  "platform.created": "平台建立",
  "platform.created_by": "平台建立",
  "platform.configured": "平台設定",
  "line.group_bound": "LINE 群組已綁定",
  "line.group_unbound": "LINE 群組解除綁定",
};

function describe(e: AuditEvent): { label: string; detail: string; color: string; icon: string; caseId?: string } {
  const p = e.payload || {};
  const base = e.event_type.replace(/^case\./, "");
  const icon = EVENT_ICONS_MAP[e.event_type] || base;
  const to = (p.to_status || p.status) as string | undefined;
  const caseNo = p.case_number ? `${p.case_number} ` : "";
  let color = "#475467";
  let detail = "";
  if (to && STATUS_LABEL[to as CaseStatus]) {
    detail = `${caseNo}${p.title || ""} → ${STATUS_LABEL[to as CaseStatus]}`;
    color = PHASE_HEX[PHASE_OF[to as CaseStatus]] || color;
  } else if (e.event_type === "case.created" || e.event_type === "case.threshold_reached") {
    detail = `${caseNo}${p.title || ""}`;
    color = "#b54708";
  } else if (e.event_type === "report.received") {
    detail = `${p.category_label || p.category || ""}${p.town ? ` · ${p.town}` : ""}`;
    color = "#98a2b3";
  } else {
    detail = String(p.note || p.title || p.unit_name || p.name || "");
  }
  return { label: FEED_LABEL[e.event_type] || e.event_type, detail, color, icon, caseId: p.case_id as string | undefined };
}

const EVENT_ICONS_MAP: Record<string, string> = {
  "case.threshold_reached": "threshold_reached",
  "case.status_changed": "status_changed",
  "case.assignment_changed": "assignment_changed",
  "case.public_update": "public_update",
  "case.emic_updated": "emic_updated",
  "case.emic_submitted": "emic_submitted",
  "case.emic_submit_failed": "emic_submit_failed",
  "cluster.opened": "threshold_reached",
  "report.created": "report.received",
};

export default function EventFeed({ platformId, limit = 40, pollMs = 8000, className = "" }: { platformId: string; limit?: number; pollMs?: number; className?: string }) {
  const [items, setItems] = useState<AuditEvent[] | null>(null);
  const [fresh, setFresh] = useState<Set<string>>(new Set());
  const known = useRef<Set<string>>(new Set());

  useEffect(() => {
    let alive = true;
    const load = () =>
      api
        .audit(platformId, limit)
        .then((r) => {
          if (!alive) return;
          const incoming = r.items;
          const newIds = incoming.filter((e) => !known.current.has(e.id)).map((e) => e.id);
          const first = known.current.size === 0;
          incoming.forEach((e) => known.current.add(e.id));
          setItems(incoming);
          if (!first && newIds.length) {
            setFresh(new Set(newIds));
            window.setTimeout(() => setFresh(new Set()), 2500);
          }
        })
        .catch(() => undefined);
    load();
    const id = window.setInterval(load, pollMs);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, [platformId, limit, pollMs]);

  if (items === null) return <div className={`af-skeleton h-40 ${className}`} />;
  if (!items.length) return <div className={`text-xs text-[var(--muted)] ${className}`}>尚無事件。</div>;
  return (
    <ol className={`af-feed ${className}`}>
      {items.map((e) => {
        const d = describe(e);
        const row = (
          <>
            <span className="af-feed-icon" style={{ color: d.color, borderColor: d.color }}>
              <EventIcon type={d.icon} size={12} />
            </span>
            <span className="min-w-0 flex-1">
              <span className="flex items-baseline justify-between gap-2">
                <span className="truncate text-[14px] font-medium text-[var(--ink)]">{d.label}</span>
                <span className="flex-none font-mono text-[12.5px] tabular-nums text-[var(--faint)]" title={fmtAgo(e.created_at)}>
                  {fmtClock(e.created_at)}
                </span>
              </span>
              {d.detail ? <span className="block truncate text-[13px] text-[var(--ink-2)]">{d.detail}</span> : null}
            </span>
          </>
        );
        return (
          <li key={e.id} className={`af-feed-row ${fresh.has(e.id) ? "af-feed-new" : ""}`}>
            {d.caseId ? (
              <Link href={`/console/platforms/${platformId}/cases/${d.caseId}`} className="flex min-w-0 flex-1 items-start gap-2 hover:opacity-80">
                {row}
              </Link>
            ) : (
              <span className="flex min-w-0 flex-1 items-start gap-2">{row}</span>
            )}
          </li>
        );
      })}
    </ol>
  );
}
