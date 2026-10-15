"use client";

// 變更密碼. When an administrator created or reset the account, this page is
// mandatory before anything else in the console (ConsoleShell redirects here).

import { useEffect, useState } from "react";
import ConsoleShell from "@/components/ConsoleShell";
import { ErrorBox } from "@/components/ui";
import { api, setToken } from "@/lib/api";
import { loadMe, useMe } from "@/lib/auth";

export default function AccountPage() {
  const { me } = useMe();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [again, setAgain] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [forced, setForced] = useState(false);

  useEffect(() => {
    setForced(new URLSearchParams(window.location.search).get("force") === "1");
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (next !== again) {
      setError("兩次輸入的新密碼不一致");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const r = await api.changePassword(current, next);
      setToken(r.token);
      await loadMe(true);
      setDone(true);
      const target = new URLSearchParams(window.location.search).get("next");
      if (forced) window.location.assign(target && target.startsWith("/") && !target.startsWith("//") ? target : "/console");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <ConsoleShell title="變更密碼" crumbs={[{ href: "/console", label: "政府管理後台" }, { label: "變更密碼" }]}>
      <form onSubmit={submit} className="af-panel max-w-lg p-6">
        {forced || me?.must_change_password ? (
          <div className="mb-4 rounded-md border px-4 py-3 text-[16px]" style={{ borderColor: "#fedf89", background: "#fffaeb", color: "#93370d" }}>
            這是管理者設定的密碼，請先變更為只有您知道的密碼再繼續使用。
          </div>
        ) : null}
        {error ? (
          <div className="mb-3">
            <ErrorBox message={error} />
          </div>
        ) : null}
        {done && !forced ? <div className="mb-3 rounded-md bg-[var(--surface-2)] px-4 py-2.5 text-[16px] text-[var(--st-done)]">已變更密碼，其他裝置上的登入已失效。</div> : null}
        <label className="block">
          <span className="af-label">目前密碼</span>
          <input className="af-input mt-1" type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} required />
        </label>
        <label className="mt-3 block">
          <span className="af-label">新密碼（至少 10 字元，含英文大小寫、數字或符號中兩種）</span>
          <input className="af-input mt-1" type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} required />
        </label>
        <label className="mt-3 block">
          <span className="af-label">再輸入一次新密碼</span>
          <input className="af-input mt-1" type="password" autoComplete="new-password" value={again} onChange={(e) => setAgain(e.target.value)} required />
        </label>
        <button type="submit" className="af-btn af-btn-primary af-btn-lg mt-5 w-full" disabled={busy || !current || !next || !again}>
          {busy ? "變更中…" : "變更密碼"}
        </button>
      </form>
    </ConsoleShell>
  );
}
