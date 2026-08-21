/**
 * 샘플 증빙 HTML → PNG 렌더러.
 *   cd e2e && node ../docs/samples/render.mjs
 * Playwright는 e2e 디렉터리에만 설치되어 있으므로 실행 위치 기준으로 불러온다.
 */
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import path from "node:path";

const require = createRequire(path.join(process.cwd(), "package.json"));
const { chromium } = require("@playwright/test");

const here = path.dirname(fileURLToPath(import.meta.url));
// 컨테이너에 사전 설치된 크로미움 경로를 쓸 수 있게 열어 둔다
const executablePath = process.env.PW_EXECUTABLE_PATH || undefined;
const browser = await chromium.launch({ executablePath });
const page = await browser.newPage({ deviceScaleFactor: 2 });
await page.goto("file://" + path.join(here, "card-receipt.html"));
await page.locator(".slip").screenshot({ path: path.join(here, "card-receipt.png") });
await browser.close();
console.log("card-receipt.png 생성 완료");
