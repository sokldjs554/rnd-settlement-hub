"""AI 호출 기록 (ai_runs). 호출자 트랜잭션에 참여한다.

무엇을 어떤 모델·프롬프트로 호출했고 무엇이 나왔는지를 전부 남긴다.
→ 대시보드의 AI 지표(추출 성공률·제안 채택률) 계산과 프롬프트 회귀 분석의 원천 데이터.
"""

from decimal import Decimal

from sqlalchemy.orm import Session

from app.ai.base import AIClient
from app.models import AiRun
from app.models.enums import AiRunKind, AiRunStatus, BudgetCategory


def record_ai_run(
    db: Session,
    *,
    kind: AiRunKind,
    client: AIClient,
    status: AiRunStatus,
    expense_id: int | None = None,
    report_id: int | None = None,
    evidence_id: int | None = None,
    output_json: dict | None = None,
    suggested_category: BudgetCategory | None = None,
    confidence: Decimal | None = None,
    error: str | None = None,
    latency_ms: int | None = None,
) -> AiRun:
    run = AiRun(
        expense_id=expense_id,
        report_id=report_id,
        evidence_id=evidence_id,
        kind=kind,
        model=client.model,
        prompt_version=client.prompt_version,
        status=status,
        output_json=output_json,
        suggested_category=suggested_category,
        confidence=confidence,
        error=error,
        latency_ms=latency_ms,
    )
    db.add(run)
    db.flush()
    return run
