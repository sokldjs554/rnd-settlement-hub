"use client";

/**
 * 집행 건 수정 — 작성 중(DRAFT)·반려(REJECTED) 상태에서 작성자만 접근한다.
 * 반려 건을 수정하면 백엔드가 상태를 DRAFT로 되돌리므로, 저장 후 상세 화면에서 재제출하면 된다.
 */

import { api, ApiError } from "@/lib/api";
import type { ExpenseDetail, Project } from "@/lib/types";
import { ExpenseForm, type ExpenseFormValues } from "@/components/expense-form";
import { ErrorState, Spinner } from "@/components/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

export default function EditExpensePage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [serverError, setServerError] = useState<string | null>(null);

  const { data: projects } = useQuery({
    queryKey: ["projects"],
    queryFn: () => api<Project[]>("/projects"),
  });
  const { data: expense, isLoading, isError } = useQuery({
    queryKey: ["expense", id],
    queryFn: () => api<ExpenseDetail>(`/expenses/${id}`),
  });

  const save = useMutation({
    mutationFn: (form: ExpenseFormValues) =>
      api(`/expenses/${id}`, {
        method: "PATCH",
        // 과제(project_id)는 백엔드 수정 대상이 아니므로 보내지 않는다
        body: JSON.stringify({
          category: form.category,
          title: form.title,
          vendor_name: form.vendor_name,
          vendor_biz_no: form.vendor_biz_no || null,
          amount: form.amount,
          spent_at: form.spent_at,
        }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["expense", id] });
      queryClient.invalidateQueries({ queryKey: ["expenses"] });
      router.replace(`/expenses/${id}`);
    },
    onError: (e) => setServerError(e instanceof ApiError ? e.message : "저장에 실패했습니다."),
  });

  if (isLoading) return <Spinner />;
  if (isError || !expense) return <ErrorState message="집행 건을 불러오지 못했습니다." />;
  if (!["DRAFT", "REJECTED"].includes(expense.status)) {
    return <ErrorState message="작성 중이거나 반려된 건만 수정할 수 있습니다." />;
  }

  return (
    <div className="mx-auto max-w-xl space-y-4">
      <h1 className="text-lg font-bold">집행 건 수정</h1>
      {expense.status === "REJECTED" && expense.reject_reason && (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          반려 사유: {expense.reject_reason}
          <p className="mt-1 text-xs">수정해 저장하면 다시 제출할 수 있는 상태가 됩니다.</p>
        </div>
      )}
      <ExpenseForm
        mode="edit"
        projects={projects}
        defaultValues={{
          project_id: expense.project_id,
          category: expense.category,
          title: expense.title,
          vendor_name: expense.vendor_name,
          vendor_biz_no: expense.vendor_biz_no ?? "",
          amount: Number(expense.amount),
          spent_at: expense.spent_at,
        }}
        submitLabel="저장"
        pending={save.isPending}
        serverError={serverError}
        onSubmit={(values) => save.mutate(values)}
        onCancel={() => router.push(`/expenses/${id}`)}
      />
    </div>
  );
}
