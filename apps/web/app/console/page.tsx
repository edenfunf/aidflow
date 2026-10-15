"use client";

// 政府管理後台 landing: every disaster platform with its review backlog.

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import ConsoleShell from "@/components/ConsoleShell";
import { EmptyState, ErrorBox, Kpi, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { useMe } from "@/lib/auth";
import { fmtTime } from "@/lib/format";
import { HAZARD_LABEL } from "@/lib/labels";
import type { GlobalOverview, PlatformItem } from "@/lib/types";

const STATUS_LABEL: Record<string, string> = { draft: "草稿", published: "已發布", archived: "已封存" };

export default function ConsoleHome() {
  const { can } = useMe();
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

  const admin = can("manage_platforms");

  return (
    <ConsoleShell title="災害平台" crumbs={[{ label: "政府管理後台" }]}>
      {error ? (
        <div className="mb-3">
          <ErrorBox message={error} onRetry={load} />
        </div>
      ) : null}
      <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-5">
        {overview ? (
          <>
            <Kpi value={overview.cases_pending_review} label="待審核" tone="pending" hint="需承辦決定處理方式" />
            <Kpi value={overview.cases_active} label="EMIC 處理中" tone="active" />
            <Kpi value={overview.cases_community} label="民眾協助中" tone="community" />
            <Kpi value={overview.reports_last_24h} label="24 小時通報" />
            <Kpi value={overview.platforms_published} label="運作中的平台" hint={`共 ${overview.platforms_total} 個`} />
          </>
        ) : (
          [0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-[84px]" />)
        )}
      </div>

      {admin ? (
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <Link href="/console/new" className="af-btn af-btn-primary">
            建立災害平台
          </Link>
          <button
            type="button"
            className="af-btn af-btn-secondary"
            disabled={busy === "seed"}
            onClick={async () => {
              setBusy("seed");
              try {
                await api.seedDemo(false);
                load();
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(null);
              }
            }}
          >
            {busy === "seed" ? "建立中…" : "載入南投示範情境"}
          </button>
          <button
            type="button"
            className="af-btn af-btn-ghost"
            disabled={busy === "prune"}
            title="刪除所有建立的平台，只保留內建的南投示範平台（示範模式）"
            onClick={async () => {
              if (!window.confirm("清除所有建立的平台？內建的南投示範平台會保留。")) return;
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
            {busy === "prune" ? "清除中…" : "清除示範用平台"}
          </button>
        </div>
      ) : null}

      {items === null ? (
        <Skeleton className="h-48" />
      ) : items.length === 0 ? (
        <EmptyState title="尚未建立任何災害平台" detail="系統管理者輸入災害名稱並選擇災害類型，即可建立民眾通報網站與政府管理後台。" action={admin ? <Link href="/console/new" className="af-btn af-btn-primary">建立第一個平台</Link> : undefined} />
      ) : (
        <div className="af-panel overflow-x-auto">
          <table className="af-table min-w-[860px]">
            <thead>
              <tr>
                <th>災害平台</th>
                <th>地區</th>
                <th>災害類型</th>
                <th>狀態</th>
                <th>建立時間</th>
                <th className="text-right">入口</th>
              </tr>
            </thead>
            <tbody>
              {items.map((p) => (
                <tr key={p.id} className="af-row-hover">
                  <td>
                    <Link href={`/console/platforms/${p.id}`} className="text-[17px] font-semibold text-[var(--ink)] hover:underline">
                      {p.name}
                    </Link>
                    <div className="font-mono text-[13px] text-[var(--muted)]">/p/{p.slug}</div>
                  </td>
                  <td className="text-sm text-[var(--ink-2)]">
                    {p.county || "—"}
                    <div className="text-[var(--muted)]">{p.towns.join("、") || "全縣"}</div>
                  </td>
                  <td className="text-sm text-[var(--ink-2)]">{p.hazards.map((h) => HAZARD_LABEL[h] || h).join("、")}</td>
                  <td>
                    <span className="af-chip">{STATUS_LABEL[p.status] || p.status}</span>
                  </td>
                  <td className="text-sm text-[var(--muted)]">{fmtTime(p.created_at)}</td>
                  <td className="text-right">
                    <div className="flex justify-end gap-1.5">
                      <Link href={`/console/platforms/${p.id}`} className="af-btn af-btn-primary">
                        進入後台
                      </Link>
                      <a href={`/p/${p.slug}`} target="_blank" rel="noreferrer" className="af-btn af-btn-secondary">
                        民眾網站 ↗
                      </a>
                      {admin ? (
                        p.status === "published" ? (
                          <button type="button" className="af-btn af-btn-ghost" disabled={busy === p.id} onClick={() => setStatus(p.id, "draft")}>
                            下架
                          </button>
                        ) : (
                          <button type="button" className="af-btn af-btn-ghost" disabled={busy === p.id} onClick={() => setStatus(p.id, "published")}>
                            發布
                          </button>
                        )
                      ) : null}
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
