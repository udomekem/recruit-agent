import { describe, expect, it } from "vitest";

import { findQuotes, segments } from "./highlight";

const CV = "Experience\nSenior Data Analyst, Coral   Ledger\n- Wrote SQL queries\nSkills: SQL, Python";

describe("findQuotes", () => {
  it("finds quotes across line breaks and extra spaces, ignoring case", () => {
    const [r] = findQuotes(CV, ["senior data analyst, coral ledger"]);
    expect(r).not.toBeNull();
    expect(CV.slice(r![0], r![1])).toBe("Senior Data Analyst, Coral   Ledger");
  });

  it("returns null for missing or empty quotes", () => {
    expect(findQuotes(CV, ["Kubernetes", "", null])).toEqual([null, null, null]);
  });

  it("uses the first match when a quote appears twice", () => {
    const [r] = findQuotes(CV, ["SQL"]);
    expect(CV.slice(0, r![0])).not.toContain("SQL");
  });
});

describe("segments", () => {
  it("rebuilds the exact text and marks covered runs", () => {
    const segs = segments(CV, ["Wrote SQL queries", "SQL, Python"]);
    expect(segs.map((s) => s.text).join("")).toBe(CV);
    expect(segs.find((s) => s.text === "Wrote SQL queries")?.marks).toEqual([0]);
    expect(segs.find((s) => s.text === "SQL, Python")?.marks).toEqual([1]);
  });

  it("keeps markup in the CV as plain text", () => {
    const evil = "<img src=x onerror=alert(1)> Wrote SQL";
    const segs = segments(evil, ["Wrote SQL"]);
    expect(segs[0].text).toBe("<img src=x onerror=alert(1)> ");
  });
});
