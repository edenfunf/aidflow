"use client";

// Who is signed in, and what they may do. One cached /v1/auth/me call shared by
// every console component; permissions mirror app/domain/permissions.py and
// only decide what the UI offers — the API enforces them regardless.

import { useEffect, useState } from "react";
import { api, getToken, setToken } from "./api";
import type { Me, Permission } from "./types";

type Listener = (me: Me | null) => void;

let cached: Me | null = null;
let inflight: Promise<Me | null> | null = null;
const listeners = new Set<Listener>();

function publish(me: Me | null) {
  cached = me;
  listeners.forEach((l) => l(me));
}

export function loadMe(force = false): Promise<Me | null> {
  if (cached && !force) return Promise.resolve(cached);
  if (inflight && !force) return inflight;
  inflight = api
    .me()
    .then((m) => {
      publish(m);
      return m;
    })
    .catch(() => {
      publish(null);
      return null;
    })
    .finally(() => {
      inflight = null;
    });
  return inflight;
}

export function setSession(token: string, me: Me) {
  setToken(token);
  publish(me);
}

export async function signOut(reason?: "idle" | "expired") {
  try {
    if (getToken()) await api.logout();
  } catch {
    /* already invalid */
  }
  setToken("");
  publish(null);
  if (typeof window !== "undefined") {
    window.location.assign(`/login${reason ? `?reason=${reason}` : ""}`);
  }
}

export function useMe() {
  const [me, setMe] = useState<Me | null>(cached);
  const [loading, setLoading] = useState(!cached);
  useEffect(() => {
    const l: Listener = (m) => {
      setMe(m);
      setLoading(false);
    };
    listeners.add(l);
    loadMe().then(l);
    return () => {
      listeners.delete(l);
    };
  }, []);
  const can = (p: Permission) => Boolean(me?.permissions.includes(p));
  return { me, loading, can };
}

/** Sign out after this long without keyboard / mouse / touch activity. */
export const IDLE_TIMEOUT_MS = 30 * 60 * 1000;
