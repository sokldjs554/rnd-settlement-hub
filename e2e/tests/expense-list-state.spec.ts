/**
 * 목록 화면 상태 유지 회귀 테스트.
 *
 * 페이지·필터·정렬을 컴포넌트 useState에 두면, 상세 화면에 다녀올 때 목록이
 * 새로 마운트되면서 1페이지로 돌아간다("2페이지에서 한 건 보고 뒤로가기 →
 * 1페이지"). URL을 단일 출처로 삼아 고쳤고, 이 테스트가 그 계약을 잠근다.
 */

import { expect, type Page, test } from "@playwright/test";

const PASSWORD = "demo1234!";
const PAGE_SIZE = 20;

async function login(page: Page, email: string) {
  await page.goto("/login");
  await page.getByLabel("이메일").fill(email);
  await page.getByLabel("비밀번호").fill(PASSWORD);
  await page.getByRole("button", { name: "로그인" }).click();
  await expect(page.getByRole("button", { name: "로그아웃" })).toBeVisible();
}

/** 2페이지가 생기도록 작성 중(DRAFT) 건을 API로 채운다 — 검증 파이프라인을 타지 않아 빠르다. */
async function seedEnoughRowsForTwoPages(page: Page) {
  const auth = await page.request.post("/api/v1/auth/login", {
    data: { email: "researcher@demo.kr", password: PASSWORD },
  });
  const token = ((await auth.json()) as { access_token: string }).access_token;
  const headers = { Authorization: `Bearer ${token}` };

  const listed = await page.request.get("/api/v1/expenses?page=1&size=1", { headers });
  const existing = ((await listed.json()) as { total: number }).total;

  const projects = await page.request.get("/api/v1/projects", { headers });
  const projectId = ((await projects.json()) as { id: number }[])[0].id;

  for (let i = existing; i <= PAGE_SIZE; i++) {
    const res = await page.request.post("/api/v1/expenses", {
      headers,
      data: {
        project_id: projectId,
        category: "MATERIAL",
        title: `목록 상태 유지 확인 ${String(i).padStart(2, "0")}`,
        vendor_name: `테스트상사${String(i).padStart(2, "0")}`,
        purpose: "목록 페이지 유지 회귀 테스트용",
        amount: 100000 + i,
        spent_at: "2026-05-01",
      },
    });
    expect(res.ok()).toBeTruthy();
  }
}

test("2페이지에서 상세로 들어갔다 뒤로가기 하면 2페이지가 유지된다", async ({
  page,
}) => {
  await login(page, "manager@demo.kr");
  await seedEnoughRowsForTwoPages(page);

  await page.goto("/expenses");
  await page.getByRole("button", { name: "다음" }).click();

  // 페이지 번호가 URL에 실려야 뒤로가기가 복원할 수 있다
  await expect(page).toHaveURL(/[?&]page=2\b/);
  const secondPageTop = await page
    .locator("tbody tr")
    .first()
    .locator("a")
    .innerText();

  await page.locator("tbody tr").first().click();
  await expect(page).toHaveURL(/\/expenses\/\d+$/);

  await page.goBack();
  await expect(page).toHaveURL(/[?&]page=2\b/);
  await expect(page.locator("tbody tr").first().locator("a")).toHaveText(
    secondPageTop,
  );
});

test("필터를 바꾸면 URL에 반영되고 페이지는 1로 돌아간다", async ({ page }) => {
  await login(page, "manager@demo.kr");
  await seedEnoughRowsForTwoPages(page);

  await page.goto("/expenses?page=2");
  await page.selectOption('[aria-label="상태 필터"]', "NEEDS_REVIEW");

  await expect(page).toHaveURL(/status=NEEDS_REVIEW/);
  // 조건이 바뀌면 이전 페이지 번호는 의미가 없으므로 URL에서 사라진다
  await expect(page).not.toHaveURL(/[?&]page=/);
});
