"use client";

/** 집행 등록: 등록 → 증빙 업로드 → 제출(자동 검증 시작)까지 한 화면에서 수행한다. */

import { api, ApiError, upload } from "@/lib/api";
import type { Evidence, Expense, Project } from "@/lib/types";
import { ExpenseForm, type ExpenseFormValues } from "@/components/expense-form";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";

export default function NewExpensePage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [serverError, setServerError] = useState<string | null>(null);
  const [progress, setProgress] = useState<string | null>(null);

  const { data: projects } = useQuery({
    queryKey: ["projects"],
    queryFn: () => api<Project[]>("/projects"),
  });

  const submitAll = useMutation({
    mutationFn: async ({ values, files }: { values: ExpenseFormValues; files: File[] }) => {
      setProgress("집행 건 등록 중…");
      const expense = await api<Expense>("/expenses", {
        method: "POST",
        body: JSON.stringify({ ...values, vendor_biz_no: values.vendor_biz_no || null }),
      });
      for (const [index, file] of files.entries()) {
        setProgress(`증빙 업로드 중… (${index + 1}/${files.length})`);
        await upload<Evidence>(`/expenses/${expense.id}/evidences`, file);
      }
      setProgress("제출(자동 검증 시작) 중…");
      await api(`/expenses/${expense.id}/submit`, { method: "POST" });
      return expense;
    },
    onSuccess: (expense) => {
      queryClient.invalidateQueries({ queryKey: ["expenses"] });
      router.replace(`/expenses/${expense.id}`);
    },
    onError: (e) => {
      setProgress(null);
      setServerError(e instanceof ApiError ? e.message : "등록에 실패했습니다.");
    },
  });

  return (
    <div className="mx-auto max-w-xl space-y-4">
      <h1 className="text-lg font-bold">집행 등록</h1>
      <ExpenseForm
        mode="create"
        projects={projects}
        submitLabel="등록하고 제출"
        progress={progress}
        pending={submitAll.isPending}
        serverError={serverError}
        onSubmit={(values, files) => submitAll.mutate({ values, files })}
        onCancel={() => router.back()}
      />
    </div>
  );
}
