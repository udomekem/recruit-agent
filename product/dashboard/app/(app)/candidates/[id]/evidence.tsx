"use client";

import { useMemo, useState } from "react";

import type { ScoreCriterion } from "@/lib/api";
import { VERDICT_CLASS, VERDICT_LABEL } from "@/lib/format";
import { segments } from "@/lib/highlight";

type Answer = { key: string; value?: unknown; rule: string | null; outcome: string; note?: string };

function show(v: unknown): string {
  if (v === null || v === undefined) return "not answered";
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (typeof v === "object" && v && "text" in v) return String((v as { text: string }).text);
  return String(v);
}

export function Evidence({
  criteria,
  text,
  reasons,
  answers,
}: {
  criteria: ScoreCriterion[];
  text: string;
  reasons: string[];
  answers: Answer[];
}) {
  const [active, setActive] = useState<number | null>(null);
  const quotes = criteria.map((c) => (c.verdict === "not_met" ? null : c.quote));
  const segs = useMemo(() => segments(text, quotes), [text, quotes]);

  function focusQuote(n: number) {
    setActive(n);
    document.getElementById(`q-${n}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  const firstMark = new Set<number>();
  return (
    <div className="mt-6 grid gap-6 lg:grid-cols-2">
      <section aria-labelledby="evidence-h">
        <h2 id="evidence-h" className="text-lg font-semibold">Evidence</h2>
        <ul className="mt-2 space-y-1 text-sm">
          {reasons.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
        <table className="mt-3 w-full border-collapse text-sm">
          <caption className="sr-only">Each rubric criterion with the AI&apos;s judgement and the CV quote</caption>
          <thead>
            <tr className="border-b border-zinc-300 text-left dark:border-zinc-700">
              <th scope="col" className="py-1 pr-2">Criterion</th>
              <th scope="col" className="py-1 pr-2">Judgement</th>
              <th scope="col" className="py-1 pr-2">Evidence</th>
            </tr>
          </thead>
          <tbody>
            {criteria.map((c, n) => (
              <tr key={c.criterion_id} className="border-b border-zinc-200 align-top dark:border-zinc-800">
                <td className="py-2 pr-2">
                  {c.text}
                  <div className="text-xs text-zinc-700 dark:text-zinc-400">
                    {c.kind === "must_have" ? "must have" : "nice to have"} · weight {c.weight}
                  </div>
                </td>
                <td className={`py-2 pr-2 font-medium ${VERDICT_CLASS[c.verdict]}`}>
                  {VERDICT_LABEL[c.verdict]}
                </td>
                <td className="py-2 pr-2">
                  {c.reason}
                  {c.quote ? (
                    <button
                      type="button"
                      onClick={() => focusQuote(n)}
                      className="mt-1 block text-left text-blue-800 underline dark:text-blue-300"
                    >
                      &ldquo;{c.quote}&rdquo;
                      <span className="sr-only"> (show in the CV)</span>
                    </button>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        <h3 className="mt-5 font-semibold">Screening answers</h3>
        <table className="mt-1 w-full border-collapse text-sm">
          <caption className="sr-only">Screening answers and their rule outcome</caption>
          <thead>
            <tr className="border-b border-zinc-300 text-left dark:border-zinc-700">
              <th scope="col" className="py-1 pr-2">Question</th>
              <th scope="col" className="py-1 pr-2">Answer</th>
              <th scope="col" className="py-1 pr-2">Result</th>
            </tr>
          </thead>
          <tbody>
            {answers.map((a) => (
              <tr key={a.key} className="border-b border-zinc-200 dark:border-zinc-800">
                <td className="py-1 pr-2">{a.key.replaceAll("_", " ")}</td>
                <td className="py-1 pr-2">{show(a.value)}</td>
                <td className="py-1 pr-2">
                  {a.outcome.replaceAll("_", " ")}
                  {a.note && a.outcome !== "pass" ? ` (${a.note})` : ""}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section aria-labelledby="cv-h">
        <h2 id="cv-h" className="text-lg font-semibold">CV (personal details removed)</h2>
        {/* Rendered as text nodes only: the CV is candidate supplied and never treated as HTML. */}
        <div
          className="mt-2 max-h-[70vh] overflow-y-auto whitespace-pre-wrap rounded border border-zinc-300 bg-white p-3 font-mono text-xs leading-relaxed dark:border-zinc-700 dark:bg-zinc-900"
          tabIndex={0}
          aria-label="CV text"
        >
          {segs.map((s, i) => {
            if (!s.marks.length) return <span key={i}>{s.text}</span>;
            const n = s.marks[0];
            const first = !firstMark.has(n);
            firstMark.add(n);
            return (
              <mark
                key={i}
                id={first ? `q-${n}` : undefined}
                className={`quote${s.marks.includes(active ?? -1) ? " active" : ""}`}
              >
                {s.text}
              </mark>
            );
          })}
        </div>
      </section>
    </div>
  );
}
