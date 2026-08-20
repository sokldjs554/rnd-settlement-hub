import { SEVERITY_LABELS, STATUS_LABELS } from "@/lib/format";
import type { ExpenseStatus, ValidationSeverity } from "@/lib/types";
import { Badge } from "./ui";

const STATUS_TONES: Record<ExpenseStatus, "slate" | "green" | "yellow" | "red" | "blue"> = {
  DRAFT: "slate",
  SUBMITTED: "blue",
  VALIDATING: "blue",
  NEEDS_REVIEW: "yellow",
  APPROVED: "green",
  REJECTED: "red",
};

export function StatusBadge({ status }: { status: ExpenseStatus }) {
  return <Badge tone={STATUS_TONES[status]}>{STATUS_LABELS[status]}</Badge>;
}

const SEVERITY_TONES: Record<ValidationSeverity, "slate" | "green" | "yellow" | "red" | "blue"> = {
  PASS: "green",
  INFO: "blue",
  WARN: "yellow",
  FAIL: "red",
};

export function SeverityBadge({ severity }: { severity: ValidationSeverity }) {
  return <Badge tone={SEVERITY_TONES[severity]}>{SEVERITY_LABELS[severity]}</Badge>;
}
