/** @type {import('next').NextConfig} */
const nextConfig = {
  // standalone is for the Docker image; the Cloudflare (OpenNext) build
  // requires the default output, so it is opt-in via env.
  output: process.env.NEXT_OUTPUT === "standalone" ? "standalone" : undefined,
  reactStrictMode: true,
};

module.exports = nextConfig;
