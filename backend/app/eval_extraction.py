"""AI 증빙 추출 정확도 벤치마크.

합성 영수증 25장(backend/eval/receipts + labels.json)에 실제 AI 클라이언트를 돌려
필드별 정확도를 잰다. 결과 마크다운은 stdout으로 나오므로 파일로 리다이렉트한다:

    docker compose exec api python -m app.eval_extraction > docs/AI_EVAL.md

- 대시보드의 "추출 성공률"은 운영 워크플로 호출만 집계한다. 모델 자체의 정확도는
  이 벤치마크로 재고, 두 숫자를 섞지 않는다 (운영 지표 ≠ 모델 평가).
- 정답이 null인 필드(문서에 아예 없는 값)에 모델이 값을 내면 hallucination으로
  따로 센다 — "없으면 null"을 지키는지가 이 시스템 AI 설계의 핵심 요구다.
"""

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from app.ai.base import AIClient, AIUnavailableError, ExtractedDoc
from app.ai.null import NullAIClient, get_ai_client

FIELDS = ("vendor_name", "biz_no", "total_amount", "issued_at")
MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".pdf": "application/pdf"}


def normalize_vendor(name: str | None) -> str | None:
    """상호 비교용 정규화 — 법인 표기·공백 차이는 오답으로 치지 않는다."""
    if name is None:
        return None
    for token in ("(주)", "㈜", "주식회사", " "):
        name = name.replace(token, "")
    return name.strip() or None


@dataclass
class FieldScore:
    correct: int = 0  # 정답 있음 + 일치
    wrong: int = 0  # 정답 있음 + 다른 값
    missed: int = 0  # 정답 있음 + 모델이 null
    abstained: int = 0  # 정답 null + 모델도 null (올바른 유보)
    hallucinated: int = 0  # 정답 null + 모델이 값을 만들어냄

    @property
    def with_answer(self) -> int:
        return self.correct + self.wrong + self.missed


def compare_field(field: str, golden: object, extracted: object) -> str:
    """한 필드의 판정 결과: correct/wrong/missed/abstained/hallucinated."""
    if field == "vendor_name":
        golden, extracted = normalize_vendor(golden), normalize_vendor(extracted)  # type: ignore[arg-type]
    if field == "issued_at" and isinstance(extracted, date):
        extracted = extracted.isoformat()
    if golden is None:
        return "abstained" if extracted is None else "hallucinated"
    if extracted is None:
        return "missed"
    return "correct" if golden == extracted else "wrong"


def score_document(label: dict, doc: ExtractedDoc) -> dict[str, str]:
    """문서 1건의 필드별 판정. {필드: 판정} 형태로 반환한다."""
    extracted = {
        "vendor_name": doc.vendor_name,
        "biz_no": doc.biz_no,
        "total_amount": doc.total_amount,
        "issued_at": doc.issued_at,
    }
    return {f: compare_field(f, label[f], extracted[f]) for f in FIELDS}


def run(client: AIClient, eval_dir: Path, limit: int | None = None) -> str:
    labels: list[dict] = json.loads((eval_dir / "labels.json").read_text())
    if limit:
        labels = labels[:limit]

    scores = {f: FieldScore() for f in FIELDS}
    rows: list[dict] = []
    perfect_confidences: list[Decimal] = []
    imperfect_confidences: list[Decimal] = []
    failed_calls = 0

    for i, label in enumerate(labels, 1):
        path = eval_dir / "receipts" / label["file"]
        print(f"[{i}/{len(labels)}] {label['file']} …", file=sys.stderr)
        try:
            doc = client.extract_document(
                file_bytes=path.read_bytes(), mime_type=MIME[path.suffix.lower()]
            )
        except AIUnavailableError as e:
            failed_calls += 1
            rows.append({"label": label, "verdicts": None, "confidence": None, "error": str(e)})
            continue

        verdicts = score_document(label, doc)
        for f, v in verdicts.items():
            setattr(scores[f], v, getattr(scores[f], v) + 1)
        ok = all(v in ("correct", "abstained") for v in verdicts.values())
        if doc.confidence is not None:
            (perfect_confidences if ok else imperfect_confidences).append(doc.confidence)
        rows.append(
            {"label": label, "verdicts": verdicts, "confidence": doc.confidence, "error": None}
        )

    return render_report(
        client, labels, scores, rows, perfect_confidences, imperfect_confidences, failed_calls
    )


