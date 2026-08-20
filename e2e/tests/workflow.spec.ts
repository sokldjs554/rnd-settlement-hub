/**
 * 핵심 워크플로 E2E:
 * 연구원 로그인 → 집행 등록(증빙 업로드) → 자동 검증 파이프라인(워커 실제 실행)
 * → 담당자 로그인 → 검증 결과 확인 → 승인 → 월별 보고서 생성 → 대시보드 반영 확인
 *
 * AI는 키 없이 성능 저하 모드(NullAIClient)로 동작한다 — "AI가 죽어도 워크플로는
 * 완주한다"는 설계 자체가 이 테스트의 검증 대상이기도 하다.
 */

import { expect, type Page, test } from "@playwright/test";
import path from "path";

const PASSWORD = "demo1234!";

async function login(page: Page, email: string) {
  await page.goto("/login");
  await page.getByLabel("이메일").fill(email);
  await page.getByLabel("비밀번호").fill(PASSWORD);
  await page.getByRole("button", { name: "로그인" }).click();
  await expect(page.getByRole("button", { name: "로그아웃" })).toBeVisible();
}

async function logout(page: Page) {
  await page.getByRole("button", { name: "로그아웃" }).click();
  await expect(page.getByRole("button", { name: "로그인" })).toBeVisible();
}

test("집행 등록부터 보고서·대시보드까지 전 과정이 동작한다", async ({ page }) => {
  // ── 1) 연구원: 집행 등록 + 증빙 + 제출 ──
  await login(page, "researcher@demo.kr");
  await page.goto("/expenses/new");
  await page.getByLabel("과제").selectOption({ index: 1 });
  await page.getByLabel(/^비목/).selectOption("MATERIAL");
  await page.getByLabel("제목").fill("E2E 시약 구입");
  await page.getByLabel("거래처명").fill("이투이상사");
  await page.getByLabel("사업자등록번호").fill("123-45-67891");
  await page.getByLabel("금액(원)").fill("450000");
  await page.getByLabel("집행일").fill("2026-04-07");
  await page
    .getByLabel(/증빙 파일/)
    .setInputFiles(path.join(__dirname, "..", "fixtures", "tax_invoice.pdf"));
  await page.getByRole("button", { name: "등록하고 제출" }).click();

  // 상세 페이지로 이동됨
  await expect(page.getByRole("heading", { name: "E2E 시약 구입" })).toBeVisible({
    timeout: 20_000,
  });

  // ── 2) 워커가 파이프라인을 실제로 처리 → 검토 대기 (UI 5초 폴링 자동 갱신) ──
  await expect(page.getByText("검토 대기").first()).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText(/자동 검증 결과/)).toBeVisible();
  // AI 미사용 모드 플래그(R-AI-001)와 사업자 미확인(R-VND-003)이 남아야 한다
  await expect(page.getByText("R-AI-001")).toBeVisible();
  await expect(page.getByText("R-VND-003")).toBeVisible();
  const detailUrl = page.url();
  await logout(page);

  // ── 3) 담당자: 검토·승인 ──
  await login(page, "manager@demo.kr");
  await page.goto(detailUrl);
  await expect(page.getByText("입력값 ↔ AI 추출값 대조")).toBeVisible();
  await page.getByRole("button", { name: "승인", exact: true }).click();
  await page.getByRole("button", { name: "확인" }).click();
  await expect(page.getByText("승인").first()).toBeVisible();
  await expect(page.getByRole("button", { name: "반려" })).toHaveCount(0);

  // ── 4) 월별 정산보고서 생성 ──
  await page.goto("/reports");
  await page.getByRole("button", { name: "월별 보고서 생성" }).click();
  await page.getByLabel("과제").selectOption({ index: 1 });
  await page.getByLabel("월").selectOption("4");
  await page.getByRole("button", { name: "생성", exact: true }).click();
  await expect(page.getByRole("heading", { name: /2026년 4월 정산보고서/ })).toBeVisible({
    timeout: 20_000,
  });
  // 집계표(SQL 스냅샷)에 방금 승인한 금액이 반영됐다
  await expect(page.getByText("SQL 스냅샷", { exact: false })).toBeVisible();
  await expect(page.getByText("450,000원").first()).toBeVisible();

  // ── 5) 대시보드 반영 ──
  await page.goto("/");
  await expect(page.getByText("비목별 예산 소진")).toBeVisible();
  await expect(page.getByText("AI 비목 제안 채택률")).toBeVisible();
});
