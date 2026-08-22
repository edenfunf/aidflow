"use client";

// Mobile-first citizen report form. Categories, roles and the map centre all
// come from the platform configuration (Module Registry), not from code.

import dynamic from "next/dynamic";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import PortalShell from "@/components/PortalShell";
import { ErrorBox, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { getClientKey } from "@/lib/clientKey";
import { categoryHex } from "@/lib/labels";
import { CategoryIcon } from "@/lib/categoryIcons";
import ProgressRing from "@/components/ProgressRing";
import type { PublicPlatform, SubmitReportResponse } from "@/lib/types";

const PickerMap = dynamic(() => import("@/components/PickerMap"), { ssr: false, loading: () => <Skeleton className="h-full w-full" /> });

type GeoState = "idle" | "locating" | "ok" | "denied" | "manual";

export default function ReportPage() {
  const { slug } = useParams<{ slug: string }>();
  const [platform, setPlatform] = useState<PublicPlatform | null>(null);
  const [category, setCategory] = useState("");
  const [point, setPoint] = useState<[number, number] | null>(null);
  const [geo, setGeo] = useState<GeoState>("idle");
  const [accuracy, setAccuracy] = useState<number | null>(null);
  const [address, setAddress] = useState("");
  const [description, setDescription] = useState("");
  const [role, setRole] = useState("citizen");
  const [files, setFiles] = useState<File[]>([]);
  const [contactOpen, setContactOpen] = useState(false);
  const [name, setName] = useState("");
  const [contact, setContact] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SubmitReportResponse | null>(null);
  const [photoNote, setPhotoNote] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    api.publicPlatform(slug).then(setPlatform).catch((e) => setError((e as Error).message));
  }, [slug]);

  const previews = useMemo(() => files.map((f) => ({ name: f.name, url: URL.createObjectURL(f) })), [files]);
  useEffect(() => () => previews.forEach((p) => URL.revokeObjectURL(p.url)), [previews]);

  function locate() {
    if (!navigator.geolocation) {
      setGeo("manual");
      return;
    }
    setGeo("locating");
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setPoint([pos.coords.latitude, pos.coords.longitude]);
        setAccuracy(Math.round(pos.coords.accuracy));
        setGeo("ok");
      },
      () => setGeo("denied"),
      { enableHighAccuracy: true, timeout: 12000, maximumAge: 30000 }
    );
  }

  async function submit() {
    if (!platform || !category) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await api.submitReport(slug, {
        category,
        description: description.trim() || null,
        lat: point?.[0] ?? null,
        lon: point?.[1] ?? null,
        address: address.trim() || null,
        reporter_role: role,
        reporter_name: name.trim() || null,
        reporter_contact: contact.trim() || null,
        client_key: getClientKey(),
      });
      setResult(res);
      if (files.length) {
        let ok = 0;
        for (const f of files.slice(0, 5)) {
          try {
            await api.uploadReportPhoto(res.report_id, f);
            ok += 1;
          } catch {
            /* keep going */
          }
        }
        setPhotoNote(ok === files.length ? `已上傳 ${ok} 張照片` : `已上傳 ${ok}/${files.length} 張照片`);
      }
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  const canSubmit = Boolean(platform && category && !submitting);
  const center = point ?? platform?.map.center ?? [23.91, 120.69];

  if (result) {
    const caseHref = result.case_id ? `/p/${slug}/cases/${result.case_id}` : null;
    return (
      <PortalShell platform={platform} slug={slug}>
        <div className="mx-auto max-w-lg">
          <div className="af-panel p-5">
            <div className="af-eyebrow">通報已送出</div>
            <h1 className="mt-1 text-lg font-semibold text-[var(--ink)]">{result.case_created ? "已自動成案，進入政府待派工" : result.case_id ? "已併入既有案件" : "感謝您的回報"}</h1>
            <p className="mt-2 text-sm leading-relaxed text-[var(--ink-2)]">{result.message}</p>
            {photoNote ? <p className="mt-1 text-xs text-[var(--muted)]">{photoNote}</p> : null}
            <div className="af-subtle mt-3 flex items-center gap-4 p-3">
              <ProgressRing value={result.unique_reporters} total={result.required_unique_reporters} label="不同回報者" />
              <div className="text-xs leading-relaxed text-[var(--ink-2)]">
                {result.unique_reporters >= result.required_unique_reporters ? (
                  <>
                    <div className="text-sm font-semibold text-[var(--st-active)]">已達成案門檻</div>
                    這個地點已有 {result.unique_reporters} 位不同民眾回報，系統自動成案並通知政府派工。
                  </>
                ) : (
                  <>
                    <div className="text-sm font-semibold text-[var(--st-pending)]">再 {Math.max(0, result.required_unique_reporters - result.unique_reporters)} 位不同民眾回報就會自動成案</div>
                    同一地點、同類災情、時間相近的回報會自動歸為一組；由 {result.required_unique_reporters} 位不同回報者確認後即正式成案。您可以把通報連結分享給在場的人。
                  </>
                )}
              </div>
            </div>
            <div className="mt-4 flex flex-col gap-2">
              {caseHref ? (
                <Link href={caseHref} className="af-btn af-btn-primary af-btn-lg">
                  追蹤處理進度 {result.case_number ? `(${result.case_number})` : ""}
                </Link>
              ) : (
                <Link href={`/p/${slug}`} className="af-btn af-btn-primary af-btn-lg">
                  回到災情態勢
                </Link>
              )}
              <button
                type="button"
                className="af-btn af-btn-secondary"
                onClick={() => {
                  setResult(null);
                  setCategory("");
                  setDescription("");
                  setFiles([]);
                  setPhotoNote(null);
                }}
              >
                再回報一筆
              </button>
            </div>
            <p className="mt-4 text-[11px] leading-relaxed text-[var(--faint)]">您的姓名與聯絡方式僅供處理單位聯繫，不會公開。公開頁面上的位置已粗化、文字已去識別化。</p>
          </div>
        </div>
      </PortalShell>
    );
  }

  return (
    <PortalShell platform={platform} slug={slug}>
      <div className="mx-auto max-w-lg pb-24 sm:pb-0">
        <div className="mb-3">
          <div className="af-eyebrow">我要通報</div>
          <h1 className="af-h1">回報您看到的災情</h1>
          <p className="mt-1 text-xs text-[var(--muted)]">危及生命請先撥打 119。同一地點有 {platform?.cluster_policy.required_unique_reporters ?? 2} 位以上不同民眾回報時，會自動成案並通知政府派工。</p>
        </div>
        {error ? (
          <div className="mb-3">
            <ErrorBox message={error} />
          </div>
        ) : null}

        {/* 1. what */}
        <section className="af-panel mb-3 p-4">
          <h2 className="af-h2 mb-2">1. 發生什麼事？</h2>
          {!platform ? (
            <Skeleton className="h-28" />
          ) : (
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {platform.report_categories.map((c) => {
                const on = category === c.key;
                return (
                  <button
                    key={c.key}
                    type="button"
                    onClick={() => setCategory(c.key)}
                    aria-pressed={on}
                    className="flex items-center gap-2 rounded border px-3 py-3 text-left text-sm font-medium transition"
                    style={{
                      borderColor: on ? "var(--brand)" : "var(--line-2)",
                      background: on ? "var(--brand)" : "var(--surface)",
                      color: on ? "#fff" : "var(--ink)",
                    }}
                  >
                    <span className="inline-grid h-7 w-7 flex-none place-items-center rounded-full text-white" style={{ background: on ? "rgba(255,255,255,0.22)" : categoryHex(c.key) }}>
                      <CategoryIcon category={c.key} size={15} />
                    </span>
                    {c.label}
                  </button>
                );
              })}
            </div>
          )}
        </section>

        {/* 2. where */}
        <section className="af-panel mb-3 p-4">
          <h2 className="af-h2 mb-2">2. 在哪裡？</h2>
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" className="af-btn af-btn-primary" onClick={locate} disabled={geo === "locating"}>
              {geo === "locating" ? (
                <>
                  <span className="af-spinner" /> 定位中…
                </>
              ) : (
                "使用目前位置（GPS）"
              )}
            </button>
            <span className="text-xs text-[var(--muted)]">
              {geo === "ok" && point ? `已定位（誤差約 ${accuracy ?? "?"} 公尺）` : geo === "denied" ? "無法取得定位，請在地圖上點選位置" : "或直接在地圖上點選"}
            </span>
          </div>
          <div className="mt-2 overflow-hidden rounded border" style={{ borderColor: "var(--line)" }}>
            <div className="h-56">
              <PickerMap
                center={center}
                zoom={point ? 15 : platform?.map.zoom ?? 11}
                point={point}
                accuracy={geo === "ok" ? accuracy : null}
                color={category ? categoryHex(category) : undefined}
                onPick={(lat, lon) => {
                  setPoint([lat, lon]);
                  setGeo("manual");
                }}
              />
            </div>
          </div>
          <div className="mt-1 text-[11px] text-[var(--muted)]">{point ? `座標 ${point[0].toFixed(5)}, ${point[1].toFixed(5)}` : "尚未選擇位置（沒有位置的通報無法與其他人的回報合併成案）"}</div>
          <input className="af-input mt-2" placeholder="地點補充（選填，例如：台14甲線 18K 清境下方）" value={address} onChange={(e) => setAddress(e.target.value)} maxLength={300} />
        </section>

        {/* 3. photo */}
        <section className="af-panel mb-3 p-4">
          <h2 className="af-h2 mb-2">3. 現場照片（選填）</h2>
          <input ref={fileInput} type="file" accept="image/*" capture="environment" multiple className="hidden" onChange={(e) => setFiles([...files, ...Array.from(e.target.files || [])].slice(0, 5))} />
          <div className="flex flex-wrap gap-2">
            {previews.map((p, i) => (
              <div key={p.url} className="relative h-20 w-20 overflow-hidden rounded border" style={{ borderColor: "var(--line)" }}>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={p.url} alt={p.name} className="h-full w-full object-cover" />
                <button type="button" className="absolute right-0.5 top-0.5 rounded bg-black/60 px-1 text-[10px] text-white" onClick={() => setFiles(files.filter((_, j) => j !== i))} aria-label="移除照片">
                  ✕
                </button>
              </div>
            ))}
            {files.length < 5 ? (
              <button type="button" className="flex h-20 w-20 flex-col items-center justify-center rounded border border-dashed text-xs text-[var(--muted)]" style={{ borderColor: "var(--line-2)" }} onClick={() => fileInput.current?.click()}>
                <span className="text-lg leading-none">＋</span>
                拍照／上傳
              </button>
            ) : null}
          </div>
          <div className="mt-1 text-[11px] text-[var(--faint)]">最多 5 張，每張 8 MB 以內。照片會公開顯示於案件頁，請避免拍到人臉與車牌。</div>
        </section>

        {/* 4. description */}
        <section className="af-panel mb-3 p-4">
          <h2 className="af-h2 mb-2">4. 簡單描述（選填）</h2>
          <textarea className="af-input" placeholder="例如：路基掏空約 30 公尺，車輛無法通行，仍有落石" value={description} onChange={(e) => setDescription(e.target.value)} maxLength={2000} />
        </section>

        {/* 5. who */}
        <section className="af-panel mb-3 p-4">
          <h2 className="af-h2 mb-2">5. 我是</h2>
          <div className="flex flex-wrap gap-2">
            {(platform?.reporter_roles || []).map((r) => (
              <button key={r.key} type="button" onClick={() => setRole(r.key)} className={`af-chip !px-3 !py-1.5 !text-xs ${role === r.key ? "af-chip-on" : ""}`} aria-pressed={role === r.key}>
                {r.label}
              </button>
            ))}
          </div>
          <button type="button" className="mt-3 text-xs text-[var(--focus)] hover:underline" onClick={() => setContactOpen((v) => !v)}>
            {contactOpen ? "收合" : "留下聯絡方式（選填，僅供處理單位聯繫，不公開）"}
          </button>
          {contactOpen ? (
            <div className="mt-2 grid gap-2 sm:grid-cols-2">
              <input className="af-input" placeholder="稱呼" value={name} onChange={(e) => setName(e.target.value)} maxLength={100} />
              <input className="af-input" placeholder="電話" inputMode="tel" value={contact} onChange={(e) => setContact(e.target.value)} maxLength={100} />
            </div>
          ) : null}
        </section>

        <div className="fixed inset-x-0 bottom-0 z-10 border-t bg-[var(--bg)]/95 px-3 py-3 backdrop-blur sm:static sm:border-0 sm:bg-transparent sm:px-0" style={{ borderColor: "var(--line)" }}>
          <button type="button" className="af-btn af-btn-primary af-btn-lg w-full" disabled={!canSubmit} onClick={submit}>
            {submitting ? (
              <>
                <span className="af-spinner" /> 送出中…
              </>
            ) : category ? (
              `送出通報：${platform?.report_categories.find((c) => c.key === category)?.label ?? ""}`
            ) : (
              "請先選擇災情類別"
            )}
          </button>
        </div>
      </div>
    </PortalShell>
  );
}
