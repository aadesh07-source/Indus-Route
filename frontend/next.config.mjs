/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    // Proxy API calls to the FastAPI backend — no CORS pain in dev.
    const backend = process.env.BACKEND_URL || "http://127.0.0.1:8000";
    return [{ source: "/api/:path*", destination: backend + "/:path*" }];
  },
};

export default nextConfig;
