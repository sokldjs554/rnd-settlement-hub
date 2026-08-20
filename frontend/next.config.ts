import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // 내부 업무 시스템 SPA — 이미지 최적화 서버 불필요(배포 단순화)
  images: { unoptimized: true },
};

export default nextConfig;
