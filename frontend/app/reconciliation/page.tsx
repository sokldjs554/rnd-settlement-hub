"use client";

/** 연구비카드 사용내역 대사 — CSV 업로드 + 과거 대사 이력.
 *
 * 카드사 연동(API)이 없는 현 단계에서, 담당자가 내려받은 사용내역 CSV를 올리면
 * 과제의 집행 건과 결정론적으로 대사한다. 업로드 즉시 결과 화면으로 이동한다.
 */

import { api, ApiError } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { Project, Reconciliation, ReconciliationDetail } from "@/lib/types";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  FieldError,
  Label,
  Select,
  Spinner,
  Table,
  Td,
  Th,
} from "@/components/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Upload } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

export default function ReconciliationPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [projectId, setProjectId] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data: projects } = useQuery({
    queryKey: ["projects"],
    queryFn: () => api<Project[]>("/projects"),
  });
  const { data: runs, isLoading, isError } = useQuery({
    queryKey: ["reconciliations"],
    queryFn: () => api<Reconciliation[]>("/reconciliations"),
  });

  const upload = useMutation({
    mutationFn: async () => {
      const file = fileRef.current?.files?.[0];
      if (!projectId) throw new ApiError(0, "FORM", "과제를 선택하세요.");
      if (!file) throw new ApiError(0, "FORM", "CSV 파일을 선택하세요.");
      const form = new FormData();
      form.append("file", file);
      return api<ReconciliationDetail>(`/projects/${projectId}/reconciliations`, {
        method: "POST",
        body: form,
      });
    },
    onSuccess: (recon) => {
      queryClient.invalidateQueries({ queryKey: ["reconciliations"] });
      router.push(`/reconciliation/${recon.id}`);
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "업로드에 실패했습니다."),
  });

  const projectName = (id: number) => {
    const p = projects?.find((p) => p.id === id);
    return p ? `[${p.code}] ${p.name}` : `#${id}`;
  };

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-bold">연구비카드 대사</h1>
        <p className="mt-1 text-sm text-slate-500">
          카드사에서 내려받은 사용내역 CSV를 업로드하면 과제의 집행 건과 자동 대사합니다.
          필수 컬럼: 승인일자 · 가맹점명 · 승인금액 (사업자번호가 있으면 정확도가 올라갑니다)
        </p>
      </div>

      <Card>
        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-56">
            <Label htmlFor="recon-project">과제</Label>
            <Select
              id="recon-project"
              value={projectId}
              onChange={(e) => setProjectId(e.target.value)}
            >
              <option value="">선택</option>
              {projects?.map((p) => (
                <option key={p.id} value={p.id}>
                  [{p.code}] {p.name}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <Label htmlFor="recon-file">사용내역 CSV</Label>
            <input
              id="recon-file"
              ref={fileRef}
              type="file"
              accept=".csv,text/csv"
              className="block text-sm text-slate-600 file:mr-3 file:rounded-md file:border-0 file:bg-slate-100 file:px-3 file:py-2 file:text-sm file:font-medium file:text-slate-700 hover:file:bg-slate-200"
            />
          </div>
          <Button onClick={() => { setError(null); upload.mutate(); }} disabled={upload.isPending}>
            <Upload size={14} /> {upload.isPending ? "대사 중…" : "업로드하고 대사"}
          </Button>
        </div>
        <FieldError message={error ?? undefined} />
      </Card>

      <h2 className="pt-2 text-sm font-semibold text-slate-700">대사 이력</h2>
      {isLoading && <Spinner />}
      {isError && <ErrorState message="대사 이력을 불러오지 못했습니다." />}
      {runs && runs.length === 0 && (
        <EmptyState message="아직 대사 이력이 없습니다. 사용내역 CSV를 업로드하면 결과가 여기에 쌓입니다." />
      )}
      {runs && runs.length > 0 && (
        <Table>
          <thead>
            <tr>
              <Th>업로드</Th>
              <Th>과제</Th>
              <Th>파일</Th>
              <Th className="text-right">카드 라인</Th>
              <Th className="text-right">일치</Th>
              <Th className="text-right">확인 필요</Th>
              <Th className="text-right">대응 없음</Th>
            </tr>
          </thead>
          <tbody>
            {runs.map((r) => (
              <tr key={r.id} className="hover:bg-slate-50">
                <Td>
                  <Link className="text-blue-700 hover:underline" href={`/reconciliation/${r.id}`}>
                    {formatDateTime(r.created_at)}
                  </Link>
                </Td>
                <Td>{projectName(r.project_id)}</Td>
                <Td>{r.file_name}</Td>
                <Td className="text-right tabular-nums">{r.total_lines}</Td>
                <Td className="text-right tabular-nums">{r.matched_count}</Td>
                <Td className="text-right tabular-nums">
                  {r.matched_near_count + r.candidate_count}
                </Td>
                <Td className="text-right tabular-nums">{r.unmatched_count}</Td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </div>
  );
}
