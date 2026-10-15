"use client";

// 帳號管理 (系統管理者): create staff accounts, assign roles, deactivate,
// reset passwords. Every change is written to the audit log by the API.

import { useCallback, useEffect, useState } from "react";
import ConsoleShell from "@/components/ConsoleShell";
import { EmptyState, ErrorBox, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { useMe } from "@/lib/auth";
import { fmtTime } from "@/lib/format";
import { STAFF_ROLE_LABEL } from "@/lib/labels";
import type { Role, UserItem } from "@/lib/types";

const ROLE_HELP: Record<Role, string> = {
  officer: "審核分流、上報 EMIC、案件處理紀錄、民間處理確認；可檢視通報者聯絡資料",
  supervisor: "檢視總覽、案件進度與稽核紀錄；不直接異動案件",
  admin: "帳號與角色、災害平台建立、圖層與 LINE 設定；不可檢視通報者個資",
};

export default function UsersPage() {
  const { me, can } = useMe();
  const [users, setUsers] = useState<UserItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [form, setForm] = useState<{ username: string; display_name: string; role: Role; password: string }>({ username: "", display_name: "", role: "officer", password: "" });

  const load = useCallback(() => {
    api.listUsers().then(setUsers).catch((e) => setError((e as Error).message));
  }, []);
  useEffect(() => {
    if (can("manage_users")) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [me]);

  const run = async (key: string, fn: () => Promise<unknown>, done: string) => {
    setBusy(key);
    setError(null);
    setNotice(null);
    try {
      await fn();
      setNotice(done);
      load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  if (me && !can("manage_users")) {
    return (
      <ConsoleShell title="帳號管理">
        <EmptyState title="只有系統管理者可以管理帳號" />
      </ConsoleShell>
    );
  }

  return (
    <ConsoleShell title="帳號管理" crumbs={[{ href: "/console", label: "政府管理後台" }, { label: "帳號管理" }]}>
      {error ? (
        <div className="mb-3">
          <ErrorBox message={error} />
        </div>
      ) : null}
      {notice ? <div className="mb-3 rounded-md bg-[var(--surface-2)] px-4 py-2.5 text-[16px] text-[var(--ink-2)]">{notice}</div> : null}
      <div className="grid gap-4 xl:grid-cols-12">
        <section className="af-panel min-w-0 p-5 xl:col-span-4">
          <h2 className="text-[19px] font-semibold text-[var(--ink)]">新增帳號</h2>
          <div className="mt-3 space-y-3">
            <label className="block">
              <span className="af-label">帳號（英數字）</span>
              <input className="af-input mt-1 font-mono" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} maxLength={64} autoComplete="off" />
            </label>
            <label className="block">
              <span className="af-label">顯示名稱（例：仁愛鄉公所 王承辦）</span>
              <input className="af-input mt-1" value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} maxLength={60} />
            </label>
            <div>
              <span className="af-label">角色</span>
              <div className="mt-1 space-y-1.5">
                {(Object.keys(ROLE_HELP) as Role[]).map((r) => (
                  <label key={r} className={`flex cursor-pointer items-start gap-2.5 rounded-md border p-2.5 ${form.role === r ? "border-[var(--brand)] bg-[var(--surface-2)]" : "border-[var(--line)]"}`}>
                    <input type="radio" className="mt-1 h-4 w-4" checked={form.role === r} onChange={() => setForm({ ...form, role: r })} />
                    <span>
                      <span className="block text-[16px] font-semibold text-[var(--ink)]">{STAFF_ROLE_LABEL[r]}</span>
                      <span className="block text-[13px] text-[var(--muted)]">{ROLE_HELP[r]}</span>
                    </span>
                  </label>
                ))}
              </div>
            </div>
            <label className="block">
              <span className="af-label">初始密碼（至少 10 字元，含兩種字元類型；首次登入須變更）</span>
              <input className="af-input mt-1" type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} autoComplete="new-password" />
            </label>
            <button
              type="button"
              className="af-btn af-btn-primary af-btn-lg w-full"
              disabled={!form.username.trim() || !form.display_name.trim() || !form.password || busy === "create"}
              onClick={() =>
                run(
                  "create",
                  async () => {
                    await api.createUser({ ...form, username: form.username.trim(), display_name: form.display_name.trim() });
                    setForm({ username: "", display_name: "", role: "officer", password: "" });
                  },
                  "已建立帳號。請以安全方式告知使用者初始密碼。"
                )
              }
            >
              建立帳號
            </button>
          </div>
        </section>

        <section className="af-panel min-w-0 overflow-x-auto xl:col-span-8">
          {users === null ? (
            <Skeleton className="m-4 h-40" />
          ) : (
            <table className="af-table min-w-[760px]">
              <thead>
                <tr>
                  <th>帳號</th>
                  <th>角色</th>
                  <th>狀態</th>
                  <th>最後登入</th>
                  <th className="text-right">操作</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => {
                  const self = me?.id === u.id;
                  return (
                    <tr key={u.id} className={u.active ? "" : "opacity-60"}>
                      <td>
                        <div className="text-[16px] font-semibold text-[var(--ink)]">
                          {u.display_name}
                          {self ? <span className="ml-1.5 text-[13px] font-normal text-[var(--muted)]">（您）</span> : null}
                        </div>
                        <div className="font-mono text-[13px] text-[var(--muted)]">{u.username}</div>
                      </td>
                      <td>
                        <select className="af-input !w-auto !py-1.5" value={u.role} disabled={self || Boolean(busy)} onChange={(e) => run(`role-${u.id}`, () => api.updateUser(u.id, { role: e.target.value as Role }), `已變更 ${u.display_name} 的角色。`)}>
                          {(Object.keys(STAFF_ROLE_LABEL) as Role[]).map((r) => (
                            <option key={r} value={r}>
                              {STAFF_ROLE_LABEL[r]}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td className="text-[15px]">
                        {u.active ? <span className="text-[var(--st-done)]">啟用</span> : <span className="text-[var(--muted)]">停用</span>}
                        {u.locked ? <div className="text-[13px] text-[var(--sev-high)]">暫時鎖定中</div> : null}
                        {u.must_change_password ? <div className="text-[13px] text-[var(--st-pending)]">待變更密碼</div> : null}
                      </td>
                      <td className="text-[14px] text-[var(--muted)]">{u.last_login_at ? fmtTime(u.last_login_at) : "尚未登入"}</td>
                      <td className="text-right">
                        <div className="flex justify-end gap-1.5">
                          <button
                            type="button"
                            className="af-btn af-btn-secondary"
                            disabled={Boolean(busy)}
                            onClick={() => {
                              const pw = window.prompt(`為 ${u.display_name} 設定新的臨時密碼（至少 10 字元）：`);
                              if (pw) run(`pw-${u.id}`, () => api.updateUser(u.id, { password: pw }), "已重設密碼，使用者下次登入須變更；鎖定已解除。");
                            }}
                          >
                            重設密碼
                          </button>
                          {!self ? (
                            <button type="button" className={`af-btn ${u.active ? "af-btn-danger" : "af-btn-secondary"}`} disabled={Boolean(busy)} onClick={() => (u.active ? window.confirm(`停用 ${u.display_name}？該帳號將立即登出。`) : true) && run(`act-${u.id}`, () => api.updateUser(u.id, { active: !u.active }), u.active ? "已停用帳號。" : "已啟用帳號。")}>
                              {u.active ? "停用" : "啟用"}
                            </button>
                          ) : null}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </section>
      </div>
    </ConsoleShell>
  );
}
