import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Emit a self-contained server (.next/standalone) for a slim Docker runner.
  output: "standalone",
  // Browser calls API via NEXT_PUBLIC_API_URL (default http://localhost:8000).
  // CORS is configured on the FastAPI side for http://localhost:3000.
};

export default nextConfig;
