"use client";

/**
 * 집행 건 상세 — 이 시스템의 핵심 검토 화면.
 * ① 증빙 원본 ↔ AI 추출값 ↔ 입력값 3단 비교  ② 룰 검증 결과  ③ 승인/반려(override 포함)  ④ 이력
 */

import { api, ApiError, fetchFileBlob } from "@/lib/api";
import {
  CATEGORY_LABELS,
  formatDate,
  formatDateTime,
  formatKrw,
} from "@/lib/format";
import { useCurrentUser } from "@/lib/providers";
import type { ExpenseDetail, HistoryEvent } from "@/lib/types";
import { SeverityBadge, StatusBadge } from "@/components/badges";
import {
  Button,
  Card,
  Dialog,
  ErrorState,
  Label,
  Spinner,
  Table,
  Td,
  Textarea,
  Th,
  cn,
} from "@/components/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

/** 값 비교 행: AI 추출값과 입력값이 다르면 강조 */
function CompareRow({
  label,
  entered,
  extracted,
}: {
  label: string;
  entered: string;
  extracted: string | null;
}) {
  const mismatch = extracted !== null && extracted !== "-" && entered !== extracted;
  return (
    <tr>
      <Td className="text-slate-500">{label}</Td>
      <Td className={cn(mismatch && "font-semibold text-red-700")}>{entered}</Td>
      <Td className={cn(mismatch && "font-semibold text-red-700")}>
        {extracted ?? <span className="text-slate-400">추출 안 됨</span>}
      </Td>
    </tr>
  );
}

function EvidenceViewer({ expense }: { expense: ExpenseDetail }) {
  const [openUrl, setOpenUrl] = useState<string | null>(null);
  const [openMime, setOpenMime] = useState<string>("");

  const view = async (evidenceId: number, mime: string) => {
    const url = await fetchFileBlob(`/evidences/${evidenceId}/file`);
    setOpenMime(mime);
    setOpenUrl(url);
  };

  if (expense.evidences.length === 0) {
    return <p className="text-sm text-red-600">첨부된 증빙이 없습니다.</p>;
  }
  return (
    <>
      <ul className="space-y-1 text-sm">
        {expense.evidences.map((ev) => (
          <li key={ev.id}>
            <button
              className="text-sky-700 hover:underline"
              onClick={() => view(ev.id, ev.mime_type)}
            >
              {ev.file_name}
            </button>
            <span className="ml-2 text-xs text-slate-400">
              {(ev.size_bytes / 1024).toFixed(0)}KB
            </span>
          </li>
        ))}
      </ul>
      {openUrl && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-6"
          onClick={() => setOpenUrl(null)}
        >
          {openMime === "application/pdf" ? (
            <iframe src={openUrl} className="h-full w-full max-w-4xl rounded-lg bg-white" />
          ) : (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={openUrl} alt="증빙" className="max-h-full max-w-4xl rounded-lg" />
          )}
        </div>
      )}
    </>
  );
}

