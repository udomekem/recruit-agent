"use client";

import { useEffect, useMemo, useState } from "react";

import type { Audit, Rejection, ScoreCriterion } from "@/lib/api";
import { stateLabel, VERDICT_LABEL, when } from "@/lib/format";
import { segments } from "@/lib/highlight";

import { RejectionPanel } from "./rejection-panel";

type Answer = { key: string; value?: unknown; rule: string | null; outcome: string; note?: string };
type Tab = "requirements" | "cv" | "email" | "activity";

function show(v: unknown): string {
  if (v === null || v === undefined) return "not answered";
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (typeof v === "object" && v && "text" in v) return String((v as { text: string }).text);
  return String(v);
}

const ORDER: Record<string, number> = { not_met: 0, partly_met: 1, met: 2 };

/** The review panel's tabs (phase 5B UI design): Requirements, CV, Rejection email,
 * Activity. Only the open tab is in the page. Candidate text is rendered as text only. */
export function ReviewTabs(props: {
  candidateId: string;
  state: string;
  version: number;
  criteria: ScoreCriterion[] | null;
  reasons: string[];
  answers: Answer[];
  text: string;
  meta: string | null;
  audit: Audit[];
  access: { what: string; actor_id: string; at: string }[];
  rejection: Rejection | null;
  emailTab: boolean;
}) {
  const [tab, setTab] = useState<Tab>(props.emailTab ? "email" : "requirements");
  const [active, setActive] = useState<number | null>(null);
  const criteria = useMemo(() => props.criteria ?? [], [props.criteria]);
  const quotes = useMemo(() => criteria.map((c) => (c.verdict === "not_met" ? null : c.quote)), [criteria]);
  const segs = useMemo(() => segments(props.text, quotes), [props.text, quotes]);

  useEffect(() => {
    if (tab === "cv" && active !== null) {
      document.getElementById(`q-${active}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [tab, active]);

  const tabs: [Tab, string][] = [
    ["requirements", "Requirements"],
    ["cv", "CV"],
    ...(props.emailTab ? ([["email", "Rejection email"]] as [Tab, string][]) : []),
    ["activity", "Activity"],
  ];

  const firstMark = new Set<number>();
  const sorted = criteria
    .map((c, n) => ({ c, n }))
    .sort((a, b) => (ORDER[a.c.verdict] ?? 3) - (ORDER[b.c.verdict] ?? 3));

  return (
    <>
      <div className="h-tabs" role="tablist" aria-label="Candidate details" style={{ margin: "0 27px" }}>
        {tabs.map(([k, label]) => (
          <button
            key={k}
            type="button"
            role="tab"
            id={`tab-${k}`}
            aria-selected={tab === k}
            aria-controls={`panel-${k}`}
            className="h-tab"
            onClick={() => setTab(k)}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="h-panel" role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
        {tab === "requirements" ? (
          props.criteria ? (
            <section aria-labelledby="evidence-h">
              <h2 id="evidence-h" className="h-panel-title">
                Evidence
              </h2>
              <p className="h-note">
                Each verdict quotes the CV line it came from. Select a quote to see it in the CV.
              </p>
              {props.reasons.length ? (
                <ul style={{ margin: "0 0 8px", paddingLeft: 18, fontSize: 13 }}>
                  {props.reasons.map((r) => (
                    <li key={r}>{r}</li>
                  ))}
                </ul>
              ) : null}
              <h3 className="h-section">Requirements</h3>
              {sorted.map(({ c, n }) => (
                <div key={c.criterion_id} className="h-req">
                  <span className="h-verdict" data-v={c.verdict}>
                    {VERDICT_LABEL[c.verdict]}
                  </span>
                  <div>
                    <span className="h-rq">{c.text}</span>
                    <span className="h-rk">
                      {c.kind === "must_have" ? "Must have" : "Nice to have"} · weight {c.weight}
                    </span>
                    {c.reason ? <p className="h-why">{c.reason}</p> : null}
                    {c.quote ? (
                      <button
                        type="button"
                        className="h-quote"
                        onClick={() => {
                          setActive(n);
                          setTab("cv");
                        }}
                      >
                        &ldquo;{c.quote}&rdquo;
                        <span className="sr-only"> (show in the CV)</span>
                      </button>
                    ) : null}
                  </div>
                </div>
              ))}
              <h3 className="h-section">Screening answers</h3>
              <table className="h-answers">
                <caption className="sr-only">Screening answers and their rule outcome</caption>
                <thead>
                  <tr>
                    <th scope="col">Question</th>
                    <th scope="col">Answer</th>
                    <th scope="col">Result</th>
                  </tr>
                </thead>
                <tbody>
                  {props.answers.map((a) => (
                    <tr key={a.key}>
                      <td>{a.key.replaceAll("_", " ")}</td>
                      <td>{show(a.value)}</td>
                      <td>
                        {a.outcome.replaceAll("_", " ")}
                        {a.note && a.outcome !== "pass" ? ` (${a.note})` : ""}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {props.meta ? <p className="h-meta">{props.meta}</p> : null}
            </section>
          ) : (
            <p className="h-note">No score yet for this candidate.</p>
          )
        ) : null}

        {tab === "cv" ? (
          <section aria-labelledby="cv-h">
            <h2 id="cv-h" className="h-panel-title">
              CV (personal details removed)
            </h2>
            <p className="h-note">
              Name, contact details, photo, age and address are removed for a fair review.
            </p>
            {/* Text nodes only: the CV is candidate supplied and never treated as HTML. */}
            <div className="h-cv" tabIndex={0} aria-label="CV text">
              {props.text
                ? segs.map((s, i) => {
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
                  })
                : "The CV text is not available."}
            </div>
          </section>
        ) : null}

        {tab === "email" ? (
          <RejectionPanel
            candidateId={props.candidateId}
            state={props.state}
            version={props.version}
            rejection={props.rejection}
          />
        ) : null}

        {tab === "activity" ? (
          <section aria-labelledby="history-h">
            <h2 id="history-h" className="h-panel-title">
              History
            </h2>
            {[...props.audit].reverse().map((e, i) => (
              <div key={i} className="h-event">
                <div>
                  {stateLabel(e.to_state)} by {e.actor_type.toLowerCase()} ({e.actor_id})
                </div>
                <small>{when(e.occurred_at)}</small>
                <p>{e.reason}</p>
              </div>
            ))}
            {props.access.map((e, i) => (
              <div key={`a${i}`} className="h-event">
                <div>Contact details opened by {e.actor_id}</div>
                <small>{when(e.at)}</small>
              </div>
            ))}
          </section>
        ) : null}
      </div>
    </>
  );
}
