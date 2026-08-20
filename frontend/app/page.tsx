"use client";

/**
 * 관리자 대시보드.
 * 차트 설계 원칙: 모든 차트는 단일 시리즈(단일 색상 #0369a1 + 중립 트랙) — 색상 순환 없음.
 * 상태 의미 색(amber/red)은 라벨이 함께 있는 배지·텍스트에만 쓴다.
 */

import { api } from "@/lib/api";
import { formatKrw, formatPercent, STATUS_LABELS } from "@/lib/format";
import type { DashboardSummary, Project } from "@/lib/types";
import { SeverityBadge } from "@/components/badges";
import { Card, EmptyState, ErrorState, Select, Spinner } from "@/components/ui";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const SERIES = "#0369a1"; // 데이터 시리즈 단일 색
const TRACK = "#e2e8f0"; // 잔여분/배경 트랙 (중립)

function StatTile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <p className="text-xs text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-bold text-slate-900">{value}</p>
      {hint && <p className="mt-0.5 text-xs text-slate-400">{hint}</p>}
    </div>
  );
}

function BudgetUsageCard({ data }: { data: DashboardSummary["budget_usage"] }) {
  const rows = data.filter((b) => Number(b.budget) > 0);
  return (
    <Card title="비목별 예산 소진">
      {rows.length === 0 ? (
        <EmptyState message="등록된 예산이 없습니다." />
      ) : (
        <ul className="space-y-3">
          {rows.map((b) => {
            const budget = Number(b.budget);
            const approved = Number(b.approved);
            const ratio = budget > 0 ? approved / budget : 0;
            const over80 = ratio > 0.8;
            return (
              <li key={b.category}>
                <div className="mb-1 flex items-baseline justify-between text-sm">
                  <span className="text-slate-700">{b.label}</span>
                  <span className="text-xs text-slate-500">
                    {formatKrw(approved)} / {formatKrw(budget)}{" "}
                    <span className={over80 ? "font-semibold text-amber-700" : ""}>
                      ({formatPercent(ratio)}{over80 ? " · 소진 임박" : ""})
                    </span>
                  </span>
                </div>
                <div className="h-2 overflow-hidden rounded-full" style={{ background: TRACK }}>
                  <div
                    className="h-full rounded-full"
                    style={{ width: `${Math.min(ratio, 1) * 100}%`, background: SERIES }}
                  />
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

export default function DashboardPage() {
  const [projectId, setProjectId] = useState<string>("");
  const { data: projects } = useQuery({
    queryKey: ["projects"],
    queryFn: () => api<Project[]>("/projects"),
  });
  const { data, isLoading, isError } = useQuery({
    queryKey: ["dashboard", projectId],
    queryFn: () =>
      api<DashboardSummary>(
        `/dashboard/summary${projectId ? `?project_id=${projectId}` : ""}`,
      ),
  });

  if (isLoading) return <Spinner />;
  if (isError || !data) return <ErrorState message="대시보드를 불러오지 못했습니다." />;

  const needsReview = data.status_counts.find((s) => s.status === "NEEDS_REVIEW");
  const { ai_metrics: ai, automation_effect: effect } = data;
  const monthly = data.monthly_approved.map((m) => ({
    month: m.month,
    amount: Number(m.approved_amount),
  }));

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold">대시보드</h1>
        <Select
          className="w-64"
          value={projectId}
          onChange={(e) => setProjectId(e.target.value)}
          aria-label="과제 필터"
        >
          <option value="">전체 과제</option>
          {projects?.map((p) => (
            <option key={p.id} value={p.id}>
              [{p.code}] {p.name}
            </option>
          ))}
        </Select>
      </div>

      {/* 지금 무엇부터 처리해야 하나 */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile
          label="검토 대기"
          value={`${needsReview?.count ?? 0}건`}
          hint={needsReview ? formatKrw(needsReview.amount) : undefined}
        />
        <StatTile
          label="AI 추출 성공률"
          value={formatPercent(ai.extraction_success_rate)}
          hint={`호출 ${ai.extraction_total}건`}
        />
        <StatTile
          label="AI 비목 제안 채택률"
          value={formatPercent(ai.suggestion_adoption_rate)}
          hint={`제안 ${ai.suggestion_total}건 · 사람 확정값과 일치 비율`}
        />
        <StatTile
          label="자동 검증 시간(중앙값)"
          value={
            effect.measured_pipeline_seconds_median != null
              ? `${effect.measured_pipeline_seconds_median}초`
              : "-"
          }
          hint={`수기 가정 ${effect.assumed_manual_minutes_per_case}분/건 대비 · ${effect.validated_cases}건 실측`}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <BudgetUsageCard data={data.budget_usage} />

        <Card title="상태별 현황">
          {data.status_counts.length === 0 ? (
            <EmptyState message="아직 집행 건이 없습니다." />
          ) : (
            <ul className="space-y-2 text-sm">
              {data.status_counts.map((s) => (
                <li key={s.status} className="flex justify-between border-b border-slate-100 pb-2">
                  <Link
                    href={`/expenses?status=${s.status}`}
                    className="text-slate-700 hover:underline"
                  >
                    {STATUS_LABELS[s.status]}
                  </Link>
                  <span className="text-slate-500">
                    {s.count}건 · {formatKrw(s.amount)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="월별 승인 금액">
          {monthly.length === 0 ? (
            <EmptyState message="승인된 집행이 없습니다." />
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={monthly} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" vertical={false} />
                <XAxis dataKey="month" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
                <YAxis
                  tick={{ fontSize: 11 }}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(v: number) => `${Math.round(v / 10000)}만`}
                />
                <Tooltip formatter={(v) => formatKrw(Number(v))} />
                <Bar dataKey="amount" name="승인 금액" fill={SERIES} radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </Card>

        <Card title="제출→승인 리드타임 (월별 중앙값)">
          {data.lead_time.length === 0 ? (
            <EmptyState message="아직 승인 이력이 없습니다." />
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={data.lead_time} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" vertical={false} />
                <XAxis dataKey="month" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
                <YAxis
                  tick={{ fontSize: 11 }}
                  tickLine={false}
                  axisLine={false}
                  unit="일"
                  width={40}
                />
                <Tooltip formatter={(v) => `${v}일`} />
                <Line
                  type="monotone"
                  dataKey="median_days"
                  name="리드타임"
                  stroke={SERIES}
                  strokeWidth={2}
                  dot={{ r: 3 }}
                />
              </LineChart>
            </ResponsiveContainer>
          )}
        </Card>
      </div>

      <Card title="자주 걸리는 검증 룰 Top 5 (최근 6개월)">
        {data.top_rules.length === 0 ? (
          <EmptyState message="위반 이력이 없습니다." />
        ) : (
          <ul className="space-y-2 text-sm">
            {data.top_rules.map((r) => (
              <li key={`${r.rule_code}-${r.severity}`} className="flex items-center gap-2">
                <SeverityBadge severity={r.severity} />
                <span className="font-mono text-xs text-slate-600">{r.rule_code}</span>
                <span className="ml-auto text-slate-500">{r.count}회</span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