def render_report(
    client: AIClient,
    labels: list[dict],
    scores: dict[str, FieldScore],
    rows: list[dict],
    perfect_conf: list[Decimal],
    imperfect_conf: list[Decimal],
    failed_calls: int,
) -> str:
    n = len(labels)
    scored = [r for r in rows if r["verdicts"] is not None]
    perfect = sum(
        1 for r in scored if all(v in ("correct", "abstained") for v in r["verdicts"].values())
    )
    tiers = {t: sum(1 for x in labels if x["tier"] == t) for t in ("easy", "medium", "hard")}
    field_names = {
        "vendor_name": "상호",
        "biz_no": "사업자번호",
        "total_amount": "합계금액",
        "issued_at": "발행일",
    }
    mean = lambda xs: f"{sum(xs) / len(xs):.3f}" if xs else "—"  # noqa: E731

    out = [
        "# AI 증빙 추출 정확도 벤치마크",
        "",
        f"- 측정일: {datetime.now().date().isoformat()}",
        f"- 모델: `{client.model}` · 프롬프트: `{client.prompt_version}`",
        f"- 표본: 합성 영수증 {n}장"
        f" (easy {tiers['easy']} / medium {tiers['medium']} / hard {tiers['hard']})"
        " — `backend/eval/generate.mjs`가 고정 시드로 생성, 정답은 `labels.json`",
        f"- 호출 실패: {failed_calls}건",
        "",
        "실제 스캔 영수증이 아닌 합성 데이터 기준의 수치다. 문서에 없는 필드의 정답은 null이며,",
        "그 자리에 모델이 값을 내면 **환각**으로 센다.",
        "",
        "## 필드별 결과",
        "",
        "| 필드 | 정답 보유 | 일치 | 오답 | 누락(null) | 정확도 | 올바른 유보 | 환각 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for f in FIELDS:
        s = scores[f]
        acc = f"{s.correct / s.with_answer * 100:.0f}%" if s.with_answer else "—"
        out.append(
            f"| {field_names[f]} | {s.with_answer} | {s.correct} | {s.wrong} | {s.missed}"
            f" | {acc} | {s.abstained} | {s.hallucinated} |"
        )

    out += [
        "",
        "## 문서 단위",
        "",
        f"- 4개 필드 전부 정확(유보 포함): **{perfect}/{len(scored)}건**",
        f"- confidence 평균 — 전부 정확한 문서: {mean(perfect_conf)}"
        f" · 오류 있는 문서: {mean(imperfect_conf)}",
        "  (오류 문서 쪽이 낮을수록 R-AI-001 저신뢰 수기 대조 플래그가 잘 작동한다는 뜻)",
        "",
        "## 오류 상세",
        "",
    ]
    error_rows = [
        r
        for r in rows
        if r["error"] or any(v not in ("correct", "abstained") for v in r["verdicts"].values())
    ]
    if not error_rows:
        out.append("오류 없음.")
    else:
        out += ["| 파일 | 문제 | confidence |", "|---|---|---|"]
        for r in error_rows:
            if r["error"]:
                problems = f"호출 실패: {r['error']}"
            else:
                problems = ", ".join(
                    f"{field_names[f]} {v}"
                    for f, v in r["verdicts"].items()
                    if v not in ("correct", "abstained")
                )
            conf = f"{r['confidence']:.2f}" if r["confidence"] is not None else "—"
            out.append(f"| {r['label']['file']} | {problems} | {conf} |")

    out += [
        "",
        "---",
        "재실행: `docker compose exec api python -m app.eval_extraction > docs/AI_EVAL.md`",
        "",
    ]
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eval-dir", default=str(Path(__file__).parent.parent / "eval"))
    parser.add_argument("--limit", type=int, default=None, help="앞에서 N장만 (요금 절약용)")
    args = parser.parse_args()

    client = get_ai_client()
    if isinstance(client, NullAIClient):
        print("ANTHROPIC_API_KEY가 없어 벤치마크를 실행할 수 없습니다.", file=sys.stderr)
        raise SystemExit(1)

    print(run(client, Path(args.eval_dir), limit=args.limit))


if __name__ == "__main__":
    main()
