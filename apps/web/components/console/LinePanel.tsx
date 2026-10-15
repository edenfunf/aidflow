"use client";

// LINE 群組通知 (G-09): status for everyone, the step-by-step binding guide and
// controls for the system administrator.

import { useCallback, useEffect, useState } from "react";
import { ErrorBox } from "@/components/ui";
import { API_BASE, api } from "@/lib/api";
import { fmtTime } from "@/lib/format";
import { NOTIFY_KIND_LABEL, NOTIFY_STATUS_LABEL } from "@/lib/labels";
import type { LineStatus, NotificationLogItem } from "@/lib/types";

export function LineStatusBanner({ status, onOpen }: { status: LineStatus | null; onOpen: () => void }) {
  if (!status) return null;
  if (status.bound) {
    return (
      <button type="button" onClick={onOpen} className="flex w-full items-center justify-between gap-3 rounded-md border px-4 py-2.5 text-left" style={{ borderColor: "#abefc6", background: "#ecfdf3" }}>
        <span className="flex items-center gap-2.5 text-[16px] font-medium text-[#067647]">
          <LineGlyph />
          LINE 群組通知已啟用：新通報會即時推播到縣府群組
          {!status.token_configured ? <span className="text-[14px] font-normal text-[#b54708]">（尚未設定 LINE 金鑰，目前為模擬）</span> : null}
        </span>
        <span className="text-[14px] text-[#067647]">設定 →</span>
      </button>
    );
  }
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border-2 px-4 py-3" style={{ borderColor: "#fedf89", background: "#fffaeb" }}>
      <div className="flex items-center gap-3">
        <LineGlyph size={34} />
        <div>
          <div className="text-[17px] font-semibold text-[#93370d]">尚未綁定 LINE 群組</div>
          <div className="text-[15px] text-[#b54708]">有民眾通報時，系統無法即時通知承辦人員。完成綁定只要 3 步驟。</div>
        </div>
      </div>
      <button type="button" onClick={onOpen} className="af-btn af-btn-lg font-bold text-white" style={{ background: "#06c755" }}>
        設定 LINE 群組通知
      </button>
    </div>
  );
}

function LineGlyph({ size = 26 }: { size?: number }) {
  return (
    <span className="grid flex-none place-items-center rounded-lg text-white" style={{ width: size, height: size, background: "#06c755" }} aria-hidden="true">
      <svg width={size * 0.62} height={size * 0.62} viewBox="0 0 24 24" fill="currentColor">
        <path d="M12 3C6.5 3 2 6.6 2 11c0 3.9 3.5 7.2 8.3 7.9.3.1.8.2.9.5.1.3.1.7 0 1l-.1.9c0 .3-.2 1 .9.5s5.9-3.5 8-6C21.4 14.3 22 12.7 22 11c0-4.4-4.5-8-10-8z" />
      </svg>
    </span>
  );
}

