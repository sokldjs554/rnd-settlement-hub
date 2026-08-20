import type { BudgetCategory, ExpenseStatus, ValidationSeverity } from "./types";

export const CATEGORY_LABELS: Record<BudgetCategory, string> = {
  PERSONNEL: "인건비",
  STUDENT_PERSONNEL: "학생인건비",
  EQUIPMENT: "연구시설·장비비",
  MATERIAL: "연구재료비",
  ACTIVITY: "연구활동비",
  ALLOWANCE: "연구수당",
  OUTSOURCED_RND: "위탁연구개발비",
  INTL_JOINT_RND: "국제공동연구개발비",
  INDIRECT: "간접비",
};

export const STATUS_LABELS: Record<ExpenseStatus, string> = {
  DRAFT: "작성 중",
  SUBMITTED: "제출됨",
  VALIDATING: "검증 중",
  NEEDS_REVIEW: "검토 대기",
  APPROVED: "승인",
  REJECTED: "반려",
};

export const SEVERITY_LABELS: Record<ValidationSeverity, string> = {
  PASS: "통과",
  INFO: "참고",
  WARN: "주의",
  FAIL: "위반",
};

export function formatKrw(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return "-";
  const n = typeof value === "string" ? Number(value) : value;
  if (Number.isNaN(n)) return "-";
  return `${n.toLocaleString("ko-KR")}원`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "-";
  return iso.slice(0, 10);
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "-";
  const d = new Date(iso);
  return d.toLocaleString("ko-KR", { dateStyle: "short", timeStyle: "short" });
}

export function formatPercent(ratio: number | null | undefined): string {
  if (ratio === null || ratio === undefined) return "-";
  return `${Math.round(ratio * 1000) / 10}%`;
}
