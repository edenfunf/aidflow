"use client";

import { api } from "@/lib/api";
import { fmtTime } from "@/lib/format";
import type { PhotoItem } from "@/lib/types";

const KIND_LABEL: Record<PhotoItem["kind"], string> = { before: "處理前", scene: "現場", after: "處理後" };
const SOURCE_LABEL: Record<PhotoItem["source"], string> = { citizen: "民眾提供", agency: "處理單位提供" };

export default function PhotoStrip({ photos, emptyText = "尚無現場照片" }: { photos: PhotoItem[]; emptyText?: string }) {
  if (!photos.length) {
    return (
      <div className="af-subtle flex h-24 items-center justify-center text-xs text-[var(--muted)]">{emptyText}</div>
    );
  }
  const order: PhotoItem["kind"][] = ["before", "scene", "after"];
  const sorted = [...photos].sort((a, b) => order.indexOf(a.kind) - order.indexOf(b.kind) || a.created_at.localeCompare(b.created_at));
  return (
    <div className="flex gap-2 overflow-x-auto pb-1">
      {sorted.map((p) => (
        <figure key={p.id} className="w-40 flex-none">
          <a href={api.mediaUrl(p.url)} target="_blank" rel="noreferrer" className="block overflow-hidden rounded border" style={{ borderColor: "var(--line)" }}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={api.mediaUrl(p.url)} alt={p.caption || KIND_LABEL[p.kind]} className="h-28 w-full object-cover" loading="lazy" />
          </a>
          <figcaption className="mt-1 text-[10.5px] leading-snug text-[var(--muted)]">
            <span className="font-medium text-[var(--ink-2)]">{KIND_LABEL[p.kind]}</span> · {SOURCE_LABEL[p.source]}
            <br />
            {fmtTime(p.created_at)}
            {p.caption ? <span className="block truncate">{p.caption}</span> : null}
          </figcaption>
        </figure>
      ))}
    </div>
  );
}