export default function LinePanel({ platformId, canManage, onChange }: { platformId: string; canManage: boolean; onChange?: (s: LineStatus) => void }) {
  const [status, setStatus] = useState<LineStatus | null>(null);
  const [logs, setLogs] = useState<NotificationLogItem[]>([]);
  const [groupId, setGroupId] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .lineStatus(platformId)
      .then((s) => {
        setStatus(s);
        onChange?.(s);
      })
      .catch((e) => setError((e as Error).message));
    api.notifications(platformId, 30).then((r) => setLogs(r.items)).catch(() => undefined);
  }, [platformId, onChange]);
  useEffect(() => {
    load();
  }, [load]);

  const run = async (key: string, fn: () => Promise<unknown>, done?: string) => {
    setBusy(key);
    setError(null);
    setNote(null);
    try {
      await fn();
      if (done) setNote(done);
      load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-4">
      {error ? <ErrorBox message={error} /> : null}
      {note ? <div className="rounded bg-[var(--surface-2)] px-3 py-2 text-[15px] text-[var(--ink-2)]">{note}</div> : null}
      {status ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <div>
            <div className="text-[16px] font-semibold text-[var(--ink)]">目前狀態</div>
            <dl className="mt-2 grid grid-cols-[7rem_1fr] gap-y-1.5 text-[15px]">
              <dt className="text-[var(--muted)]">群組綁定</dt>
              <dd className={status.bound ? "font-semibold text-[var(--st-done)]" : "font-semibold text-[#b54708]"}>{status.bound ? `已綁定（${status.group_id_masked}）` : "尚未綁定"}</dd>
              {status.bound_at ? (
                <>
                  <dt className="text-[var(--muted)]">綁定時間</dt>
                  <dd>{fmtTime(status.bound_at)}</dd>
                </>
              ) : null}
              <dt className="text-[var(--muted)]">LINE 金鑰</dt>
              <dd>{status.token_configured ? "已設定（實際推播）" : "未設定（通知僅記錄為模擬）"}</dd>
              <dt className="text-[var(--muted)]">Webhook</dt>
              <dd>{status.webhook_enabled ? "已啟用" : "未設定 LINE_CHANNEL_SECRET"}</dd>
            </dl>
            {canManage ? (
              <div className="mt-3 flex flex-wrap gap-2">
                <button type="button" className="af-btn af-btn-secondary" disabled={!status.bound || busy === "test"} onClick={() => run("test", () => api.lineTest(platformId), "已發送測試訊息（未設定金鑰時僅記錄為模擬）。")}>
                  發送測試訊息
                </button>
                {status.bound ? (
                  <button type="button" className="af-btn af-btn-danger" disabled={busy === "unbind"} onClick={() => window.confirm("解除 LINE 群組綁定？之後新通報將不會推播。") && run("unbind", () => api.lineUnbind(platformId), "已解除綁定。")}>
                    解除綁定
                  </button>
                ) : null}
              </div>
            ) : (
              <p className="mt-3 text-[14px] text-[var(--muted)]">LINE 群組的綁定與變更由系統管理者設定。</p>
            )}
          </div>

          {canManage ? (
            <div>
              <div className="text-[16px] font-semibold text-[var(--ink)]">綁定步驟</div>
              <ol className="mt-2 space-y-3 text-[15px] text-[var(--ink-2)]">
                <li className="flex gap-3">
                  <span className="grid h-7 w-7 flex-none place-items-center rounded-full text-[14px] font-bold text-white" style={{ background: "#06c755" }}>1</span>
                  <span>把縣府的 LINE 官方帳號（通報機器人）<b>邀請進承辦人員的 LINE 群組</b>。</span>
                </li>
                <li className="flex gap-3">
                  <span className="grid h-7 w-7 flex-none place-items-center rounded-full text-[14px] font-bold text-white" style={{ background: "#06c755" }}>2</span>
                  <span>
                    在群組中輸入：
                    <span className="mt-1.5 flex items-center gap-2">
                      <code className="rounded-md border bg-white px-3 py-1.5 font-mono text-[22px] font-bold tracking-[0.15em] text-[var(--ink)]" style={{ borderColor: "var(--line-2)" }}>
                        綁定 {status.bind_code}
                      </code>
                      <button type="button" className="af-btn af-btn-ghost" onClick={() => navigator.clipboard?.writeText(`綁定 ${status.bind_code}`)}>
                        複製
                      </button>
                    </span>
                  </span>
                </li>
                <li className="flex gap-3">
                  <span className="grid h-7 w-7 flex-none place-items-center rounded-full text-[14px] font-bold text-white" style={{ background: "#06c755" }}>3</span>
                  <span>機器人回覆「已綁定」即完成，重新整理此頁確認狀態。</span>
                </li>
              </ol>
              <div className="mt-3 flex flex-wrap gap-2 text-[14px]">
                <button type="button" className="text-[var(--focus)] hover:underline" disabled={busy === "code"} onClick={() => run("code", () => api.lineRegenerateCode(platformId), "已產生新的綁定代碼。")}>
                  重新產生代碼
                </button>
                <span className="text-[var(--faint)]">·</span>
                <span className="text-[var(--muted)]">
                  Webhook 網址：<code className="text-[13px]">{API_BASE}{status.webhook_path}</code>
                </span>
              </div>
              <details className="mt-3">
                <summary className="cursor-pointer text-[14px] text-[var(--muted)]">已知群組 ID？手動綁定</summary>
                <div className="mt-2 flex gap-2">
                  <input className="af-input font-mono" placeholder="C 開頭的 33 碼群組 ID" value={groupId} onChange={(e) => setGroupId(e.target.value)} />
                  <button type="button" className="af-btn af-btn-primary" disabled={!groupId.trim() || busy === "bind"} onClick={() => run("bind", () => api.lineBind(platformId, groupId.trim()), "已綁定群組。")}>
                    綁定
                  </button>
                </div>
              </details>
            </div>
          ) : null}
        </div>
      ) : null}

      <div>
        <div className="text-[16px] font-semibold text-[var(--ink)]">最近通知紀錄</div>
        {logs.length === 0 ? (
          <div className="mt-2 text-[15px] text-[var(--muted)]">尚無通知紀錄。</div>
        ) : (
          <div className="mt-2 overflow-x-auto">
            <table className="af-table">
              <thead>
                <tr>
                  <th>時間</th>
                  <th>管道</th>
                  <th>類型</th>
                  <th>對象</th>
                  <th>結果</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((n) => (
                  <tr key={n.id}>
                    <td className="whitespace-nowrap font-mono text-[13px] text-[var(--muted)]">{fmtTime(n.created_at)}</td>
                    <td>{n.channel === "line" ? "LINE 群組" : "Email"}</td>
                    <td>{NOTIFY_KIND_LABEL[n.kind] || n.kind}</td>
                    <td className="text-[14px] text-[var(--muted)]">{n.recipient || "—"}</td>
                    <td>
                      <span className={n.status === "sent" ? "text-[var(--st-done)]" : n.status === "failed" ? "text-[var(--sev-high)]" : "text-[var(--muted)]"}>{NOTIFY_STATUS_LABEL[n.status] || n.status}</span>
                      {n.detail ? <div className="text-[13px] text-[var(--faint)]">{n.detail}</div> : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
