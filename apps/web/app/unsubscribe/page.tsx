"use client";

// One-click unsubscribe from a case's progress e-mails (link in every mail).

import Link from "next/link";
import { useEffect, useState } from "react";
import { BrandLockup } from "@/components/Brand";
import { api } from "@/lib/api";

export default function UnsubscribePage() {
  const [state, setState] = useState<"idle" | "busy" | "done" | "error">("idle");
  const [message, setMessage] = useState("");
  const [token, setToken] = useState("");

  useEffect(() => {
    setToken(new URLSearchParams(window.location.search).get("token") || "");
  }, []);

  async function confirm() {
    setState("busy");
    try {
      const r = await api.unsubscribe(token);
      setMessage(r.message);
      setState("done");
    } catch (e) {
      setMessage((e as Error).message);
      setState("error");
    }
  }

  return (
    <div className="grid min-h-screen place-items-center px-4" style={{ background: "var(--bg)" }}>
      <div className="w-full max-w-md">
        <div className="mb-5 flex justify-center">
          <BrandLockup subtitle="災情通報與處理平台" />
        </div>
        <div className="af-panel p-6 text-center">
          <h1 className="af-h1">取消案件進度通知</h1>
          {state === "done" ? (
            <p className="mt-3 text-[17px] text-[var(--st-done)]">{message}</p>
          ) : state === "error" ? (
            <p className="mt-3 text-[17px] text-[var(--sev-high)]">{message}</p>
          ) : (
            <>
              <p className="mt-3 text-[16px] text-[var(--ink-2)]">確認後，這筆通報的處理進度將不再寄信給您。您留下的聯絡資料仍僅供承辦人員查證使用。</p>
              <button type="button" className="af-btn af-btn-primary af-btn-lg mt-5 w-full" disabled={!token || state === "busy"} onClick={confirm}>
                {state === "busy" ? "處理中…" : "確認取消通知"}
              </button>
              {!token ? <p className="mt-2 text-[14px] text-[var(--sev-high)]">連結不完整，請從通知信中的連結開啟。</p> : null}
            </>
          )}
          <Link href="/" className="mt-5 inline-block text-[15px] text-[var(--focus)] hover:underline">
            回到首頁
          </Link>
        </div>
      </div>
    </div>
  );
}
