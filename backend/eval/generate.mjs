/**
 * AI 추출 정확도 벤치마크용 합성 영수증 생성기.
 *
 *   cd e2e && PW_EXECUTABLE_PATH=... node ../backend/eval/generate.mjs
 *
 * backend/eval/receipts/*.png|jpg 25장과 정답 라벨(labels.json)을 만든다.
 * 고정 시드 PRNG를 쓰므로 다시 실행해도 같은 세트가 나온다(벤치마크 재현성).
 * 난이도 3단계: easy(선명) / medium(회전·저품질 JPEG) / hard(흐림·저대비·필드 누락).
 * 필드가 문서에 아예 없는 경우 정답도 null이다 — "없으면 null"을 지키는지도 채점 대상.
 */
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import fs from "node:fs";
import path from "node:path";

const require = createRequire(path.join(process.cwd(), "package.json"));
const { chromium } = require("@playwright/test");

const here = path.dirname(fileURLToPath(import.meta.url));
const outDir = path.join(here, "receipts");

// ── 고정 시드 PRNG (mulberry32) ──
let seed = 20260821;
function rand() {
  seed |= 0; seed = (seed + 0x6d2b79f5) | 0;
  let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
  t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
}
const pick = (arr) => arr[Math.floor(rand() * arr.length)];
const randint = (lo, hi) => lo + Math.floor(rand() * (hi - lo + 1));

// 사업자번호 체크섬 (국세청 알고리즘) — 유효한 번호만 생성한다
function makeBizNo() {
  const d = Array.from({ length: 9 }, () => randint(0, 9));
  const w = [1, 3, 7, 1, 3, 7, 1, 3, 5];
  let t = d.reduce((s, x, i) => s + x * w[i], 0) + Math.floor((d[8] * 5) / 10);
  return d.join("") + ((10 - (t % 10)) % 10);
}
const hy = (b) => `${b.slice(0, 3)}-${b.slice(3, 5)}-${b.slice(5)}`;

const VENDORS = [
  "(주)가온바이오", "한솔계측기기", "(주)미르광학", "누리소재상사", "(주)새빛전자부품",
  "정도화학", "(주)이룸테크", "다온시약", "(주)해성정밀", "온새미로컴퍼니",
  "(주)푸른融合소재", "빛가람기기", "(주)한결머티리얼", "세움과학", "(주)도담로보틱스",
];
const ITEMS = [
  "실험용 시약 세트", "정밀 저울 교정", "PCR 튜브 및 소모품", "산업용 카메라 렌즈",
  "알루미늄 프로파일", "고순도 에탄올", "서보모터 부품", "전자부품 일괄", "광학 필터",
  "시험용 배지", "케이블 하네스", "센서 모듈", "3D프린터 필라멘트", "볼트·너트류", "리튬 배터리 셀",
];
const fmt = (n) => n.toLocaleString("ko-KR");
const dateStr = () => `2026-0${randint(1, 8)}-${String(randint(1, 28)).padStart(2, "0")}`;

// ── 문서 템플릿 3종 ──
function cardSlip(v) {
  return `
  <div class="doc slip">
    <h1>신용카드 매출전표</h1><div class="sub">고객용</div><hr>
    <div class="row"><span>가맹점명</span><span>${v.vendor}</span></div>
    <div class="row"><span>사업자번호</span><span>${hy(v.biz)}</span></div>
    <div class="row"><span>대표자</span><span>${pick(["김민준", "이서연", "박도윤", "최지우"])}</span></div><hr>
    <div class="row"><span>거래일시</span><span>${v.date} ${randint(9, 18)}:${String(randint(0, 59)).padStart(2, "0")}</span></div>
    <div class="row"><span>카드번호</span><span>${randint(4000, 5599)}-****-****-${randint(1000, 9999)}</span></div>
    <div class="row"><span>승인번호</span><span>${randint(10000000, 99999999)}</span></div><hr>
    <div class="row"><span>품명</span><span>${v.item}</span></div><hr>
    <div class="row"><span>공급가액</span><span>${fmt(v.supply)}원</span></div>
    <div class="row"><span>부가세</span><span>${fmt(v.vat)}원</span></div>
    ${v.noTotal ? "" : `<div class="row total"><span>합계</span><span>${fmt(v.total)}원</span></div>`}
  </div>`;
}
function taxInvoice(v) {
  return `
  <div class="doc invoice">
    <h1>세 금 계 산 서</h1>
    <table>
      <tr><th>등록번호</th><td>${hy(v.biz)}</td><th>작성일자</th><td>${v.date}</td></tr>
      <tr><th>상호</th><td>${v.vendor}</td><th>품목</th><td>${v.item}</td></tr>
      <tr><th>공급가액</th><td>${fmt(v.supply)}</td><th>세액</th><td>${fmt(v.vat)}</td></tr>
      <tr class="total"><th>합계금액</th><td colspan="3">${v.noTotal ? "" : `₩${fmt(v.total)}`}</td></tr>
    </table>
    <div class="foot">공급받는자 보관용 · 전자세금계산서</div>
  </div>`;
}
function simpleReceipt(v) {
  return `
  <div class="doc simple">
    <h1>영 수 증</h1>
    <p class="line">No. ${randint(1, 99)}  &nbsp; ${v.date}</p>
    <p class="line">공급자: ${v.vendor} ${v.noBiz ? "" : `(${hy(v.biz)})`}</p>
    <p class="line">내역: ${v.item}</p>
    <p class="line big">금액: ${v.noTotal ? "" : `${fmt(v.total)}원 (부가세 포함)`}</p>
    <p class="line">위 금액을 정히 영수함.</p>
  </div>`;
}

