"use client";

// 稽核紀錄 (業務主管／系統管理者): logins, account changes, personal-data
// views and platform / LINE configuration — the security trail, separate from
// the case event feed.

import { useCallback, useEffect, useState } from "react";
import ConsoleShell from "@/components/ConsoleShell";
import { EmptyState, ErrorBox, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { useMe } from "@/lib/auth";
import { fmtTime } from "@/lib/format";
import type { AuditEvent } from "@/lib/types";

const KINDS: { key: string; label: string }[] = [
  { key: "", label: "全部" },
  { key: "auth", label: "登入登出" },
  { key: "user", label: "帳號異動" },
  { key: "pii", label: "個資查閱" },
  { key: "line", label: "LINE 設定" },
  { key: "platform", label: "平台設定" },
];

const EVENT_LABEL: Record<string, string> = {
  "auth.login": "登入成功",
  "auth.logout": "登出",
  "auth.login_failed": "登入失敗",
  "auth.login_blocked": "鎖定中嘗試登入",
  "auth.account_locked": "帳號鎖定",
  "user.created": "建立帳號",
  "user.updated": "修改帳號",
  "user.password_changed": "變更密碼",
  "pii.viewed": "查閱通報者個資",
  "line.group_bound": "綁定 LINE 群組",
  "line.group_unbound": "解除 LINE 群組",
  "platform.created": "建立平台",
  "platform.created_by": "建立平台（操作者）",
  "platform.configured": "修改平台設定",
  "platform.published": "發布平台",
  "platform.draft": "下架平台",
  "platform.archived": "封存平台",
};

function describe(e: AuditEvent): string {
  const p = e.payload || {};
  const parts: string[] = [];
  if (p.username) parts.push(String(p.username));
  if (p.attempted_username) parts.push(`嘗試帳號 ${p.attempted_username}`);
  if (p.by) parts.push(p.by === "self" ? "本人操作" : p.by === "bootstrap" ? "系統初始化" : `操作者 ${p.by}`);
  if (p.case_number) parts.push(`案件 ${p.case_number}`);
  if (p.changes) parts.push(`變更 ${Object.keys(p.changes).join("、")}`);
  if (p.role_label) parts.push(String(p.role_label));
  if (p.reason) parts.push(`原因 ${p.reason}`);
  if (p.ip) parts.push(`IP ${p.ip}`);
  if (p.slug) parts.push(`/p/${p.slug}`);
  return parts.join(" · ");
}

export default function AuditPage() {
  const { me, can } = useMe();
  const [kind, setKind] = useState("");
  const [items, setItems] = useState<AuditEvent[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setItems(null);
    api
      .securityAudit({ kind: kind || undefined, limit: 300 })
      .then((r) => setItems(r.items))
      .catch((e) => setError((e as Error).message));
  }, [kind]);
  useEffect(() => {
    if (can("view_audit")) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [load, me]);

  if (me && !can("view_audit")) {
    return (
      <ConsoleShell title="稽核紀錄">
        <EmptyState title="您的角色無法查詢稽核紀錄" detail="稽核紀錄提供業務主管與系統管理者查詢。" />
      </ConsoleShell>
    );
  }

  return (
    <ConsoleShell title="稽核紀錄" crumbs={[{ href: "/console", label: "政府管理後台" }, { label: "稽核紀錄" }]}>
      {error ? (
        <div className="mb-3">
          <ErrorBox message={error} onRetry={load} />
        </div>
      ) : null}
      <div className="mb-3 flex flex-wrap gap-1.5">
        {KINDS.map((k) => (
          <button key={k.key} type="button" onClick={() => setKind(k.key)} className={`af-chip !px-3.5 !py-2 !text-[15px] ${kind === k.key ? "af-chip-on" : ""}`}>
            {k.label}
          </button>
        ))}
      </div>
      <div className="af-panel overflow-x-auto">
        {items === null ? (
          <Skeleton className="m-4 h-40" />
        ) : items.length === 0 ? (
          <div className="p-6 text-[16px] text-[var(--muted)]">沒有紀錄。</div>
        ) : (
          <table className="af-table min-w-[760px]">
            <thead>
              <tr>
                <th>時間</th>
                <th>事件</th>
                <th>內容</th>
              </tr>
            </thead>
            <tbody>
              {items.map((e) => (
                <tr key={e.id}>
                  <td className="whitespace-nowrap font-mono text-[14px] text-[var(--muted)]">{fmtTime(e.created_at)}</td>
                  <td className={`whitespace-nowrap text-[16px] font-medium ${e.event_type.includes("failed") || e.event_type.includes("locked") || e.event_type.includes("blocked") ? "text-[var(--sev-high)]" : "text-[var(--ink)]"}`}>{EVENT_LABEL[e.event_type] || e.event_type}</td>
                  <td className="text-[15px] text-[var(--ink-2)]">{describe(e)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      <p className="mt-3 text-[14px] text-[var(--muted)]">稽核紀錄由系統自動寫入，無法於介面刪除或修改。</p>
    </ConsoleShell>
  );
}
