import { describe, expect, it } from "vitest";
import { formatDate, formatKrw, formatPercent } from "./format";

describe("formatKrw", () => {
  it("문자열 Decimal(서버 직렬화)을 원화로 표기한다", () => {
    expect(formatKrw("1234567")).toBe("1,234,567원");
    expect(formatKrw(0)).toBe("0원");
  });
  it("없는 값은 대시로 표기한다", () => {
    expect(formatKrw(null)).toBe("-");
    expect(formatKrw(undefined)).toBe("-");
    expect(formatKrw("abc")).toBe("-");
  });
});

describe("formatDate / formatPercent", () => {
  it("ISO 문자열의 날짜 부분만 남긴다", () => {
    expect(formatDate("2026-03-10T02:11:00Z")).toBe("2026-03-10");
    expect(formatDate(null)).toBe("-");
  });
  it("비율을 소수점 한 자리 %로 표기한다", () => {
    expect(formatPercent(0.913)).toBe("91.3%");
    expect(formatPercent(1)).toBe("100%");
    expect(formatPercent(null)).toBe("-");
  });
});
