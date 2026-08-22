"""일괄 등록 데모 — 서로 다른 상황의 집행 건을 만들어 검토 대기열을 채운다.

    docker compose run --rm api python -m app.bulk_demo \
        --base-url https://<render-서비스>.onrender.com --count 12

증빙은 벤치마크 세트(eval/receipts + labels.json)를 쓰고, 입력값은 각 영수증의
정답 라벨에서 가져온다. 그 위에 **시나리오별로 한 군데씩만 어긋나게** 만들어
룰마다 다른 이유로 주의·위반이 뜨게 한다 — 원인이 한 가지뿐인 대기열은
룰 엔진이 일하는 걸 보여주지 못하기 때문이다.

이 스크립트가 보여주는 것:
- DB 큐 + 워커가 밀린 작업을 순서대로 소화하는 과정
- 대시보드 "자동 검증 시간(중앙값)"이 1건 요행이 아닌 N건 실측 통계가 되는 것
- 룰 카탈로그가 서로 다른 사유로 걸러내는 현실적인 검토 대기열

기본값이 '사업자번호 미입력'인 이유: 합성 영수증의 사업자번호는 체크섬만 유효한
무작위 값이라 실존하지 않는다. NTS_API_KEY가 설정된 환경에서 이 번호를 그대로
입력하면 **모든 건이 국세청 미등록(R-VND-002 위반)**으로 떠서 화면이 단조로워진다.
그래서 대부분의 시나리오는 번호를 비우고(R-VND-001 주의), 휴폐업 검증을 보여주는
시나리오에서만 번호를 넣는다.

hard 등급 증빙에서는 AI가 실제로 오독하기도 한다. 그 경우 입력값과의 대조
(R-EVD-002/003/004)가 잡아내는데, AI의 confidence가 임계값을 넘겨 저신뢰 플래그가
붙지 않는 경우에도 이 대조는 독립적으로 동작한다 — 다층 방어의 실제 사례다.
그래서 아래 '기대 결과'와 다른 룰이 추가로 뜰 수 있고, 그건 오류가 아니다.

자동 승인은 없다 — 파이프라인의 종착지는 항상 '검토 대기'이고 승인은 사람이 한다.
승인·반려가 섞인 화면은 담당자 계정으로 직접 처리해서 만든다.

앱 내부를 import하지 않고 공개 API만 호출한다 — 배포 환경을 바깥에서 두드리는
스모크 테스트를 겸하기 위해서다.
"""

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

EVAL_DIR = Path(__file__).parent.parent / "eval"
MIME = {".png": "image/png", ".jpg": "image/jpeg"}


@dataclass(frozen=True)
class Scenario:
    """집행 건 하나가 재현하는 상황.

    증빙의 정답값에서 출발해 아래 필드만큼만 어긋나게 만든다.
    """

    label: str  # 목록 제목에 들어갈 상황 이름
    expect: str  # 사람이 눈으로 대조할 기대 결과
    with_biz: bool = False  # 사업자번호 입력 여부 (넣으면 국세청 조회 대상이 된다)
    biz_override: str | None = None  # 일부러 틀린 번호
    category: str = "MATERIAL"
    amount_delta: int = 0  # 증빙 금액과의 차이
    date_override: str | None = None
    duplicate_prev: bool = False  # 앞서 등록한 건과 같은 거래처·금액·일자로 재청구


# 2026-08-23은 일요일, 2025-12-22는 협약 시작(2026-01-01) 이전의 평일이다.
SCENARIOS: list[Scenario] = [
    Scenario("정상 집행", "주의 — 사업자번호 미입력(R-VND-001)"),
    Scenario("정상 집행", "주의 — 사업자번호 미입력(R-VND-001)"),
    Scenario(
        "휴일 집행",
        "주의 — 휴일 집행(R-DAY-001) + 증빙 발행일 불일치(R-EVD-003)",
        date_override="2026-08-23",
    ),
    Scenario("비목 오선택 의심", "주의 — AI 제안 비목과 불일치(R-CAT-001)", category="ACTIVITY"),
    Scenario(
        "거래처 실검증",
        "위반 — 국세청 미등록(R-VND-002). NTS 키가 없으면 주의(R-VND-003)",
        with_biz=True,
    ),
    Scenario("금액 오입력", "위반 — 증빙 금액 불일치(R-EVD-002)", amount_delta=-120_000),
    Scenario(
        "연구기간 외 집행",
        "위반 — 연구기간 외(R-PRD-001) + 증빙 발행일 불일치(R-EVD-003)",
        date_override="2025-12-22",
    ),
    Scenario(
        "사업자번호 오타",
        "위반 — 체크섬 불일치(R-VND-001) + 증빙 번호 불일치(R-EVD-004)",
        with_biz=True,
        biz_override="1234567890",
    ),
    Scenario("정상 집행", "주의 — 사업자번호 미입력(R-VND-001)"),
    Scenario(
        "중복 청구 의심",
        "주의/위반 — 중복 의심(R-DUP-001). 중복 판정은 사업자번호 기준이라"
        " 번호가 필요하고, 그래서 국세청 미등록(R-VND-002)도 함께 뜬다",
        with_biz=True,
        duplicate_prev=True,
    ),
    Scenario("정상 집행", "주의 — 사업자번호 미입력(R-VND-001)"),
    Scenario("금액 오입력", "위반 — 증빙 금액 불일치(R-EVD-002)", amount_delta=55_000),
]


@dataclass
class Submitted:
    expense_id: int
    scenario: Scenario
    receipt: str
    body: dict = field(default_factory=dict)


def log(msg: str) -> None:
    print(msg, flush=True)


