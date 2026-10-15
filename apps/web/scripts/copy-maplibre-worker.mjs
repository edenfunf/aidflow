// maplibre-gl v6 spawns its worker from a bundler-resolved URL, which Next's
// webpack build does not emit correctly (the map then renders no basemap at
// all: "Worker failed to load"). Serving the worker ourselves from /public and
// pointing setWorkerUrl at it (lib/mapStyle.ts) is the supported escape hatch.
// Runs automatically via the "prebuild" script, so it cannot drift from the
// installed maplibre version.
import { copyFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const src = join(here, "..", "node_modules", "maplibre-gl", "dist", "maplibre-gl-worker.mjs");
const dest = join(here, "..", "public", "maplibre-gl-worker.js");

mkdirSync(dirname(dest), { recursive: true });
copyFileSync(src, dest);
console.log("copied maplibre worker →", dest);
