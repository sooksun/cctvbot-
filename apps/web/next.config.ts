import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Browser calls API via NEXT_PUBLIC_API_URL (default http://localhost:8000).
  // CORS is configured on the FastAPI side for http://localhost:3000.
};

export default nextConfig;
