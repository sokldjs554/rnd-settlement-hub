/**
 * README용 스크린샷 캡처 — 실제 앱을 구동한 상태에서 실행한다.
 *
 *   (Codespace, docker compose up + seed --demo 완료, ANTHROPIC_API_KEY 설정 상태에서)
 *   cd e2e && npm ci && node capture.mjs
 *
 * 데모 증빙(docs/samples/card-receipt.png)으로 집행 건 2개를 실제로 등록한다:
 *   ① 증빙과 값이 전부 일치하는 기준선 → 승인까지
 *   ② 금액만 다르게 입력해 R-EVD-002 위반을 유도
 * 그 후 상세·보고서·대시보드를 docs/images/*.png 로 저장한다.
 *
 * 주의: 실행할 때마다 집행 건이 새로 생기므로, 깨끗한 스크린샷을 원하면
 * `docker compose down -v && docker compose up -d --build && ... seed --demo` 후 1회만 실행.
 */
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import path from "node:path";

const require = createRequire(path.join(process.cwd(), "package.json"));
const { chromium } = require("@playwright/test");

const BASE = process.env.BASE_URL || "http://localhost:3000";
const here = path.dirname(fileURLToPath(import.meta.url));
const outDir = path.join(here, "..", "docs", "images");
const receipt = path.join(here, "..", "docs", "samples", "card-receipt.png");
const PASSWORD = "demo1234!";

const browser = await chromium.launch({ executablePath: process.env.PW_EXECUTABLE_PATH || undefined });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
const shot = (name, opts = {}) => page.screenshot({ path: path.join(outDir, name), ...opts });

async function login(email) {
  await page.goto(`${BASE}/login`);
  await page.getByLabel("이메일").fill(email);
  await page.getByLabel("비밀번호").fill(PASSWORD);
  await page.getByRole("button", { name: "로그인" }).click();
  await page.getByRole("button", { name: "로그아웃" }).waitFor();
}
async function logout() {
  await page.getByRole("button", { name: "로그아웃" }).click();
  await page.getByRole("button", { name: "로그인" }).waitFor();
}

// 집행 등록 → 제출 → 검증 완료(검토 대기)까지 기다리고 상세 URL을 반환
async function registerExpense({ title, amount }) {
  await page.goto(`${BASE}/expenses/new`);
  await page.getByLabel("과제").selectOption({ index: 1 });
  await page.getByLabel(/^비목/).selectOption("MATERIAL");
  await page.getByLabel("제목").fill(title);
  await page.getByLabel("사용 용도").fill("인지 모듈 성능시험용 시약 — 연구 수행에 직접 사용");
  await page.getByLabel("거래처명").fill("(주)한빛사이언스");
  await page.getByLabel("사업자등록번호").fill("101-81-16293");
  await page.getByLabel("금액(원)").fill(String(amount));
  await page.getByLabel("집행일").fill("2026-08-20");
  await page.getByLabel(/증빙 파일/).setInputFiles(receipt);
  await page.getByRole("button", { name: "등록하고 제출" }).click();
  await page.getByRole("heading", { name: title }).waitFor({ timeout: 20_000 });
  // 워커의 AI 추출 + 룰 검증이 끝나면 UI가 자동 갱신된다
  await page.getByText("검토 대기").first().waitFor({ timeout: 120_000 });
  await page.getByText("입력값 ↔ AI 추출값 대조").waitFor();
  return page.url();
}

console.log("① 연구원: 기준선(증빙 일치) 건 등록…");
await login("researcher@demo.kr");
const passUrl = await registerExpense({ title: "실험용 시약 및 소모품 구입", amount: 1320000 });
await shot("expense-pass.png", { fullPage: true });
console.log("   expense-pass.png 저장");

console.log("② 연구원: 금액 불일치 건 등록…");
const failUrl = await registerExpense({ title: "시약 구입(금액 불일치 예시)", amount: 1100000 });
await shot("expense-fail.png", { fullPage: true });
console.log("   expense-fail.png 저장");
await logout();

console.log("③ 담당자: 기준선 건 승인…");
await login("manager@demo.kr");
await page.goto(passUrl);
await page.getByRole("button", { name: "승인", exact: true }).click();
await page.getByRole("button", { name: "확인" }).click();
await page.getByText("승인").first().waitFor();

console.log("④ 월별 보고서 생성…");
await page.goto(`${BASE}/reports`);
await page.getByRole("button", { name: "월별 보고서 생성" }).click();
await page.getByLabel("과제").selectOption({ index: 1 });
await page.getByLabel("월").selectOption("8");
await page.getByRole("button", { name: "생성", exact: true }).click();
await page.getByRole("heading", { name: /2026년 8월 정산보고서/ }).waitFor({ timeout: 30_000 });
await shot("report.png", { fullPage: true });
console.log("   report.png 저장");

console.log("⑤ 대시보드…");
await page.goto(`${BASE}/`);
await page.getByText("비목별 예산 소진").waitFor();
await page.getByText("AI 비목 제안 채택률").waitFor();
await page.waitForTimeout(1500); // 차트 애니메이션 안정화
await shot("dashboard.png");
console.log("   dashboard.png 저장");

await browser.close();
console.log(`완료 — ${outDir} 에 4장 저장. git add docs/images && commit && push 하세요.`);