export default function ExpenseDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const user = useCurrentUser();
  const queryClient = useQueryClient();
  const [dialog, setDialog] = useState<"approve" | "reject" | "override" | null>(null);
  const [comment, setComment] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);

  const { data: expense, isLoading, isError } = useQuery({
    queryKey: ["expense", id],
    queryFn: () => api<ExpenseDetail>(`/expenses/${id}`),
    // 파이프라인 진행 중이면 5초마다 갱신해 검증 완료를 자동 반영한다
    refetchInterval: (query) =>
      ["SUBMITTED", "VALIDATING"].includes(query.state.data?.status ?? "") ? 5000 : false,
  });
  const { data: history } = useQuery({
    queryKey: ["expense-history", id],
    queryFn: () => api<HistoryEvent[]>(`/expenses/${id}/history`),
  });

  const act = useMutation({
    mutationFn: (input: { path: string; body: Record<string, unknown> }) =>
      api(`/expenses/${id}/${input.path}`, {
        method: "POST",
        body: JSON.stringify(input.body),
      }),
    onSuccess: () => {
      setDialog(null);
      setComment("");
      setActionError(null);
      queryClient.invalidateQueries({ queryKey: ["expense", id] });
      queryClient.invalidateQueries({ queryKey: ["expense-history", id] });
      queryClient.invalidateQueries({ queryKey: ["expenses"] });
    },
    onError: (e) =>
      setActionError(e instanceof ApiError ? e.message : "처리에 실패했습니다."),
  });

  if (isLoading) return <Spinner />;
  if (isError || !expense) return <ErrorState message="집행 건을 불러오지 못했습니다." />;

  const extraction = expense.ai.extraction;
  const suggestion = expense.ai.category_suggestion;
  const hasFail = expense.validations.some((v) => v.severity === "FAIL");
  const canReview = user && user.role !== "RESEARCHER" && expense.status === "NEEDS_REVIEW";
  const isOwnerEditable =
    user?.id === expense.created_by && ["DRAFT", "REJECTED"].includes(expense.status);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-lg font-bold">{expense.title}</h1>
        <StatusBadge status={expense.status} />
        {expense.report_id && <span className="text-xs text-slate-500">보고서에 확정 포함(잠김)</span>}
        <div className="ml-auto flex gap-2">
          {isOwnerEditable && (
            <Button variant="secondary" onClick={() => router.push(`/expenses`)}>
              목록
            </Button>
          )}
          {canReview && (
            <>
              <Button variant="danger" onClick={() => setDialog("reject")}>
                반려
              </Button>
              <Button onClick={() => setDialog(hasFail ? "override" : "approve")}>
                {hasFail ? "override 승인" : "승인"}
              </Button>
            </>
          )}
        </div>
      </div>

      {expense.status === "REJECTED" && expense.reject_reason && (
        <ErrorState message={`반려 사유: ${expense.reject_reason}`} />
      )}
      {["SUBMITTED", "VALIDATING"].includes(expense.status) && (
        <div className="rounded-md border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-800">
          자동 검증 파이프라인이 실행 중입니다. 완료되면 자동으로 갱신됩니다.
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="입력값 ↔ AI 추출값 대조">
          <Table>
            <thead>
              <tr>
                <Th />
                <Th>입력값</Th>
                <Th>AI 추출값 (증빙)</Th>
              </tr>
            </thead>
            <tbody>
              <CompareRow
                label="거래처"
                entered={expense.vendor_name}
                extracted={extraction ? extraction.vendor_name ?? "-" : null}
              />
              <CompareRow
                label="사업자번호"
                entered={expense.vendor_biz_no ?? "-"}
                extracted={extraction ? extraction.biz_no ?? "-" : null}
              />
              <CompareRow
                label="금액"
                entered={formatKrw(expense.amount)}
                extracted={extraction ? formatKrw(extraction.total_amount) : null}
              />
              <CompareRow
                label="일자"
                entered={formatDate(expense.spent_at)}
                extracted={extraction ? formatDate(extraction.issued_at) : null}
              />
            </tbody>
          </Table>
          <div className="mt-2 space-y-1 text-xs text-slate-500">
            {extraction ? (
              <p>
                문서 종류: {extraction.doc_type ?? "미상"} · AI 신뢰도:{" "}
                {extraction.confidence ?? "-"}
                {extraction.status === "FAILED" && (
                  <span className="text-red-600"> · 추출 실패 — 수기 대조 필요</span>
                )}
              </p>
            ) : (
              <p>AI 추출 결과가 없습니다 (미실행 또는 AI 미사용 모드) — 수기 대조가 필요합니다.</p>
            )}
            {suggestion?.category && (
              <p>
                AI 비목 제안:{" "}
                <span
                  className={cn(
                    "font-medium",
                    suggestion.category !== expense.category && "text-amber-700",
                  )}
                >
                  {CATEGORY_LABELS[suggestion.category]}
                </span>{" "}
                (선택: {CATEGORY_LABELS[expense.category]}) — {suggestion.rationale}
              </p>
            )}
          </div>
        </Card>

        <Card title="증빙 원본">
          <EvidenceViewer expense={expense} />
          <dl className="mt-4 grid grid-cols-2 gap-2 border-t border-slate-100 pt-3 text-sm">
            <dt className="text-slate-500">과제</dt>
            <dd className="font-mono text-xs">{expense.project_code}</dd>
            <dt className="text-slate-500">작성자</dt>
            <dd>{expense.created_by_name}</dd>
            <dt className="text-slate-500">등록일</dt>
            <dd>{formatDateTime(expense.created_at)}</dd>
          </dl>
        </Card>
      </div>

      <Card title={`자동 검증 결과 (${expense.validations.length}건)`}>
        {expense.validations.length === 0 ? (
          <p className="text-sm text-slate-500">아직 검증이 실행되지 않았습니다.</p>
        ) : (
          <ul className="space-y-2">
            {[...expense.validations]
              .sort((a, b) => severityRank(b.severity) - severityRank(a.severity))
              .map((v) => (
                <li key={v.rule_code} className="flex items-start gap-2 text-sm">
                  <SeverityBadge severity={v.severity} />
                  <div>
                    <p className="text-slate-800">
                      <span className="mr-1 font-mono text-xs text-slate-400">{v.rule_code}</span>
                      {v.message}
                    </p>
                    {v.detail && (
                      <p className="text-xs text-slate-400">{JSON.stringify(v.detail)}</p>
                    )}
                  </div>
                </li>
              ))}
          </ul>
        )}
      </Card>

      <Card title="처리 이력">
        {!history || history.length === 0 ? (
          <p className="text-sm text-slate-500">이력이 없습니다.</p>
        ) : (
          <ul className="space-y-1.5 text-sm">
            {history.map((event, i) => (
              <li key={i} className="flex gap-3">
                <span className="w-36 shrink-0 text-xs text-slate-400">
                  {formatDateTime(event.at)}
                </span>
                <span className="text-slate-700">{describeEvent(event)}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {/* 승인/반려 다이얼로그 */}
      <Dialog
        open={dialog !== null}
        title={
          dialog === "reject" ? "반려" : dialog === "override" ? "override 승인" : "승인"
        }
        onClose={() => setDialog(null)}
      >
        {dialog === "override" && (
          <p className="mb-3 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800">
            위반(FAIL) 판정이 있는 건입니다. 승인하려면 사유를 반드시 남겨야 하며, 사유는 감사
            로그에 기록됩니다.
          </p>
        )}
        <Label htmlFor="comment">
          {dialog === "reject" ? "반려 사유 (필수)" : dialog === "override" ? "override 사유 (필수)" : "코멘트 (선택)"}
        </Label>
        <Textarea
          id="comment"
          rows={3}
          value={comment}
          onChange={(e) => setComment(e.target.value)}
        />
        {actionError && <p className="mt-2 text-sm text-red-600">{actionError}</p>}
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="secondary" onClick={() => setDialog(null)}>
            취소
          </Button>
          <Button
            variant={dialog === "reject" ? "danger" : "primary"}
            disabled={act.isPending || (dialog !== "approve" && !comment.trim())}
            onClick={() =>
              act.mutate(
                dialog === "reject"
                  ? { path: "reject", body: { reason: comment } }
                  : {
                      path: "approve",
                      body: { comment: comment || null, override: dialog === "override" },
                    },
              )
            }
          >
            {act.isPending ? "처리 중…" : "확인"}
          </Button>
        </div>
      </Dialog>
    </div>
  );
}

function severityRank(s: string): number {
  return { FAIL: 3, WARN: 2, INFO: 1, PASS: 0 }[s] ?? 0;
}

function describeEvent(event: HistoryEvent): string {
  const actor = event.actor ? `${event.actor} — ` : "시스템 — ";
  const names: Record<string, string> = {
    "audit:create": "집행 건 등록",
    "audit:update": "내용 수정",
    "audit:submit": "제출",
    "audit:upload_evidence": "증빙 업로드",
    "audit:approve": "승인",
    "audit:approve_override": "override 승인",
    "audit:reject": "반려",
    "audit:pipeline_completed": "자동 검증 완료",
    "audit:delete": "삭제",
    "pipeline:queued": "검증 대기",
    "pipeline:running": "검증 실행 중",
    "pipeline:succeeded": "검증 파이프라인 성공",
    "pipeline:failed": "검증 파이프라인 실패",
  };
  return actor + (names[event.type] ?? event.type);
}
