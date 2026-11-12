import Link from "next/link";

import { api, type RejectionQueue } from "@/lib/api";

import { resolve, retryDelivery } from "../actions";

// To do (phase 5B UI design): everything waiting on the recruiter in one place. Same
// actions as the phase 4 and 5 review queue.

type Queue = {
  candidates: {
    id: string;
    label: string;
    job_id: string | null;
    job_title: string | null;
    state_version: number;
    return_state: string | null;
    reason: string;
  }[];
  jobs: { id: string; title: string }[];
};

export default async function ReviewPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; done?: string }>;
}) {
  const s = await searchParams;
  const [q, emails] = await Promise.all([
    api.get<Queue>("/review-queue"),
    api.get<RejectionQueue>("/rejections/queue"),
  ]);
  const open = q.candidates.length + q.jobs.length + emails.drafts.length + emails.undelivered.length;
  return (
    <>
      <div className="h-hero">
        <div>
          <div className="h-eyebrow">To do</div>
          <h1 className="h-h1">Things waiting on you.</h1>
          <p className="h-intro">
            Everything the agent could not finish alone. Retry sends a candidate back to the step that failed.
          </p>
        </div>
        <div className="h-stats" aria-label="Open items">
          <div className="h-stat">
            <strong>{String(open).padStart(2, "0")}</strong>
            <small>Open items</small>
          </div>
          <div className="h-stat">
            <strong>{String(q.candidates.length).padStart(2, "0")}</strong>
            <small>Need review</small>
          </div>
          <div className="h-stat">
            <strong>{String(emails.drafts.length).padStart(2, "0")}</strong>
            <small>Emails to send</small>
          </div>
        </div>
      </div>
      {s.error ? (
        <p role="alert" className="h-banner bad">
          {s.error}
        </p>
      ) : null}
      {s.done ? (
        <p role="status" className="h-banner ok">
          Done.
        </p>
      ) : null}

      <section className="h-card" aria-labelledby="needs-h">
        <div className="h-chead">
          <h2 id="needs-h">Candidates that need review</h2>
        </div>
        {q.candidates.length === 0 ? (
          <p className="h-empty">Nothing needs review.</p>
        ) : (
          <table className="h-table">
            <caption className="sr-only">Candidates that need review</caption>
            <thead>
              <tr>
                <th scope="col">Candidate</th>
                <th scope="col" className="hide-sm">
                  Why
                </th>
                <th scope="col">Action</th>
              </tr>
            </thead>
            <tbody>
              {q.candidates.map((c) => (
                <tr key={c.id}>
                  <td>
                    <Link href={`/candidates/${c.id}`} className="h-t1">
                      {c.label}
                    </Link>
                    <div className="h-t2">{c.job_title ?? "No job"}</div>
                  </td>
                  <td className="hide-sm">{c.reason}</td>
                  <td>
                    <form action={resolve} className="h-inline-form">
                      <input type="hidden" name="candidate_id" value={c.id} />
                      <input type="hidden" name="expected_version" value={c.state_version} />
                      <label className="sr-only" htmlFor={`reason-${c.id}`}>
                        Reason
                      </label>
                      <input
                        id={`reason-${c.id}`}
                        name="reason"
                        placeholder="Reason (optional)"
                        className="h-input"
                        style={{ width: 180, padding: "7px 10px" }}
                      />
                      {c.return_state ? (
                        <button name="action" value="retry" className="h-btn small">
                          Retry
                        </button>
                      ) : null}
                      <button name="action" value="reject" className="h-btn small danger">
                        Reject
                      </button>
                    </form>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {q.jobs.length ? (
        <section className="h-card" aria-labelledby="rubric-h">
          <div className="h-chead">
            <h2 id="rubric-h">Jobs whose rubric could not be built</h2>
          </div>
          <ul className="h-list">
            {q.jobs.map((j) => (
              <li key={j.id}>
                <span className="h-t1">{j.title}</span>
                <span className="h-t2">Supply a rubric through the API</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="h-card" aria-labelledby="send-h">
        <div className="h-chead">
          <h2 id="send-h">Rejection emails to send</h2>
          <small>Read each one, then send it from the candidate</small>
        </div>
        {emails.drafts.length === 0 ? (
          <p className="h-empty">No drafts waiting.</p>
        ) : (
          <ul aria-label="Rejection emails to send" className="h-list">
            {emails.drafts.map((d) => (
              <li key={d.id}>
                <span>
                  <Link href={`/candidates/${d.id}`} className="h-t1">
                    {d.label}
                  </Link>
                  <span className="h-t2"> · {d.job_title ?? "no job"}</span>
                </span>
                {d.needs_edit ? <span className="h-pill warn">read first: {d.fallback_reason}</span> : null}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="h-card" aria-labelledby="undelivered-h">
        <div className="h-chead">
          <h2 id="undelivered-h">Emails not delivered</h2>
        </div>
        {emails.undelivered.length === 0 ? (
          <p className="h-empty">None.</p>
        ) : (
          <ul aria-label="Emails not delivered" className="h-list">
            {emails.undelivered.map((u) => (
              <li key={u.id}>
                <form action={retryDelivery} className="h-inline-form" style={{ width: "100%" }}>
                  <input type="hidden" name="candidate_id" value={u.id} />
                  <input type="hidden" name="back" value="/review?done=1" />
                  <Link href={`/candidates/${u.id}`} className="h-t1">
                    {u.label}
                  </Link>
                  <span className="h-t2">
                    {u.job_title ?? "no job"}: {u.attempts} attempts, {u.last_error}
                  </span>
                  <button className="h-btn small" style={{ marginLeft: "auto" }}>
                    Retry delivery
                  </button>
                </form>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
