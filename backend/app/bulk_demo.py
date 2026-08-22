"""일괄 등록 데모 — 서로 다른 증빙 N건을 API로 등록·제출해 큐 처리를 관찰한다.

    docker compose run --rm api python -m app.bulk_demo \
        --base-url https://<render-서비스>.onrender.com --count 5

벤치마크 세트(eval/receipts + labels.json)의 영수증을 증빙으로 쓰고, 입력값은
각 영수증의 정답 라벨에서 가져온다 — 건마다 거래처·금액·일자가 달라서
중복 룰에 걸리지 않고, AI가 제대로 읽으면 대사 룰이 통과한다.

이 스크립트가 보여주는 것:
- DB 큐 + 워커가 밀린 작업을 순서대로 소화하는 과정 (검토 대기 목록이 하나씩 늘어남)
- 대시보드 "자동 검증 시간(중앙값)"이 1건 요행이 아닌 N건 실측 통계가 되는 것
- hard 등급 영수증을 섞으면(--count 20 이상) 일부러 흐린 증빙에서 대사 룰이
  불일치를 잡아내는 것 — 전부 통과가 아닌 현실적인 검토함이 만들어진다

주의: 등록되는 건은 대부분 위반이 뜨는 것이 정상이다. 두 가지 이유가 겹친다.
1. NTS_API_KEY가 설정된 환경에서는 **가상 사업자번호가 국세청 미등록(R-VND-002)**으로
   걸린다. 합성 영수증의 번호는 체크섬만 유효한 무작위 값이라 실존하지 않는다.
2. hard 등급 증빙에서는 AI가 실제로 오독하기도 하며, 그 경우 입력값과의 대조
   (R-EVD-002/003/004)가 잡아낸다. AI의 confidence가 임계값을 넘겨 저신뢰 플래그가
   붙지 않는 경우에도 이 대조는 독립적으로 동작한다 — 다층 방어의 실제 사례다.
따라서 이 스크립트의 결과물은 "깨끗한 데모"가 아니라 **검토가 필요한 현실적인 대기열**이다.
승인된 건이 섞인 화면을 원하면 담당자 계정으로 직접 승인/반려하면 된다(자동 승인은 없다).

앱 내부를 import하지 않고 공개 API만 호출한다 — 배포 환경을 바깥에서 두드리는
스모크 테스트를 겸하기 위해서다.
"""

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

EVAL_DIR = Path(__file__).parent.parent / "eval"
MIME = {".png": "image/png", ".jpg": "image/jpeg"}


def log(msg: str) -> None:
    print(msg, flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="예: https://xxx.onrender.com")
    parser.add_argument("--count", type=int, default=5, help="등록할 건수 (최대 25)")
    parser.add_argument("--email", default="researcher@demo.kr")
    parser.add_argument("--password", default="demo1234!")
    parser.add_argument("--no-wait", action="store_true", help="제출만 하고 결과를 기다리지 않음")
    args = parser.parse_args()
    api = args.base_url.rstrip("/") + "/api/v1"

    labels: list[dict] = json.loads((EVAL_DIR / "labels.json").read_text())
    # 합계금액이 문서에 없는 영수증은 금액을 입력할 수 없으므로 건너뛴다
    usable = [x for x in labels if x["total_amount"] is not None][: args.count]

    # 무료 티어 슬립 대비: 첫 요청은 서버가 깨어날 때까지 오래 걸릴 수 있다
    client = httpx.Client(timeout=90)

    log(f"로그인: {args.email}")
    res = client.post(f"{api}/auth/login", json={"email": args.email, "password": args.password})
    res.raise_for_status()
    client.headers["Authorization"] = f"Bearer {res.json()['access_token']}"

    projects = client.get(f"{api}/projects").json()
    project = projects[0]
    log(f"과제: {project['code']} {project['name']}")

    ids: list[int] = []
    for i, label in enumerate(usable, 1):
        receipt = EVAL_DIR / "receipts" / label["file"]
        body = {
            "project_id": project["id"],
            "category": "MATERIAL",
            "title": f"일괄검증 {i:02d} — {label['vendor_name']}",
            "vendor_name": label["vendor_name"],
            "vendor_biz_no": label["biz_no"],
            "purpose": "연구 수행에 직접 소모되는 재료 구입 (일괄 검증 데모)",
            "amount": label["total_amount"],
            "spent_at": label["issued_at"],
        }
        expense = client.post(f"{api}/expenses", json=body).raise_for_status().json()
        client.post(
            f"{api}/expenses/{expense['id']}/evidences",
            files={"file": (label["file"], receipt.read_bytes(), MIME[receipt.suffix])},
        ).raise_for_status()
        client.post(f"{api}/expenses/{expense['id']}/submit").raise_for_status()
        ids.append(expense["id"])
        log(f"[{i}/{len(usable)}] #{expense['id']} 제출 — {label['file']} ({label['tier']})")

    if args.no_wait:
        log(f"제출 완료 {len(ids)}건. 검토 대기 목록에서 처리 과정을 확인하세요.")
        return

    # 워커가 순서대로 소화하는 과정을 지켜본다 (건당 AI 호출 2회라 수십 초씩 걸린다)
    log("워커 처리 대기 중… (검증 완료된 건부터 결과를 출력)")
    pending = set(ids)
    deadline = time.monotonic() + 15 * 60
    while pending and time.monotonic() < deadline:
        time.sleep(5)
        for expense_id in sorted(pending):
            detail = client.get(f"{api}/expenses/{expense_id}").json()
            if detail["status"] in ("SUBMITTED", "VALIDATING"):
                continue
            counts: dict[str, int] = {}
            for v in detail["validations"]:
                counts[v["severity"]] = counts.get(v["severity"], 0) + 1
            summary = " ".join(f"{k}={v}" for k, v in sorted(counts.items()))
            log(f"  #{expense_id} → {detail['status']} ({summary})")
            pending.discard(expense_id)

    if pending:
        log(f"시간 초과 — 미완료 {len(pending)}건: {sorted(pending)} (워커 로그를 확인하세요)")
        sys.exit(1)
    log("전체 완료. 담당자 계정으로 검토 대기 목록과 대시보드를 확인하세요.")


if __name__ == "__main__":
    main()
