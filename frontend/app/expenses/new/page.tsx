"use client";

/** 집행 등록: 폼 검증(zod) → 등록 → 증빙 업로드 → 제출까지 한 화면에서. */

import { api, ApiError, upload } from "@/lib/api";
import { CATEGORY_LABELS } from "@/lib/format";
import type { Evidence, Expense, Project } from "@/lib/types";
import {
  Button,
  Card,
  ErrorState,
  FieldError,
  Input,
  Label,
  Select,
} from "@/components/ui";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

const schema = z.object({
  project_id: z.coerce.number({ message: "과제를 선택하세요" }).int().positive("과제를 선택하세요"),
  category: z.string().min(1, "비목을 선택하세요"),
  title: z.string().min(1, "제목을 입력하세요").max(255),
  vendor_name: z.string().min(1, "거래처명을 입력하세요").max(255),
  vendor_biz_no: z
    .string()
    .regex(/^[\d-]*$/, "숫자와 하이픈만 입력하세요")
    .optional()
    .or(z.literal("")),
  amount: z.coerce.number({ message: "금액을 입력하세요" }).int("원 단위 정수").positive("0보다 커야 합니다"),
  spent_at: z.string().min(1, "집행일을 선택하세요"),
});
type FormValues = z.infer<typeof schema>;

export default function NewExpensePage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [files, setFiles] = useState<File[]>([]);
  const [serverError, setServerError] = useState<string | null>(null);
  const [progress, setProgress] = useState<string | null>(null);

  const { data: projects } = useQuery({
    queryKey: ["projects"],
    queryFn: () => api<Project[]>("/projects"),
  });

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  const submitAll = useMutation({
    mutationFn: async (values: FormValues) => {
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
      <Card>
        <form
          onSubmit={handleSubmit((values) => submitAll.mutate(values))}
          className="space-y-4"
          noValidate
        >
          <div>
            <Label htmlFor="project_id">과제</Label>
            <Select id="project_id" defaultValue="" {...register("project_id")}>
              <option value="" disabled>
                과제 선택
              </option>
              {projects?.map((p) => (
                <option key={p.id} value={p.id}>
                  [{p.code}] {p.name}
                </option>
              ))}
            </Select>
            <FieldError message={errors.project_id?.message} />
          </div>

          <div>
            <Label htmlFor="category">비목 (AI가 검증 후 다른 비목을 제안할 수 있습니다)</Label>
            <Select id="category" defaultValue="" {...register("category")}>
              <option value="" disabled>
                비목 선택
              </option>
              {Object.entries(CATEGORY_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
            <FieldError message={errors.category?.message} />
          </div>

          <div>
            <Label htmlFor="title">제목</Label>
            <Input id="title" placeholder="예: 시약 및 배양배지 구입" {...register("title")} />
            <FieldError message={errors.title?.message} />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label htmlFor="vendor_name">거래처명</Label>
              <Input id="vendor_name" {...register("vendor_name")} />
              <FieldError message={errors.vendor_name?.message} />
            </div>
            <div>
              <Label htmlFor="vendor_biz_no">사업자등록번호</Label>
              <Input id="vendor_biz_no" placeholder="123-45-67890" {...register("vendor_biz_no")} />
              <FieldError message={errors.vendor_biz_no?.message} />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label htmlFor="amount">금액(원)</Label>
              <Input id="amount" type="number" min={1} {...register("amount")} />
              <FieldError message={errors.amount?.message} />
            </div>
            <div>
              <Label htmlFor="spent_at">집행일</Label>
              <Input id="spent_at" type="date" {...register("spent_at")} />
              <FieldError message={errors.spent_at?.message} />
            </div>
          </div>

          <div>
            <Label htmlFor="evidence">증빙 파일 (PDF/JPG/PNG, 10MB 이하)</Label>
            <input
              id="evidence"
              type="file"
              multiple
              accept="application/pdf,image/jpeg,image/png"
              className="block w-full text-sm text-slate-600 file:mr-3 file:rounded-md file:border-0 file:bg-slate-100 file:px-3 file:py-2 file:text-sm file:font-medium"
              onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
            />
            <p className="mt-1 text-xs text-slate-400">
              제출하면 AI가 증빙을 읽어 입력값과 자동 대조합니다. 증빙 없이 제출하면 검증에서
              위반(FAIL)으로 표시됩니다.
            </p>
          </div>

          {serverError && <ErrorState message={serverError} />}

          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={() => router.back()}>
              취소
            </Button>
            <Button type="submit" disabled={isSubmitting || submitAll.isPending}>
              {progress ?? "등록하고 제출"}
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
}
