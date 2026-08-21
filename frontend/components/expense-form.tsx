"use client";

/**
 * 집행 건 입력 폼 — 등록(create)과 수정(edit) 화면이 공유한다.
 *
 * 두 화면의 차이:
 * - create: 과제 선택 가능, 증빙 파일 첨부, 저장 후 곧바로 제출까지 수행
 * - edit:   과제는 변경 불가(백엔드 ExpenseUpdate에 없음)이라 읽기 전용으로 보여주고,
 *           증빙은 이미 첨부된 것을 상세 화면에서 확인하므로 여기서는 다루지 않는다
 */

import { CATEGORY_LABELS } from "@/lib/format";
import type { Project } from "@/lib/types";
import { Button, Card, ErrorState, FieldError, Input, Label, Select } from "@/components/ui";
import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

export const expenseSchema = z.object({
  project_id: z.coerce.number({ message: "과제를 선택하세요" }).int().positive("과제를 선택하세요"),
  category: z.string().min(1, "비목을 선택하세요"),
  title: z.string().min(1, "제목을 입력하세요").max(255),
  vendor_name: z.string().min(1, "거래처명을 입력하세요").max(255),
  vendor_biz_no: z
    .string()
    .regex(/^[\d-]*$/, "숫자와 하이픈만 입력하세요")
    .optional()
    .or(z.literal("")),
  amount: z.coerce
    .number({ message: "금액을 입력하세요" })
    .int("원 단위 정수")
    .positive("0보다 커야 합니다"),
  spent_at: z.string().min(1, "집행일을 선택하세요"),
});

export type ExpenseFormValues = z.infer<typeof expenseSchema>;

interface Props {
  mode: "create" | "edit";
  projects: Project[] | undefined;
  defaultValues?: Partial<ExpenseFormValues>;
  submitLabel: string;
  /** 진행 중 문구(있으면 버튼 라벨을 대체) */
  progress?: string | null;
  pending: boolean;
  serverError: string | null;
  onSubmit: (values: ExpenseFormValues, files: File[]) => void;
  onCancel: () => void;
}

export function ExpenseForm({
  mode,
  projects,
  defaultValues,
  submitLabel,
  progress,
  pending,
  serverError,
  onSubmit,
  onCancel,
}: Props) {
  const [files, setFiles] = useState<File[]>([]);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ExpenseFormValues>({ resolver: zodResolver(expenseSchema), defaultValues });

  return (
    <Card>
      <form
        onSubmit={handleSubmit((values) => onSubmit(values, files))}
        className="space-y-4"
        noValidate
      >
        <div>
          <Label htmlFor="project_id">과제{mode === "edit" && " (변경 불가)"}</Label>
          <Select
            id="project_id"
            defaultValue={defaultValues?.project_id ?? ""}
            disabled={mode === "edit"}
            {...register("project_id")}
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
          <FieldError message={errors.project_id?.message} />
        </div>

        <div>
          <Label htmlFor="category">비목 (AI가 검증 후 다른 비목을 제안할 수 있습니다)</Label>
          <Select id="category" defaultValue={defaultValues?.category ?? ""} {...register("category")}>
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

        {mode === "create" && (
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
        )}

        {serverError && <ErrorState message={serverError} />}

        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onCancel}>
            취소
          </Button>
          <Button type="submit" disabled={isSubmitting || pending}>
            {progress ?? submitLabel}
          </Button>
        </div>
      </form>
    </Card>
  );
}
