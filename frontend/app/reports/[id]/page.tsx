"use client";

/**
 * 보고서 상세: 비목별 집계표(숫자 = SQL 스냅샷) + AI 서술 초안 편집 + 확정.
 * 서술부에는 "AI 초안" 표시를 명확히 하고, 확정 후에는 모든 편집이 잠긴다.
 */

import { api, ApiError } from "@/lib/api";
import { formatDateTime, formatKrw } from "@/lib/format";
import type { ReportDetail } from "@/lib/types";
import {
  Badge,
  Button,
  Card,
  Dialog,
  ErrorState,
  Spinner,
  Table,
  Td,
  Textarea,
  Th,
} from "@/components/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

export default function ReportDetailPage() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const [narrative, setNarrative] = useState("");
  const [finalizeOpen, setFinalizeOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: report, isLoading, isError } = useQuery({
    queryKey: ["report", id],
    queryFn: () => api<ReportDetail>(`/reports/${id}`),
    // AI 서술 초안이 비동기로 채워지므로, 초안이 비어 있는 동안 폴링한다
    refetchInterval: (query) => {
      const r = query.state.data;
      return r && r.status === "DRAFT" && r.narrative_md === null ? 5000 : false;
    },
  });

  useEffect(() => {
    if (report?.narrative_md != null) setNarrative(report.narrative_md);
  }, [report?.narrative_md]);

  const saveNarrative = useMutation({
    mutationFn: () =>
      api(`/reports/${id}`, { method: "PATCH", body: JSON.stringify({ narrative_md: narrative }) }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["report", id] }),
    onError: (e) => setError(e instanceof ApiError ? e.message : "저장 실패"),
  });

  const finalize = useMutation({
    mutationFn: () => api(`/reports/${id}/finalize`, { method: "POST" }),
    onSuccess: () => {
      setFinalizeOpen(false);
      queryClient.invalidateQueries({ queryKey: ["report", id] });
      queryClient.invalidateQueries({ queryKey: ["reports"] });
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "확정 실패"),
  });

  if (isLoading) return <Spinner />;
  if (isError || !report) return <ErrorState message="보고서를 불러오지 못했습니다." />;

  const summary = report.summary_json;
  const isDraft = report.status === "DRAFT";

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-bold">
          {report.period_year}년 {report.period_month}월 정산보고서
        </h1>
        <Badge tone={isDraft ? "yellow" : "green"}>{isDraft ? "초안" : "확정"}</Badge>
        {report.finalized_at && (
          <span className="text-xs text-slate-500">확정: {formatDateTime(report.finalized_at)}</span>
        )}
        {isDraft && (
          <Button className="ml-auto" onClick={() => setFinalizeOpen(true)}>
            보고서 확정
          </Button>
        )}
      </div>

      {error && <ErrorState message={error} />}

      <Card title="비목별 집계 (SQL 스냅샷 — AI가 만들지 않은 숫자)">
        {!summary ? (
          <p className="text-sm text-slate-500">집계가 없습니다.</p>
        ) : (
          <>
            <Table>
              <thead>
                <tr>
                  <Th>비목</Th>
                  <Th className="text-right">예산</Th>
                  <Th className="text-right">당월 승인</Th>
                  <Th className="text-right">누적 승인</Th>
                  <Th className="text-right">잔액</Th>
                </tr>
              </thead>
              <tbody>
                {summary.categories.map((c) => (
                  <tr key={c.category}>
                    <Td>{c.label}</Td>
                    <Td className="text-right">{formatKrw(c.budget)}</Td>
                    <Td className="text-right">{formatKrw(c.month_approved)}</Td>
                    <Td className="text-right">{formatKrw(c.cumulative_approved)}</Td>
                    <Td className="text-right">{formatKrw(c.remaining)}</Td>
                  </tr>
                ))}
                <tr className="font-semibold">
                  <Td>합계</Td>
                  <Td className="text-right">{formatKrw(summary.totals.budget)}</Td>
                  <Td className="text-right">{formatKrw(summary.totals.month_approved)}</Td>
                  <Td className="text-right">{formatKrw(summary.totals.cumulative_approved)}</Td>
                  <Td className="text-right">{formatKrw(summary.totals.remaining)}</Td>
                </tr>
              </tbody>
            </Table>
            <p className="mt-2 text-xs text-slate-500">
              당월 승인 {summary.counts.month_approved_count}건 · 반려{" "}
              {summary.counts.month_rejected_count}건 · 검토 대기{" "}
              {summary.counts.pending_review_count}건 · override 승인{" "}
              {summary.counts.month_override_count}건
            </p>
          </>
        )}
      </Card>

      <Card
        title="서술부"
        actions={
          isDraft && (
            <Button
              variant="secondary"
              disabled={saveNarrative.isPending}
              onClick={() => saveNarrative.mutate()}
            >
              {saveNarrative.isPending ? "저장 중…" : "저장"}
            </Button>
          )
        }
      >
        {isDraft && report.narrative_md === null && (
          <p className="mb-2 text-sm text-sky-700">
            AI 서술 초안을 생성하는 중입니다… (AI 미사용 모드에서는 직접 작성해 주세요)
          </p>
        )}
        {isDraft ? (
          <>
            <p className="mb-2 text-xs text-amber-700">
              아래 내용은 AI가 집계를 바탕으로 쓴 <b>초안</b>입니다. 담당자 검토·수정 후
              확정하세요.
            </p>
            <Textarea
              rows={10}
              value={narrative}
              onChange={(e) => setNarrative(e.target.value)}
              placeholder="서술부를 입력하세요 (마크다운)"
            />
          </>
        ) : (
          <pre className="whitespace-pre-wrap font-sans text-sm text-slate-800">
            {report.narrative_md ?? "(서술 없음)"}
          </pre>
        )}
      </Card>

      <Dialog open={finalizeOpen} title="보고서 확정" onClose={() => setFinalizeOpen(false)}>
        <p className="text-sm text-slate-600">
          확정하면 이 기간의 승인된 집행 건들이 보고서에 묶여 <b>더 이상 수정·반려할 수
          없습니다</b>. 숫자 집계도 확정 시점 기준으로 고정됩니다. 계속할까요?
        </p>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="secondary" onClick={() => setFinalizeOpen(false)}>
            취소
          </Button>
          <Button disabled={finalize.isPending} onClick={() => finalize.mutate()}>
            {finalize.isPending ? "확정 중…" : "확정"}
          </Button>
        </div>
      </Dialog>
    </div>
  );
}
