import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SeverityBadge, StatusBadge } from "./badges";

describe("StatusBadge", () => {
  it("상태 코드를 한국어 라벨로 렌더링한다", () => {
    render(<StatusBadge status="NEEDS_REVIEW" />);
    expect(screen.getByText("검토 대기")).toBeInTheDocument();
  });
});

describe("SeverityBadge", () => {
  it("FAIL은 '위반' 라벨로 표시한다 (색상만으로 의미를 전달하지 않는다)", () => {
    render(<SeverityBadge severity="FAIL" />);
    expect(screen.getByText("위반")).toBeInTheDocument();
  });
  it("PASS는 '통과'로 표시한다", () => {
    render(<SeverityBadge severity="PASS" />);
    expect(screen.getByText("통과")).toBeInTheDocument();
  });
});
