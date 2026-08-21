import { defineConfig } from "@playwright/test";

/**
 * E2E 설정. 서비스 기동/정리는 run.sh가 담당한다 (DB 준비 → api·worker·frontend 실행).
 * PW_EXECUTABLE_PATH: 시스템에 미리 설치된 Chromium을 쓸 때 지정 (예: /opt/pw-browsers/chromium)
 */
export default defineConfig({
  testDir: "./tests",
  timeout: 90_000,
  expect: { timeout: 15_000 },
  retries: 0,
  workers: 1, // 워크플로 시나리오는 상태를 공유하므로 직렬 실행
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    ...(process.env.PW_EXECUTABLE_PATH
      ? { launchOptions: { executablePath: process.env.PW_EXECUTABLE_PATH } }
      : {}),
  },
});
