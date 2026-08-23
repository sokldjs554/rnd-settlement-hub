"use client";

/** 집행 건 목록 — 검색·필터·정렬·페이지네이션 + 리스크 배지. */

import { api } from "@/lib/api";
import { CATEGORY_LABELS, formatDate, formatKrw, STATUS_LABELS } from "@/lib/format";
import type { ExpenseListItem, Page, Project } from "@/lib/types";
import { SeverityBadge, StatusBadge } from "@/components/badges";
import {
  Button,
  EmptyState,
  ErrorState,
  Input,
  Select,
  Spinner,
  Table,
  Td,
  Th,
} from "@/components/ui";
import { useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

function buildQuery(params: Record<string, string | number | undefined>): string {
  const sp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") sp.set(key, String(value));
  }
  return sp.toString();
}

function ExpenseListInner() {
  const router = useRouter();
  const searchParams = useSearchParams();

  // 목록 상태(페이지·필터·정렬)의 단일 출처는 URL이다. useState에 두면 상세 화면에
  // 다녀올 때 목록이 새로 마운트되면서 초기값으로 돌아간다 — 2페이지에서 한 건을 열고
  // 뒤로가기 하면 1페이지가 되던 문제.
  const page = Math.max(1, Number(searchParams.get("page")) || 1);
  const q = searchParams.get("q") ?? "";
  const status = searchParams.get("status") ?? "";
  const projectId = searchParams.get("project_id") ?? "";
  const sort = searchParams.get("sort") ?? "-created_at";

  // 검색어 입력창만 로컬 상태다(타이핑 중에는 URL을 건드리지 않는다).
  // 뒤로가기로 q가 바뀌어 들어오면 입력창도 따라간다.
  const [qInput, setQInput] = useState(q);
  useEffect(() => setQInput(q), [q]);

  /**
   * URL 쿼리를 갱신한다. 명시하지 않은 키는 유지되고, 빈 값은 URL에서 지운다.
   *
   * - 필터·정렬 변경은 replace: 조건을 다듬는 행위라 히스토리에 쌓지 않는다
   *   (쌓으면 뒤로가기가 필터 조작을 한 단계씩 되짚게 된다).
   * - 페이지 이동은 push: 사용자가 뒤로가기로 되돌릴 것을 기대하는 이동이다.
   */
  const updateParams = (
    patch: Record<string, string | number | undefined>,
    { push = false } = {},
  ) => {
    const sp = new URLSearchParams(searchParams.toString());
    for (const [key, value] of Object.entries(patch)) {
      if (value === undefined || value === "") sp.delete(key);
      else sp.set(key, String(value));
    }
    const qs = sp.toString();
    if (push) router.push(qs ? `/expenses?${qs}` : "/expenses");
    else router.replace(qs ? `/expenses?${qs}` : "/expenses");
  };

  const { data: projects } = useQuery({
    queryKey: ["projects"],
    queryFn: () => api<Project[]>("/projects"),
  });

  const query = buildQuery({ page, size: 20, sort, q, status, project_id: projectId });
  const { data, isLoading, isError } = useQuery({
    queryKey: ["expenses", query],
    queryFn: () => api<Page<ExpenseListItem>>(`/expenses?${query}`),
  });

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.size)) : 1;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold">집행 건</h1>
        <Button onClick={() => router.push("/expenses/new")}>
          <Plus size={14} /> 집행 등록
        </Button>
      </div>

      {/* 필터 바 */}
      <form
        className="flex flex-wrap gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          updateParams({ q: qInput, page: undefined });
        }}
      >
        <Input
          className="w-56"
          placeholder="제목·거래처 검색"
          value={qInput}
          onChange={(e) => setQInput(e.target.value)}
        />
        <Select
          className="w-36"
          value={status}
          onChange={(e) => updateParams({ status: e.target.value, page: undefined })}
          aria-label="상태 필터"
        >
          <option value="">모든 상태</option>
          {Object.entries(STATUS_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </Select>
        <Select
          className="w-56"
          value={projectId}
          onChange={(e) => updateParams({ project_id: e.target.value, page: undefined })}
          aria-label="과제 필터"
        >
          <option value="">모든 과제</option>
          {projects?.map((p) => (
            <option key={p.id} value={p.id}>
              [{p.code}] {p.name}
            </option>
          ))}
        </Select>
        <Select
          className="w-40"
          value={sort}
          onChange={(e) => updateParams({ sort: e.target.value, page: undefined })}
          aria-label="정렬"
        >
          <option value="-created_at">최신 등록순</option>
          <option value="-spent_at">집행일 내림차순</option>
          <option value="spent_at">집행일 오름차순</option>
          <option value="-amount">금액 큰 순</option>
        </Select>
        <Button type="submit" variant="secondary">
          검색
        </Button>
      </form>

      {isLoading && <Spinner />}
      {isError && <ErrorState message="목록을 불러오지 못했습니다." />}
      {data && data.items.length === 0 && (
        <EmptyState message="조건에 맞는 집행 건이 없습니다. 우측 상단에서 새 집행을 등록하세요." />
      )}

      {data && data.items.length > 0 && (
        <>
          <Table>
            <thead>
              <tr>
                <Th>제목</Th>
                <Th>과제</Th>
                <Th>비목</Th>
                <Th>거래처</Th>
                <Th className="text-right">금액</Th>
                <Th>집행일</Th>
                <Th>상태</Th>
                <Th>리스크</Th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((e) => (
                <tr
                  key={e.id}
                  className="cursor-pointer hover:bg-slate-50"
                  onClick={() => router.push(`/expenses/${e.id}`)}
                >
                  <Td>
                    <Link
                      href={`/expenses/${e.id}`}
                      className="font-medium text-slate-800"
                      onClick={(ev) => ev.stopPropagation()}
                    >
                      {e.title}
                    </Link>
                    <p className="text-xs text-slate-400">{e.created_by_name}</p>
                  </Td>
                  <Td className="font-mono text-xs">{e.project_code}</Td>
                  <Td>{CATEGORY_LABELS[e.category]}</Td>
                  <Td>{e.vendor_name}</Td>
                  <Td className="text-right font-medium">{formatKrw(e.amount)}</Td>
                  <Td>{formatDate(e.spent_at)}</Td>
                  <Td>
                    <StatusBadge status={e.status} />
                  </Td>
                  <Td>{e.worst_severity ? <SeverityBadge severity={e.worst_severity} /> : "-"}</Td>
                </tr>
              ))}
            </tbody>
          </Table>

          <div className="flex items-center justify-between text-sm text-slate-500">
            <span>총 {data.total}건</span>
            <div className="flex items-center gap-2">
              <Button
                variant="secondary"
                disabled={page <= 1}
                onClick={() => updateParams({ page: page - 1 }, { push: true })}
              >
                이전
              </Button>
              <span>
                {page} / {totalPages}
              </span>
              <Button
                variant="secondary"
                disabled={page >= totalPages}
                onClick={() => updateParams({ page: page + 1 }, { push: true })}
              >
                다음
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export default function ExpenseListPage() {
  return (
    <Suspense fallback={<Spinner />}>
      <ExpenseListInner />
    </Suspense>
  );
}
