"use client";

/** 대사 결과 상세 — 카드 라인별 판정 + 카드에 대응되지 않은 집행 건.
 *
 * 판정은 업로드 시점의 스냅샷이다. 이후 집행 건이 바뀌어도 이 화면은
 * "그때 무엇과 대조했는지"를 그대로 보여준다(보고서 집계와 같은 태도).
 */

import { api } from "@/lib/api";
import { CATEGORY_LABELS, STATUS_LABELS, formatDate, formatDateTime, formatKrw } from "@/lib/format";
import type { CardMatchStatus, ReconciliationDetail } from "@/lib/types";
import { Badge, Card, ErrorState, Spinner, Table, Td, Th } from "@/components/ui";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";

const MATCH_LABELS: Record<CardMatchStatus, string> = {
  MATCHED: "일치",
  MATCHED_NEAR: "근사 일치",
  CANDIDATE: "수기 확인",
  UNMATCHED: "대응 없음",
};

const MATCH_TONES: Record<CardMatchStatus, "green" | "yellow" | "red"> = {
  MATCHED: "green",
  MATCHED_NEAR: "yellow",
  CANDIDATE: "yellow",
  UNMATCHED: "red",
};

function StatCell({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-4 py-3">
      <p className="text-xs text-slate-500">{label}</p>
      <p className="mt-1 text-xl font-bold tabular-nums">{value}</p>
    </div>
  );
}

export default function ReconciliationDetailPage() {
  const params = useParams<{ id: string }>();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["reconciliation", params.id],
    queryFn: () => api<ReconciliationDetail>(`/reconciliations/${params.id}`),
  });

  if (isLoading) return <Spinner />;
  if (isError || !data) return <ErrorState message="대사 결과를 불러오지 못했습니다." />;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Link href="/reconciliation" className="text-slate-500 hover:text-slate-700">
          <ArrowLeft size={18} />
        </Link>
        <div>
          <h1 className="text-lg font-bold">대사 결과 — {data.file_name}</h1>
          <p className="text-sm text-slate-500">{formatDateTime(data.created_at)} 업로드</p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <StatCell label="카드 라인" value={data.total_lines} />
        <StatCell label="일치" value={data.matched_count} />
        <StatCell label="근사 일치" value={data.matched_near_count} />
        <StatCell label="수기 확인" value={data.candidate_count} />
        <StatCell label="대응 없음" value={data.unmatched_count} />
      </div>

      <Card>
        <h2 className="mb-2 text-sm font-semibold text-slate-700">카드 사용내역 라인</h2>
        <Table>
          <thead>
            <tr>
              <Th>승인일</Th>
              <Th>가맹점</Th>
              <Th>사업자번호</Th>
              <Th className="text-right">승인금액</Th>
              <Th>판정</Th>
              <Th>집행 건</Th>
              <Th>비고</Th>
            </tr>
          </thead>
          <tbody>
            {data.lines.map((ln) => (
              <tr key={ln.id} className="hover:bg-slate-50">
                <Td>{formatDate(ln.approved_on)}</Td>
                <Td>{ln.merchant_name}</Td>
                <Td className="tabular-nums">{ln.merchant_biz_no ?? "-"}</Td>
                <Td className="text-right tabular-nums">{formatKrw(ln.amount)}</Td>
                <Td>
                  <Badge tone={MATCH_TONES[ln.match_status]}>{MATCH_LABELS[ln.match_status]}</Badge>
                </Td>
                <Td>
                  {ln.matched_expense_id ? (
                    <Link
                      className="text-blue-700 hover:underline"
                      href={`/expenses/${ln.matched_expense_id}`}
                    >
                      #{ln.matched_expense_id}
                    </Link>
                  ) : (
                    "-"
                  )}
                </Td>
                <Td className="text-slate-500">
                  {ln.note ?? (ln.match_status === "UNMATCHED" ? "미등록 집행 의심" : "")}
                </Td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Card>

      <Card>
        <h2 className="mb-1 text-sm font-semibold text-slate-700">
          카드에 대응되지 않은 집행 건 ({data.unmatched_expenses.length})
        </h2>
        <p className="mb-2 text-xs text-slate-500">
          계좌이체 등 카드 외 결제일 수 있습니다 — 집행 건에 결제수단 정보가 없어 구분하지 못하는
          것이 현재 한계입니다.
        </p>
        {data.unmatched_expenses.length === 0 ? (
          <p className="py-2 text-sm text-slate-500">모든 집행 건이 카드 라인과 대응되었습니다.</p>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>집행일</Th>
                <Th>제목</Th>
                <Th>거래처</Th>
                <Th>비목</Th>
                <Th className="text-right">금액</Th>
                <Th>상태</Th>
              </tr>
            </thead>
            <tbody>
              {data.unmatched_expenses.map((e) => (
                <tr key={e.id} className="hover:bg-slate-50">
                  <Td>{formatDate(e.spent_at)}</Td>
                  <Td>
                    <Link className="text-blue-700 hover:underline" href={`/expenses/${e.id}`}>
                      {e.title}
                    </Link>
                  </Td>
                  <Td>{e.vendor_name}</Td>
                  <Td>{CATEGORY_LABELS[e.category]}</Td>
                  <Td className="text-right tabular-nums">{formatKrw(e.amount)}</Td>
                  <Td>{STATUS_LABELS[e.status]}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </div>
  );
}