const CSS = `
  body { margin:0; background:#ddd; font-family:"WenQuanYi Zen Hei",sans-serif; }
  .wrap { width:420px; padding:16px; }
  .doc { background:#fff; color:#111; padding:20px 22px; font-size:13px; line-height:1.7;
         box-shadow:0 1px 6px rgba(0,0,0,.25); position:relative; }
  h1 { font-size:16px; text-align:center; letter-spacing:3px; margin:0 0 6px; }
  .sub { text-align:center; font-size:11px; color:#666; }
  hr { border:0; border-top:1px dashed #999; margin:8px 0; }
  .row { display:flex; justify-content:space-between; }
  .total { font-weight:bold; font-size:15px; }
  table { width:100%; border-collapse:collapse; font-size:12px; }
  th,td { border:1px solid #b33; padding:5px 7px; text-align:left; }
  th { color:#b33; background:#fdf3f3; width:72px; }
  .invoice h1 { color:#b33; }
  .simple .line { margin:6px 0; border-bottom:1px dotted #aaa; padding-bottom:4px; }
  .simple .big { font-size:15px; font-weight:bold; }
  .foot { font-size:10px; color:#888; margin-top:8px; text-align:center; }
  .stamp { position:absolute; right:26px; bottom:34px; width:64px; height:64px;
           border:3px solid rgba(200,30,30,.65); border-radius:50%; color:rgba(200,30,30,.65);
           display:flex; align-items:center; justify-content:center; font-size:13px;
           font-weight:bold; transform:rotate(-14deg); background:rgba(255,255,255,.15); }
`;

const TEMPLATES = { card: cardSlip, invoice: taxInvoice, simple: simpleReceipt };

// 25장 계획: easy 10 / medium 8 / hard 7
const plan = [];
for (let i = 0; i < 10; i++) plan.push({ tier: "easy" });
for (let i = 0; i < 8; i++) plan.push({ tier: "medium" });
for (let i = 0; i < 7; i++) plan.push({ tier: "hard" });

fs.rmSync(outDir, { recursive: true, force: true });
fs.mkdirSync(outDir, { recursive: true });

const browser = await chromium.launch({ executablePath: process.env.PW_EXECUTABLE_PATH || undefined });
const labels = [];

for (let i = 0; i < plan.length; i++) {
  const tier = plan[i].tier;
  const type = pick(["card", "invoice", "simple"]);
  const supply = randint(3, 480) * 10000;
  const vat = Math.floor(supply / 10);
  const v = {
    vendor: pick(VENDORS), biz: makeBizNo(), date: dateStr(), item: pick(ITEMS),
    supply, vat, total: supply + vat,
    // hard에서만 일부 필드를 문서에서 통째로 뺀다 → 정답 null
    noTotal: tier === "hard" && rand() < 0.35,
    noBiz: false,
  };
  if (type === "simple" && tier === "hard" && rand() < 0.5) v.noBiz = true;

  // 난이도별 화질 열화 (CSS filter/transform)
  let filter = "none", rotate = 0, width = 420, stamp = "";
  if (tier === "medium") {
    filter = `contrast(${0.75 + rand() * 0.1}) brightness(1.05)`;
    rotate = (rand() - 0.5) * 5;
  } else if (tier === "hard") {
    filter = `blur(${(0.8 + rand() * 0.8).toFixed(2)}px) contrast(${0.55 + rand() * 0.1})`;
    rotate = (rand() - 0.5) * 11;
    width = 340;
    if (rand() < 0.4) stamp = `<div class="stamp">확인필</div>`;
  }

  const html = `<!doctype html><meta charset="utf-8"><style>${CSS}
    .doc { filter:${filter}; transform:rotate(${rotate.toFixed(2)}deg); }</style>
    <div class="wrap" style="width:${width}px">${TEMPLATES[type](v)}</div>`;
  const page = await browser.newPage({ deviceScaleFactor: tier === "hard" ? 1 : 2 });
  await page.setContent(html);
  // 도장은 .doc 내부에 넣어야 문서와 함께 기울어진다
  if (stamp) await page.evaluate((s) => { document.querySelector(".doc").insertAdjacentHTML("beforeend", s); }, stamp);

  const ext = tier === "easy" ? "png" : "jpg";
  const file = `r${String(i + 1).padStart(2, "0")}_${tier}_${type}.${ext}`;
  const shot = { path: path.join(outDir, file) };
  if (ext === "jpg") { shot.type = "jpeg"; shot.quality = tier === "hard" ? 30 : 45; }
  await page.locator(".wrap").screenshot(shot);
  await page.close();

  labels.push({
    file,
    tier,
    doc_type: type,
    vendor_name: v.vendor,
    biz_no: v.noBiz ? null : v.biz,
    total_amount: v.noTotal ? null : v.total,
    issued_at: v.date,
  });
  console.log(`${file} 생성`);
}

await browser.close();
fs.writeFileSync(path.join(here, "labels.json"), JSON.stringify(labels, null, 2) + "\n");
console.log(`완료: ${labels.length}장 + labels.json`);
