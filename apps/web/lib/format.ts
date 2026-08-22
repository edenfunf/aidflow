export function fmtTime(iso?: string | null, withDate = true): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleString("zh-TW", {
      hour12: false,
      ...(withDate ? { month: "2-digit", day: "2-digit" } : {}),
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export function fmtClock(iso?: string | null): string {
  return fmtTime(iso, false);
}

export function fmtAgo(iso?: string | null, now: number = Date.now()): string {
  if (!iso) return "—";
  const diff = Math.max(0, Math.round((now - new Date(iso).getTime()) / 60000));
  if (diff < 1) return "剛剛";
  if (diff < 60) return `${diff} 分鐘前`;
  if (diff < 1440) return `${Math.round(diff / 60)} 小時前`;
  return `${Math.round(diff / 1440)} 天前`;
}

export function fmtDuration(minutes?: number | null): string {
  if (minutes === null || minutes === undefined) return "—";
  if (minutes < 60) return `${Math.round(minutes)} 分鐘`;
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  return m ? `${h} 小時 ${m} 分` : `${h} 小時`;
}

export function fmtNum(n?: number | null): string {
  if (n === null || n === undefined) return "—";
  return n.toLocaleString("zh-TW");
}

export function fmtMeters(m?: number | null): string {
  if (m === null || m === undefined) return "—";
  return m >= 1000 ? `${(m / 1000).toFixed(1)} 公里` : `${Math.round(m)} 公尺`;
}
