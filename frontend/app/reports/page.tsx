"use client";

/** 정산보고서 목록 + 생성. */

import { api, ApiError } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { Project, Report } from "@/lib/types";
import {
  Badge,
  Button,
  Dialog,
  EmptyState,
  ErrorState,
  Input,
  Label,
  Select,
  Spinner,
  Table,
  Td,
  Th,
} from "@/components/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

export default function ReportsPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [form, setForm] = useState({ project_id: "", year: "2026", month: "" });
  const [error, setError] = useState<string | null>(null);

  const { data: projects } = useQuery({
    queryKey: ["projects"],
    queryFn: () => api<Project[]>("/projects"),
  });
  const { data: reports, isLoading, isError } = useQuery({
    queryKey: ["reports"],
    queryFn: () => api<Report[]>("/reports"),
  });

  const create = useMutation({
    mutationFn: () =>
      api<Report>(`/projects/${form.project_id}/reports`, {
        method: "POST",
        body: JSON.stringify({ year: Number(form.year), month: Number(form.month) }),
      }),
    onSuccess: (report) => {
      queryClient.invalidateQueries({ queryKey: ["reports"] });
      setCreateOpen(false);
      router.push(`/reports/${report.id}`);
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "생성에 실패했습니다."),
  });

  const projectName = (id: number) => {
    const p = projects?.find((p) => p.id === id);
    return p ? `[${p.code}] ${p.name}` : `#${id}`;
  };

  if (isLoading) return <Spinner />;
  if (isError) return <ErrorState message="보고서 목록을 불러오지 못했습니다." />;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold">정산보고서</h1>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus size={14} /> 월별 보고서 생성
        </Button>
      </div>

      {(!reports || reports.length === 0) && (
        <EmptyState message="생성된 보고서가 없습니다. 월별 보고서를 생성하면 비목별 집계와 AI 서술 초안이 준비됩니다." />
      )}

      {reports && reports.length > 0 && (
        <Table>
          <thead>
            <tr>
              <Th>기간</Th>
              <Th>과제</Th>
              <Th>상태</Th>
              <Th>생성일</Th>
              <Th>확정일</Th>
            </tr>
          </thead>
          <tbody>
            {reports.map((r) => (
              <tr
                key={r.id}
                className="cursor-pointer hover:bg-slate-50"
                onClick={() => router.push(`/reports/${r.id}`)}
              >
                <Td className="font-medium">
                  {r.period_year}년 {r.period_month}월
                </Td>
                <Td>{projectName(r.project_id)}</Td>
                <Td>
                  <Badge tone={r.status === "FINAL" ? "green" : "yellow"}>
                    {r.status === "FINAL" ? "확정" : "초안"}
                  </Badge>
                </Td>
                <Td>{formatDateTime(r.created_at)}</Td>
                <Td>{formatDateTime(r.finalized_at)}</Td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}

      <Dialog open={createOpen} title="월별 보고서 생성" onClose={() => setCreateOpen(false)}>
        <div className="space-y-3">
          <div>
            <Label htmlFor="report-project">과제</Label>
            <Select
              id="report-project"
              value={form.project_id}
              onChange={(e) => setForm((f) => ({ ...f, project_id: e.target.value }))}
            >
              <option value="" disabled>
                과제 선택
              </option>
              {projects?.map((p) => (
                <option key={p.id} value={p.id}>
                  [{p.code}] {p.name}
                </option>
              ))}
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label htmlFor="report-year">연도</Label>
              <Input
                id="report-year"
                type="number"
                value={form.year}
                onChange={(e) => setForm((f) => ({ ...f, year: e.target.value }))}
              />
            </div>
            <div>
              <Label htmlFor="report-month">월</Label>
              <Select
                id="report-month"
                value={form.month}
                onChange={(e) => setForm((f) => ({ ...f, month: e.target.value }))}
              >
                <option value="" disabled>
                  월 선택
                </option>
                {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
                  <option key={m} value={m}>
                    {m}월
                  </option>
                ))}
              </Select>
            </div>
          </div>
          <p className="text-xs text-slate-500">
            숫자 집계는 즉시 완성되고, AI 서술 초안은 잠시 후 자동으로 채워집니다.
          </p>
          {error && <ErrorState message={error} />}
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setCreateOpen(false)}>
              취소
            </Button>
            <Button
              disabled={!form.project_id || !form.month || create.isPending}
              onClick={() => create.mutate()}
            >
              {create.isPending ? "생성 중…" : "생성"}
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
}