def build_body(
    scenario: Scenario, label: dict, project_id: int, prev_with_biz: dict | None
) -> dict:
    """정답 라벨 + 시나리오 → 등록 요청 본문."""
    if scenario.duplicate_prev and prev_with_biz is not None:
        # 중복 판정은 과제·사업자번호·금액·일자가 모두 같아야 하고, 사업자번호가
        # 비어 있으면 아예 검사하지 않는다 — 그래서 '번호가 있는' 앞선 건을 복제한다.
        return {
            **prev_with_biz,
            "title": f"{scenario.label} — {prev_with_biz['vendor_name']}",
            "purpose": "앞선 건과 동일 조건 재청구 (중복 탐지 확인용)",
        }

    biz = None
    if scenario.biz_override is not None:
        biz = scenario.biz_override
    elif scenario.with_biz:
        biz = label["biz_no"]

    return {
        "project_id": project_id,
        "category": scenario.category,
        "title": f"{scenario.label} — {label['vendor_name']}",
        "vendor_name": label["vendor_name"],
        "vendor_biz_no": biz,
        "purpose": "연구 수행에 직접 소모되는 재료 구입 (일괄 검증 데모)",
        "amount": max(1, label["total_amount"] + scenario.amount_delta),
        "spent_at": scenario.date_override or label["issued_at"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="예: https://xxx.onrender.com")
    parser.add_argument("--count", type=int, default=len(SCENARIOS), help="등록할 건수")
    parser.add_argument("--email", default="researcher@demo.kr")
    parser.add_argument("--password", default="demo1234!")
    parser.add_argument("--no-wait", action="store_true", help="제출만 하고 결과를 기다리지 않음")
    args = parser.parse_args()
    api = args.base_url.rstrip("/") + "/api/v1"

    labels: list[dict] = json.loads((EVAL_DIR / "labels.json").read_text())
    # 합계금액이 문서에 없는 영수증은 금액을 입력할 수 없으므로 제외한다
    usable = [x for x in labels if x["total_amount"] is not None]
    scenarios = SCENARIOS[: args.count]
    if len(usable) < len(scenarios):
        log(f"사용 가능한 영수증이 {len(usable)}장뿐이라 그만큼만 등록합니다.")
        scenarios = scenarios[: len(usable)]

    # 무료 티어 슬립 대비: 첫 요청은 서버가 깨어날 때까지 오래 걸릴 수 있다
    client = httpx.Client(timeout=90)

    log(f"로그인: {args.email}")
    res = client.post(f"{api}/auth/login", json={"email": args.email, "password": args.password})
    res.raise_for_status()
    client.headers["Authorization"] = f"Bearer {res.json()['access_token']}"

    project = client.get(f"{api}/projects").raise_for_status().json()[0]
    log(f"과제: {project['code']} {project['name']}\n")

    submitted: list[Submitted] = []
    prev_with_biz: dict | None = None  # 중복 시나리오가 복제할 원본
    for i, (scenario, label) in enumerate(zip(scenarios, usable, strict=False), 1):
        body = build_body(scenario, label, project["id"], prev_with_biz)
        receipt = EVAL_DIR / "receipts" / label["file"]

        expense = client.post(f"{api}/expenses", json=body).raise_for_status().json()
        client.post(
            f"{api}/expenses/{expense['id']}/evidences",
            files={"file": (label["file"], receipt.read_bytes(), MIME[receipt.suffix])},
        ).raise_for_status()
        client.post(f"{api}/expenses/{expense['id']}/submit").raise_for_status()

        submitted.append(Submitted(expense["id"], scenario, label["file"], body))
        # 복제 원본은 '유효한' 번호를 가진 건이어야 한다 — 오타 시나리오를 복제하면
        # 중복 건이 체크섬 위반까지 물려받아 무엇을 보여주는 건지 흐려진다.
        if scenario.with_biz and scenario.biz_override is None and not scenario.duplicate_prev:
            prev_with_biz = body
        log(f"[{i}/{len(scenarios)}] #{expense['id']} {scenario.label} ({label['tier']})")
        log(f"        기대: {scenario.expect}")

    if args.no_wait:
        log(f"\n제출 완료 {len(submitted)}건. 검토 대기 목록에서 처리 과정을 확인하세요.")
        return

    # 워커가 순서대로 소화하는 과정을 지켜본다 (건당 AI 호출 2회라 수십 초씩 걸린다)
    log("\n워커 처리 대기 중… (검증이 끝난 건부터 결과를 출력)")
    pending = {s.expense_id: s for s in submitted}
    deadline = time.monotonic() + 20 * 60
    while pending and time.monotonic() < deadline:
        time.sleep(5)
        for expense_id in sorted(pending):
            detail = client.get(f"{api}/expenses/{expense_id}").json()
            if detail["status"] in ("SUBMITTED", "VALIDATING"):
                continue
            fired = [v for v in detail["validations"] if v["severity"] in ("WARN", "FAIL")]
            risk = "위반" if any(v["severity"] == "FAIL" for v in fired) else "주의"
            codes = ", ".join(f"{v['rule_code']}({v['severity']})" for v in fired) or "없음"
            log(f"  #{expense_id} [{risk}] {pending[expense_id].scenario.label} → {codes}")
            del pending[expense_id]

    if pending:
        log(f"\n시간 초과 — 미완료 {len(pending)}건: {sorted(pending)} (워커 로그를 확인하세요)")
        sys.exit(1)
    log("\n전체 완료. 담당자 계정으로 승인/반려를 처리하면 상태가 섞인 화면이 만들어집니다.")


if __name__ == "__main__":
    main()
