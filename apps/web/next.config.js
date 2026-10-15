/** @type {import('next').NextConfig} */

// Only the embeddable map may be framed, and only by the sites listed in
// EMBED_ALLOWED_ORIGINS (space- or comma-separated, e.g.
// "https://www.nantou.gov.tw https://*.nantou.gov.tw"). Every other page
// refuses to be framed (clickjacking protection). Read at build time.
const embedOrigins = (process.env.EMBED_ALLOWED_ORIGINS || "")
  .split(/[\s,]+/)
  .map((s) => s.trim())
  .filter(Boolean);

const common = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(self), geolocation=(self), microphone=()" },
];

const nextConfig = {
  // standalone is for the Docker image; the Cloudflare (OpenNext) build
  // requires the default output, so it is opt-in via env.
  output: process.env.NEXT_OUTPUT === "standalone" ? "standalone" : undefined,
  reactStrictMode: true,
  async headers() {
    return [
      {
        source: "/embed/:path*",
        headers: [...common, { key: "Content-Security-Policy", value: `frame-ancestors 'self' ${embedOrigins.join(" ")}`.trim() }],
      },
      {
        // everything except /embed
        source: "/((?!embed/).*)",
        headers: [...common, { key: "X-Frame-Options", value: "SAMEORIGIN" }, { key: "Content-Security-Policy", value: "frame-ancestors 'self'" }],
      },
    ];
  },
};

module.exports = nextConfig;
