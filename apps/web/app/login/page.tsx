"use client";

// Staff sign-in for the 政府管理後台. Citizens never need an account.

import Link from "next/link";
import { useEffect, useState } from "react";
import { BrandLockup } from "@/components/Brand";
import { ErrorBox } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { setSession } from "@/lib/auth";

function safeNext(raw: string | null): string {
  // only same-site paths: never bounce a freshly signed-in officer elsewhere
  if (!raw || !raw.startsWith("/") || raw.startsWith("//") || raw.startsWith("/login")) return "/console";
  return raw;
}

export default function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    const reason = new URLSearchParams(window.location.search).get("reason");
    if (reason === "idle") setNotice("閒置超過 30 分鐘，已自動登出。");
    if (reason === "expired") setNotice("登入已失效，請重新登入。");
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await api.login(username.trim(), password);
      setSession(res.token, res.user);
      const next = safeNext(new URLSearchParams(window.location.search).get("next"));
      window.location.assign(res.user.must_change_password ? `/console/account?force=1&next=${encodeURIComponent(next)}` : next);
    } catch (err) {
      const detail = err instanceof ApiError ? err.detail : null;
      const lockedUntil = detail && typeof detail === "object" ? (detail as { locked_until?: string }).locked_until : undefined;
      setError(lockedUntil ? `登入失敗次數過多，帳號鎖定至 ${new Date(lockedUntil).toLocaleTimeString("zh-TW", { hour: "2-digit", minute: "2-digit" })}。` : (err as Error).message);
      setPassword("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid min-h-screen place-items-center px-4 py-10" style={{ background: "var(--bg)" }}>
      <div className="w-full max-w-[420px]">
        <div className="mb-6 flex justify-center">
          <BrandLockup subtitle="災情通報與處理平台" />
        </div>
        <form onSubmit={submit} className="af-panel p-6">
          <h1 className="af-h1">政府管理後台登入</h1>
          <p className="mt-1 text-sm text-[var(--muted)]">承辦審核人員、業務主管與系統管理者使用。民眾通報不需登入。</p>
          {notice ? <div className="mt-3 rounded bg-[var(--surface-2)] px-3 py-2 text-sm text-[var(--ink-2)]">{notice}</div> : null}
          {error ? (
            <div className="mt-3">
              <ErrorBox message={error} />
            </div>
          ) : null}
          <label className="mt-4 block">
            <span className="af-label">帳號</span>
            <input className="af-input mt-1" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required autoFocus />
          </label>
          <label className="mt-3 block">
            <span className="af-label">密碼</span>
            <input className="af-input mt-1" type="password" autoComplete="off" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </label>
          <button type="submit" className="af-btn af-btn-primary af-btn-lg mt-5 w-full" disabled={busy || !username || !password}>
            {busy ? (
              <>
                <span className="af-spinner" /> 登入中…
              </>
            ) : (
              "登入"
            )}
          </button>
          <p className="mt-4 text-xs leading-relaxed text-[var(--faint)]">連續輸入錯誤會暫時鎖定帳號；閒置 30 分鐘自動登出。忘記密碼請洽系統管理者重設。</p>
        </form>
        <div className="mt-4 text-center text-sm">
          <Link href="/" className="text-[var(--focus)] hover:underline">
            ← 回到首頁
          </Link>
        </div>
      </div>
    </div>
  );
}
