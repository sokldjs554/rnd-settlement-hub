import type { NextConfig } from "next";

/**
 * 브라우저는 언제나 프론트엔드와 **같은 오리진**의 `/api/v1`을 호출하고,
 * Next.js 서버가 백엔드로 프록시한다. 이렇게 한 이유:
 *
 * - 배포 환경마다 다른 API 주소를 브라우저 번들에 빌드 타임으로 박지 않아도 된다.
 *   (Codespaces·프리뷰 URL처럼 주소가 매번 바뀌는 환경에서 특히 중요)
 * - 같은 오리진이므로 CORS 설정이 필요 없고, refresh 토큰 쿠키의 SameSite 제약도 걸리지 않는다.
 *
 * API_ORIGIN은 서버 전용 환경변수다(NEXT_PUBLIC_ 아님) — 브라우저에 노출되지 않는다.
 */
const API_ORIGIN = process.env.API_ORIGIN ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  // 내부 업무 시스템 SPA — 이미지 최적화 서버 불필요(배포 단순화)
  images: { unoptimized: true },
  async rewrites() {
    return [{ source: "/api/v1/:path*", destination: `${API_ORIGIN}/api/v1/:path*` }];
  },
};

export default nextConfig;
