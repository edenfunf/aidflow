"use client";

// 建立災害平台 (G-10): name the disaster, confirm its hazard types and region,
// and the system composes the matching report categories and map layers by
// rule. No model, no free-text planner.

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import ConsoleShell from "@/components/ConsoleShell";
import { EmptyState, ErrorBox, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { useMe } from "@/lib/auth";
import { CategoryIcon } from "@/lib/categoryIcons";
import { LAYERS, categoryHex } from "@/lib/labels";
import type { PlatformDetail, PlatformOptions, PlatformPreview } from "@/lib/types";

const NAME_EXAMPLES = ["115 年 0903 豪雨", "卡努颱風", "115 年 1021 地震"];

export default function NewPlatformPage() {
  const { can, loading: meLoading } = useMe();
  const [options, setOptions] = useState<PlatformOptions | null>(null);
  const [name, setName] = useState("");
  const [hazards, setHazards] = useState<string[]>([]);
  const [hazardsTouched, setHazardsTouched] = useState(false);
  const [county, setCounty] = useState("南投縣");
  const [towns, setTowns] = useState<string[]>([]);
  const [publish, setPublish] = useState(true);
  const [withDemo, setWithDemo] = useState(false);
  const [preview, setPreview] = useState<PlatformPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<PlatformDetail | null>(null);
  const [seedNote, setSeedNote] = useState<string | null>(null);
  const timer = useRef<number | null>(null);

  useEffect(() => {
    api.platformOptions().then(setOptions).catch((e) => setError((e as Error).message));
  }, []);

  // live preview: hazards are suggested from the name until the operator picks them
  useEffect(() => {
    if (!can("manage_platforms")) return;
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      api
        .previewPlatform({ name, hazards: hazardsTouched ? hazards : null, county, towns })
        .then((p) => {
          setPreview(p);
          // same list → keep the same array, or this effect would re-run forever
          if (!hazardsTouched) setHazards((cur) => (cur.join() === p.hazards.join() ? cur : p.hazards));
        })
        .catch(() => undefined);
    }, 300);
    return () => {
      if (timer.current) window.clearTimeout(timer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [name, hazards, hazardsTouched, county, towns]);

  const countyTowns = useMemo(() => options?.regions.find((r) => r.county === county)?.towns ?? [], [options, county]);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const p = await api.createPlatform({ name: name.trim(), hazards, county, towns, publish });
      if (withDemo) {
        try {
          const r = await api.seedPlatformDemo(p.id);
          setSeedNote(`已帶入示範資料：${r.reports} 筆通報、${r.cases} 件案件`);
        } catch {
          setSeedNote("示範資料未帶入（示範模式未開啟），平台已建立完成。");
        }
      }
      setCreated(p);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (!meLoading && !can("manage_platforms")) {
    return (
      <ConsoleShell title="建立災害平台">
        <EmptyState title="只有系統管理者可以建立災害平台" detail="如需建立新的災害平台，請洽系統管理者。" action={<Link href="/console" className="af-btn af-btn-primary">回到災害平台</Link>} />
      </ConsoleShell>
    );
  }

  if (created) {
    return (
      <ConsoleShell title="平台已建立" crumbs={[{ href: "/console", label: "災害平台" }, { label: "建立完成" }]}>
        <div className="af-panel mx-auto max-w-3xl p-6">
          <div className="flex items-center gap-2.5">
            <span className="af-check grid h-8 w-8 place-items-center rounded-full text-white" style={{ background: "var(--st-done)" }}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M5 12.5 10 17.5 19 7" />
              </svg>
            </span>
            <span className="text-[15px] font-semibold text-[var(--st-done)]">{created.status === "published" ? "已建立並發布" : "已建立（草稿，尚未公開）"}</span>
          </div>
          <h2 className="mt-3 text-[28px] font-bold text-[var(--ink)]">{created.name}</h2>
          <p className="mt-1 text-[16px] text-[var(--ink-2)]">
            {created.county} {created.towns.join("、")} · {(created.configuration.hazard_labels || []).join("、")}
          </p>
          {seedNote ? <p className="mt-2 text-[15px] text-[var(--muted)]">{seedNote}</p> : null}
          <div className="mt-6 grid gap-3 sm:grid-cols-2">
            <Link href={`/console/platforms/${created.id}`} className="af-subtle af-panel-hover block rounded-md p-4">
              <div className="text-[18px] font-semibold text-[var(--ink)]">政府管理後台 →</div>
              <p className="mt-1 text-[15px] text-[var(--muted)]">審核分流、案件佇列、LINE 群組通知設定</p>
            </Link>
            <a href={`/p/${created.slug}`} target="_blank" rel="noreferrer" className="af-subtle af-panel-hover block rounded-md p-4">
              <div className="text-[18px] font-semibold text-[var(--ink)]">民眾通報網站 ↗</div>
              <p className="mt-1 font-mono text-[14px] text-[var(--muted)]">/p/{created.slug}</p>
            </a>
          </div>
          <div className="mt-5 rounded-md bg-[var(--surface-2)] p-4 text-[15px] text-[var(--ink-2)]">
            <div className="font-semibold text-[var(--ink)]">接下來</div>
            <ol className="mt-1 list-decimal space-y-1 pl-5">
              <li>在政府管理後台綁定縣府 LINE 群組，新通報才會即時通知承辦人員。</li>
              <li>將嵌入地圖放到縣府網站：<code className="rounded bg-white px-1.5 py-0.5 text-[13px]">{`<iframe src="${created.embed_url}" width="100%" height="560" style="border:0" loading="lazy" title="災情地圖"></iframe>`}</code></li>
            </ol>
          </div>
          <div className="mt-5 flex flex-wrap gap-2">
            <button type="button" className="af-btn af-btn-secondary" onClick={() => { setCreated(null); setName(""); setHazardsTouched(false); setSeedNote(null); }}>
              再建立一個平台
            </button>
          </div>
        </div>
      </ConsoleShell>
    );
  }

  const canSubmit = Boolean(name.trim() && hazards.length && !busy);

  return (
    <ConsoleShell title="建立災害平台" crumbs={[{ href: "/console", label: "災害平台" }, { label: "建立平台" }]}>
      <div className="grid gap-4 lg:grid-cols-12">
        <section className="af-panel p-5 lg:col-span-7">
          {error ? (
            <div className="mb-3">
              <ErrorBox message={error} />
            </div>
          ) : null}
          <label className="block">
            <span className="text-[17px] font-semibold text-[var(--ink)]">1. 災害名稱</span>
            <input className="af-input mt-2 !text-[19px]" placeholder="例如：115 年 0903 豪雨" value={name} onChange={(e) => setName(e.target.value)} maxLength={120} autoFocus />
          </label>
          <div className="mt-1.5 flex flex-wrap gap-1.5 text-[14px] text-[var(--muted)]">
            範例：
            {NAME_EXAMPLES.map((n) => (
              <button key={n} type="button" className="text-[var(--focus)] hover:underline" onClick={() => setName(n)}>
                {n}
              </button>
            ))}
          </div>

          <div className="mt-6">
            <div className="flex items-baseline justify-between">
              <span className="text-[17px] font-semibold text-[var(--ink)]">2. 災害類型</span>
              <span className="text-[14px] text-[var(--muted)]">{hazardsTouched ? "已手動選擇" : "依名稱自動建議，可修改"}</span>
            </div>
            {!options ? (
              <Skeleton className="mt-2 h-12" />
            ) : (
              <div className="mt-2 flex flex-wrap gap-2">
                {options.hazards.map((h) => {
                  const on = hazards.includes(h.key);
                  return (
                    <button
                      key={h.key}
                      type="button"
                      aria-pressed={on}
                      className={`af-chip !px-4 !py-2 !text-[16px] ${on ? "af-chip-on" : ""}`}
                      onClick={() => {
                        setHazardsTouched(true);
                        setHazards(on ? hazards.filter((x) => x !== h.key) : [...hazards, h.key]);
                      }}
                    >
                      {h.label}
                    </button>
                  );
                })}
              </div>
            )}
            {!hazards.length && name.trim() ? <div className="mt-1.5 text-[14px] text-[var(--sev-high)]">名稱中沒有辨識到災害類型，請至少選擇一項。</div> : null}
          </div>

          <div className="mt-6 grid gap-3 sm:grid-cols-2">
            <label className="block">
              <span className="text-[17px] font-semibold text-[var(--ink)]">3. 縣市</span>
              <select className="af-input mt-2" value={county} onChange={(e) => { setCounty(e.target.value); setTowns([]); }}>
                {(options?.regions || []).map((r) => (
                  <option key={r.county} value={r.county}>
                    {r.county}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="text-[17px] font-semibold text-[var(--ink)]">發布</span>
              <select className="af-input mt-2" value={publish ? "1" : "0"} onChange={(e) => setPublish(e.target.value === "1")}>
                <option value="1">建立後立即公開</option>
                <option value="0">先存為草稿</option>
              </select>
            </label>
          </div>
          <div className="mt-3">
            <div className="flex items-baseline justify-between">
              <span className="text-[15px] font-medium text-[var(--ink-2)]">鄉鎮市區（選填，未選＝全縣）</span>
              {towns.length ? (
                <button type="button" className="text-[14px] text-[var(--focus)] hover:underline" onClick={() => setTowns([])}>
                  清除
                </button>
              ) : null}
            </div>
            <div className="mt-2 flex max-h-40 flex-wrap gap-1.5 overflow-y-auto">
              {countyTowns.map((t) => {
                const on = towns.includes(t);
                return (
                  <button key={t} type="button" aria-pressed={on} className={`af-chip ${on ? "af-chip-on" : ""}`} onClick={() => setTowns(on ? towns.filter((x) => x !== t) : [...towns, t])}>
                    {t}
                  </button>
                );
              })}
            </div>
          </div>

          <label className="mt-6 flex items-center gap-2.5 text-[15px] text-[var(--ink-2)]">
            <input type="checkbox" className="h-5 w-5 accent-[var(--brand)]" checked={withDemo} onChange={(e) => setWithDemo(e.target.checked)} />
            同時帶入示範資料（教育訓練／展示用，會標示為示範）
          </label>

          <button type="button" className="af-btn af-btn-primary af-btn-lg mt-6 w-full" disabled={!canSubmit} onClick={submit}>
            {busy ? (
              <>
                <span className="af-spinner" /> 建立中…
              </>
            ) : (
              "建立災害平台"
            )}
          </button>
        </section>

        <aside className="af-panel p-5 lg:col-span-5">
          <div className="text-[17px] font-semibold text-[var(--ink)]">系統將自動產生</div>
          <p className="mt-1 text-[14px] text-[var(--muted)]">依災害類型以規則產生，不經 AI 判斷。建立後可在後台調整成案規則。</p>
          {!preview || !preview.hazards.length ? (
            <div className="mt-4 text-[15px] text-[var(--faint)]">輸入災害名稱或選擇災害類型後顯示。</div>
          ) : (
            <>
              <div className="mt-4 text-[14px] font-semibold text-[var(--ink-2)]">民眾通報類別（{preview.report_categories.length}）</div>
              <ul className="mt-2 grid grid-cols-2 gap-1.5">
                {preview.report_categories.map((c) => (
                  <li key={c.key} className="flex items-center gap-2 text-[15px] text-[var(--ink)]">
                    <span className="inline-grid h-7 w-7 place-items-center rounded-full text-white" style={{ background: categoryHex(c.key) }}>
                      <CategoryIcon category={c.key} size={15} />
                    </span>
                    {c.label}
                  </li>
                ))}
              </ul>
              <div className="mt-4 text-[14px] font-semibold text-[var(--ink-2)]">地圖資料圖層（民眾可自行開關）</div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {preview.layers.filter((k) => LAYERS[k]).map((k) => (
                  <span key={k} className="af-chip">
                    <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: LAYERS[k].hex }} />
                    {LAYERS[k].label}
                  </span>
                ))}
              </div>
              <div className="mt-4 rounded-md bg-[var(--surface-2)] p-3 text-[14px] leading-relaxed text-[var(--ink-2)]">
                同一地點多位民眾回報會自動成案，進入<b>承辦審核</b>；審核後分流為<b>上報 EMIC</b>或<b>開放民眾協助處理</b>。
              </div>
            </>
          )}
        </aside>
      </div>
    </ConsoleShell>
  );
}
