"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import ConsoleShell from "@/components/ConsoleShell";
import { EmptyState, ErrorBox, Kpi, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { fmtTime } from "@/lib/format";
import { HAZARD_LABEL } from "@/lib/labels";
import type { GlobalOverview, PlatformItem } from "@/lib/types";

const STATUS_LABEL: Record<string, string> = { draft: "草稿", published: "已發布", archived: "已封存" };

export default function ConsoleHome() {
  const [items, setItems] = useState<PlatformItem[] | null>(null);
  const [overview, setOverview] = useState<GlobalOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(() => {
    Promise.all([api.listPlatforms(), api.overview()])
      .then(([p, o]) => {
        setItems(p.items);
        setOverview(o);
        setError(null);
      })
      .catch((e) => setError((e as Error).message));
  }, []);
  useEffect(() => {
    load();
  }, [load]);

  async function setStatus(id: string, status: string) {
    setBusy(id);
    try {
      await api.setPlatformStatus(id, status);
      load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function seed() {
    setBusy("seed");
    try {
      await api.seedDemo(false);
      load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <ConsoleShell title="平台管理" crumbs={[{ href: "/", label: "系統控制台" }, { label: "平台管理" }]}>
      {error ? (
        <div className="mb-3">
          <ErrorBox message={error} onRetry={load} />
        </div>
      ) : null}
      <div className="mb-4 grid grid-cols-2 gap-2 md:grid-cols-6">
        {overview ? (
          <>
            <Kpi value={overview.platforms_published} label="運作中的災情平台" hint={`共 ${overview.platforms_total} 個`} />
            <Kpi value={overview.cases_open} label="進行中案件" />
            <Kpi value={overview.cases_awaiting_dispatch} label="待派工" tone="pending" />
            <Kpi value={overview.cases_active} label="處理中" tone="active" />
            <Kpi value={overview.reports_last_24h} label="24 小時通報" />
            <div className="af-kpi flex flex-col justify-center gap-1.5">
              <Link href="/console/new" className="af-btn af-btn-primary w-full text-xs">
                建立新平台
              </Link>
              <button type="button" className="af-btn af-btn-secondary w-full text-xs" onClick={seed} disabled={busy === "seed"}>
                {busy === "seed" ? "建立中…" : "載入示範情境"}
              </button>
              <button
                type="button"
                className="af-btn af-btn-ghost w-full text-xs"
                disabled={busy === "prune"}
                title="刪除所有由生成器建立的平台，只保留內建的南投示範平台"
                onClick={async () => {
                  if (!window.confirm("清除所有生成的平台？內建的南投示範平台會保留。")) return;
                  setBusy("prune");
                  try {
                    const r = await api.prunePlatforms(0);
                    setError(r.count ? null : "沒有可清除的平台");
                    load();
                  } catch (e) {
                    setError((e as Error).message);
                  } finally {
                    setBusy(null);
                  }
                }}
              >
                {busy === "prune" ? "清除中…" : "清除生成的平台"}
              </button>
            </div>
          </>
        ) : (
          [0, 1, 2, 3, 4, 5].map((i) => <Skeleton key={i} className="h-[68px]" />)
        )}
      </div>

      {items === null ? (
        <Skeleton className="h-48" />
      ) : items.length === 0 ? (
        <EmptyState title="尚未建立任何平台" detail="輸入災害背景描述，系統會分析情境、建議模組與圖層，經確認後生成公開災情網站與管理後台。" action={<Link href="/console/new" className="af-btn af-btn-primary">建立第一個平台</Link>} />
      ) : (
        <div className="af-panel overflow-x-auto">
          <table className="af-table min-w-[860px]">
            <thead>
              <tr>
                <th>平台</th>
                <th>地區</th>
                <th>災害</th>
                <th>模組／圖層</th>
                <th>狀態</th>
                <th>建立時間</th>
                <th className="text-right">生成的兩套系統</th>
              </tr>
            </thead>
            <tbody>
              {items.map((p) => (
                <tr key={p.id} className="af-row-hover">
                  <td>
                    <Link href={`/console/platforms/${p.id}`} className="font-medium text-[var(--ink)] hover:underline">
                      {p.name}
                    </Link>
                    <div className="font-mono text-[11px] text-[var(--muted)]">/p/{p.slug}</div>
                  </td>
                  <td className="text-xs text-[var(--ink-2)]">
                    {p.county || "—"}
                    <div className="text-[var(--muted)]">{p.towns.join("、") || "全縣"}</div>
                  </td>
                  <td className="text-xs text-[var(--ink-2)]">{p.hazards.map((h) => HAZARD_LABEL[h] || h).join("、")}</td>
                  <td className="text-xs tabular-nums text-[var(--ink-2)]">
                    {p.modules.length} / {p.layers.length}
                  </td>
                  <td>
                    <span className="af-chip">{STATUS_LABEL[p.status] || p.status}</span>
                  </td>
                  <td className="text-xs text-[var(--muted)]">{fmtTime(p.created_at)}</td>
                  <td className="text-right">
                    <div className="flex justify-end gap-1">
                      <Link href={`/console/platforms/${p.id}`} className="af-btn af-btn-primary !py-1 text-xs" title="政府管理後台：案件佇列、派遣、官方情資">
                        政府後台
                      </Link>
                      <a href={`/p/${p.slug}`} target="_blank" rel="noreferrer" className="af-btn af-btn-secondary !py-1 text-xs" title="民眾通報網站：態勢圖、通報、處理進度">
                        民眾網站 ↗
                      </a>
                      {p.status === "published" ? (
                        <button type="button" className="af-btn af-btn-ghost !py-1 text-xs" disabled={busy === p.id} onClick={() => setStatus(p.id, "draft")}>
                          下架
                        </button>
                      ) : (
                        <button type="button" className="af-btn af-btn-ghost !py-1 text-xs" disabled={busy === p.id} onClick={() => setStatus(p.id, "published")}>
                          發布
                        </button>
                      )}
                    </div>
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
