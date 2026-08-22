"use client";

import { useEffect, useState } from "react";
import ConsoleShell from "@/components/ConsoleShell";
import { ErrorBox, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { LAYERS } from "@/lib/labels";
import type { ConnectorStatusItem } from "@/lib/types";

export default function ConnectorsPage() {
  const [items, setItems] = useState<ConnectorStatusItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api.listConnectors().then((r) => setItems(r.items)).catch((e) => setError((e as Error).message));
  }, []);

  return (
    <ConsoleShell title="官方資料介接" crumbs={[{ href: "/console", label: "平台總覽" }, { label: "官方資料介接" }]}>
      <p className="mb-3 max-w-3xl text-sm text-[var(--muted)]">
        所有官方資料經 Connector → Normalizer 轉成統一的地圖 Feature，前端不需理解各政府 API 的格式。未設定金鑰的來源會誠實顯示為「不可用」，平台仍可正常運作。
      </p>
      {error ? <ErrorBox message={error} /> : null}
      {items === null ? (
        <Skeleton className="h-48" />
      ) : (
        <div className="af-panel overflow-x-auto">
          <table className="af-table min-w-[760px]">
            <thead>
              <tr>
                <th>來源</th>
                <th>提供單位</th>
                <th>餵入圖層</th>
                <th>憑證</th>
                <th>狀態</th>
              </tr>
            </thead>
            <tbody>
              {items.map((c) => (
                <tr key={c.id}>
                  <td>
                    <div className="font-medium">{c.name}</div>
                    <div className="max-w-md text-xs text-[var(--ink-2)]">{c.description}</div>
                    <a href={c.homepage} target="_blank" rel="noreferrer" className="text-[11px] text-[var(--focus)] hover:underline">
                      {c.homepage}
                    </a>
                  </td>
                  <td className="text-xs">{c.provider}</td>
                  <td>
                    <div className="flex flex-wrap gap-1">
                      {c.layers.map((l) => (
                        <span key={l} className="af-chip">
                          <span className="inline-block h-2 w-2 rounded-sm" style={{ background: LAYERS[l]?.hex }} />
                          {LAYERS[l]?.label || l}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="text-xs">{c.requires_key ? <code className="rounded bg-[var(--surface-3)] px-1 py-0.5 text-[11px]">{c.key_env}</code> : "公開，無需金鑰"}</td>
                  <td className="text-xs">
                    <span className="inline-flex items-center gap-1.5">
                      <span className="h-1.5 w-1.5 rounded-full" style={{ background: c.live_enabled ? "var(--st-done)" : "var(--st-pending)" }} />
                      {c.live_enabled ? "可即時介接" : "未設定（graceful fallback）"}
                    </span>
                    {c.detail ? <div className="mt-0.5 text-[11px] text-[var(--muted)]">{c.detail}</div> : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </ConsoleShell>
  );
}
