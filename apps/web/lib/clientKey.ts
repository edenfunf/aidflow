// A stable, anonymous per-device key. The backend hashes it (salted) to count
// distinct reporters; the raw value never leaves the browser except in the
// submit request and is never shown to anyone.
const STORAGE_KEY = "aidflow.clientKey";

export function getClientKey(): string | null {
  if (typeof window === "undefined") return null;
  try {
    let key = window.localStorage.getItem(STORAGE_KEY);
    if (!key) {
      const bytes = new Uint8Array(16);
      window.crypto.getRandomValues(bytes);
      key = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
      window.localStorage.setItem(STORAGE_KEY, key);
    }
    return key;
  } catch {
    return null;
  }
}
