// Pings TARGET_URL on a cron schedule to keep the free backend instance warm.
export default {
  async scheduled(_event, env, _ctx) {
    try {
      const res = await fetch(env.TARGET_URL, { signal: AbortSignal.timeout(30000) });
      console.log(`keepwarm ${env.TARGET_URL} -> ${res.status}`);
    } catch (err) {
      console.log(`keepwarm failed: ${err}`);
    }
  },
  // manual check: opening the worker URL also triggers a ping
  async fetch(_req, env) {
    const res = await fetch(env.TARGET_URL).catch(() => null);
    return new Response(`target=${env.TARGET_URL} status=${res ? res.status : "error"}`);
  },
};
