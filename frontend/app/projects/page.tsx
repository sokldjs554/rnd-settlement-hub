"use client";

/** 과제·비목 예산 현황. ADMIN은 새 과제를 등록할 수 있다. */

import { api, ApiError } from "@/lib/api";
import { CATEGORY_LABELS, formatDate, formatKrw } from "@/lib/format";
import { useCurrentUser } from "@/lib/providers";
import type { BudgetCategory, Project } from "@/lib/types";
import {
  Badge,
  Button,
  Card,
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
import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";

interface BudgetRow {
  category: BudgetCategory | "";
  amount: string;
}

function CreateProjectDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({
    code: "",
    name: "",
    agency: "",
    start_date: "",
    end_date: "",
  });
  const [budgets, setBudgets] = useState<BudgetRow[]>([{ category: "MATERIAL", amount: "" }]);
  const [error, setError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: () =>
      api<Project>("/projects", {
        method: "POST",
        body: JSON.stringify({
          ...form,
          budgets: budgets
            .filter((b) => b.category && b.amount)
            .map((b) => ({ category: b.category, amount: Number(b.amount) })),
        }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      onClose();
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "등록에 실패했습니다."),
  });

  const setField = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));

  return (
    <Dialog open={open} title="과제 등록" onClose={onClose}>
      <div className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label>과제번호</Label>
            <Input value={form.code} onChange={setField("code")} placeholder="P-2026-001" />
          </div>
          <div>
            <Label>전문기관</Label>
            <Input value={form.agency} onChange={setField("agency")} />
          </div>
        </div>
        <div>
          <Label>과제명</Label>
          <Input value={form.name} onChange={setField("name")} />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label>연구 시작일</Label>
            <Input type="date" value={form.start_date} onChange={setField("start_date")} />
          </div>
          <div>
            <Label>연구 종료일</Label>
            <Input type="date" value={form.end_date} onChange={setField("end_date")} />
          </div>
        </div>
        <div>
          <Label>비목 예산</Label>
          <div className="space-y-2">
            {budgets.map((row, i) => (
              <div key={i} className="flex gap-2">
                <Select
                  value={row.category}
                  onChange={(e) =>
                    setBudgets((rows) =>
                      rows.map((r, j) =>
                        j === i ? { ...r, category: e.target.value as BudgetCategory } : r,
                      ),
                    )
                  }
                >
                  {Object.entries(CATEGORY_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </Select>
                <Input
                  type="number"
                  placeholder="금액(원)"
                  value={row.amount}
                  onChange={(e) =>
                    setBudgets((rows) =>
                      rows.map((r, j) => (j === i ? { ...r, amount: e.target.value } : r)),
                    )
                  }
                />
                <Button
                  variant="ghost"
                  type="button"
                  onClick={() => setBudgets((rows) => rows.filter((_, j) => j !== i))}
                  aria-label="비목 삭제"
                >
                  <Trash2 size={14} />
                </Button>
              </div>
            ))}
          </div>
          <Button
            variant="secondary"
            type="button"
            className="mt-2"
            onClick={() => setBudgets((rows) => [...rows, { category: "", amount: "" }])}
          >
            <Plus size={14} /> 비목 추가
          </Button>
        </div>
        {error && <ErrorState message={error} />}
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            취소
          </Button>
          <Button disabled={create.isPending} onClick={() => create.mutate()}>
            {create.isPending ? "등록 중…" : "등록"}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}

export default function ProjectsPage() {
  const user = useCurrentUser();
  const [createOpen, setCreateOpen] = useState(false);
  const { data: projects, isLoading, isError } = useQuery({
    queryKey: ["projects"],
    queryFn: () => api<Project[]>("/projects"),
  });

  if (isLoading) return <Spinner />;
  if (isError) return <ErrorState message="과제 목록을 불러오지 못했습니다." />;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold">과제·예산</h1>
        {user?.role === "ADMIN" && (
          <Button onClick={() => setCreateOpen(true)}>
            <Plus size={14} /> 과제 등록
          </Button>
        )}
      </div>

      {(!projects || projects.length === 0) && (
        <EmptyState message="등록된 과제가 없습니다. 관리자가 과제와 비목 예산을 등록해야 집행을 시작할 수 있습니다." />
      )}

      {projects?.map((project) => (
        <Card
          key={project.id}
          title={
            <span>
              <span className="mr-2 font-mono text-xs text-slate-400">{project.code}</span>
              {project.name}
            </span>
          }
          actions={
            <div className="flex items-center gap-2 text-xs text-slate-500">
              <span>
                {formatDate(project.start_date)} ~ {formatDate(project.end_date)}
              </span>
              <Badge tone={project.status === "ACTIVE" ? "green" : "slate"}>
                {project.status === "ACTIVE" ? "진행 중" : "종료"}
              </Badge>
            </div>
          }
        >
          <p className="mb-2 text-xs text-slate-500">전문기관: {project.agency}</p>
          <Table>
            <thead>
              <tr>
                <Th>비목</Th>
                <Th className="text-right">예산</Th>
                <Th className="text-right">승인 집행</Th>
                <Th className="text-right">잔액</Th>
              </tr>
            </thead>
            <tbody>
              {project.budgets.map((b) => (
                <tr key={b.category}>
                  <Td>{CATEGORY_LABELS[b.category]}</Td>
                  <Td className="text-right">{formatKrw(b.budget)}</Td>
                  <Td className="text-right">{formatKrw(b.approved)}</Td>
                  <Td
                    className={
                      Number(b.remaining) < 0
                        ? "text-right font-semibold text-red-700"
                        : "text-right"
                    }
                  >
                    {formatKrw(b.remaining)}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Card>
      ))}

      <CreateProjectDialog open={createOpen} onClose={() => setCreateOpen(false)} />
    </div>
  );
}
