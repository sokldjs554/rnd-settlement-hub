/** 백엔드 API 응답 타입 (backend/app/schemas와 1:1 대응) */

export type UserRole = "RESEARCHER" | "MANAGER" | "ADMIN";

export type BudgetCategory =
  | "PERSONNEL"
  | "STUDENT_PERSONNEL"
  | "EQUIPMENT"
  | "MATERIAL"
  | "ACTIVITY"
  | "ALLOWANCE"
  | "OUTSOURCED_RND"
  | "INTL_JOINT_RND"
  | "INDIRECT";

export type ExpenseStatus =
  | "DRAFT"
  | "SUBMITTED"
  | "VALIDATING"
  | "NEEDS_REVIEW"
  | "APPROVED"
  | "REJECTED";

export type ValidationSeverity = "PASS" | "INFO" | "WARN" | "FAIL";

export interface User {
  id: number;
  email: string;
  name: string;
  role: UserRole;
}

export interface LoginResponse {
  access_token: string;
  user: User;
}

export interface BudgetSummary {
  category: BudgetCategory;
  budget: string; // 서버가 Decimal을 문자열로 직렬화한다
  approved: string;
  remaining: string;
}

export interface Project {
  id: number;
  code: string;
  name: string;
  agency: string;
  start_date: string;
  end_date: string;
  status: "ACTIVE" | "CLOSED";
  budgets: BudgetSummary[];
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
}

export interface Expense {
  id: number;
  project_id: number;
  category: BudgetCategory;
  title: string;
  vendor_name: string;
  vendor_biz_no: string | null;
  purpose: string | null; // 사용 용도 — 비목 판단 근거
  amount: string;
  spent_at: string;
  status: ExpenseStatus;
  reject_reason: string | null;
  report_id: number | null;
  created_by: number;
  created_at: string;
  updated_at: string;
}

export interface ExpenseListItem extends Expense {
  project_code: string;
  created_by_name: string;
  worst_severity: ValidationSeverity | null;
}

export interface Evidence {
  id: number;
  file_name: string;
  mime_type: string;
  size_bytes: number;
  created_at: string;
}

export interface AiExtraction {
  status: "SUCCESS" | "FAILED";
  doc_type: string | null;
  vendor_name: string | null;
  biz_no: string | null;
  total_amount: string | null;
  issued_at: string | null;
  confidence: string | null;
  error: string | null;
}

export interface AiSuggestion {
  status: "SUCCESS" | "FAILED";
  category: BudgetCategory | null;
  confidence: string | null;
  rationale: string | null;
}

export interface ValidationResult {
  rule_code: string;
  severity: ValidationSeverity;
  message: string;
  detail: Record<string, unknown> | null;
}

export interface Approval {
  action: "APPROVE" | "REJECT";
  override: boolean;
  comment: string | null;
  actor: { id: number; name: string };
  created_at: string;
}

export interface ExpenseDetail extends Expense {
  project_code: string;
  created_by_name: string;
  evidences: Evidence[];
  ai: { extraction: AiExtraction | null; category_suggestion: AiSuggestion | null };
  validations: ValidationResult[];
  approvals: Approval[];
}

export interface HistoryEvent {
  at: string;
  type: string;
  actor: string | null;
  data: Record<string, unknown> | null;
}

export interface Report {
  id: number;
  project_id: number;
  period_year: number;
  period_month: number;
  status: "DRAFT" | "FINAL";
  generated_by: number;
  finalized_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ReportDetail extends Report {
  summary_json: ReportSummary | null;
  narrative_md: string | null;
}

export interface ReportSummary {
  period: { year: number; month: number };
  categories: {
    category: BudgetCategory;
    label: string;
    budget: number;
    month_approved: number;
    cumulative_approved: number;
    remaining: number;
  }[];
  totals: {
    budget: number;
    month_approved: number;
    cumulative_approved: number;
    remaining: number;
  };
  counts: {
    month_approved_count: number;
    month_rejected_count: number;
    pending_review_count: number;
    month_override_count: number;
  };
}

export interface DashboardSummary {
  budget_usage: {
    category: BudgetCategory;
    label: string;
    budget: string;
    approved: string;
    remaining: string;
  }[];
  status_counts: { status: ExpenseStatus; count: number; amount: string }[];
  top_rules: { rule_code: string; severity: ValidationSeverity; count: number }[];
  lead_time: { month: string; median_days: number }[];
  monthly_approved: { month: string; approved_amount: string }[];
  ai_metrics: {
    extraction_total: number;
    extraction_success_rate: number | null;
    suggestion_total: number;
    suggestion_adoption_rate: number | null;
  };
  automation_effect: {
    assumed_manual_minutes_per_case: number;
    measured_pipeline_seconds_median: number | null;
    validated_cases: number;
  };
}

export interface Notification {
  id: number;
  type: string;
  payload: Record<string, unknown>;
  read_at: string | null;
  created_at: string;
}

export interface ApiErrorBody {
  error: { code: string; message: string; detail?: unknown };
}
