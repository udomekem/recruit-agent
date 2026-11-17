import Link from "next/link";

import {
  api,
  ApiError,
  type CandidateDetail,
  type Contact,
  type ParseDetail,
  type Rejection,
  type ScoreDetail,
} from "@/lib/api";
import { BAND_LABEL, FLAG_LABEL, rate, SERIOUS_FLAGS, stateLabel, when } from "@/lib/format";
import {
  AFTER_SHORTLIST,
  type Filters,
  loadQueue,
  PAGE,
  qs,
  REJECTED,
  type Row,
  type Status,
  statusOf,
} from "@/lib/workbench";

import { rescore } from "./actions";
import { ReviewPanel } from "./candidates/[id]/review-panel";
import { ReviewTabs } from "./candidates/[id]/review-tabs";

// The Hira workbench (phase 5B UI design): heading and counts, status and job filters,
// the ranked queue on the left and the review panel on the right. Under 680 px the list
// and the review are separate screens (data-mode).

async function maybe<T>(p: Promise<T>): Promise<T | null> {
  try {
    return await p;
  } catch (e) {
    if (e instanceof ApiError && [403, 404, 410].includes(e.status)) return null;
    throw e;
  }
}

const TONE: Record<string, string> = { advance: "good", maybe: "maybe", reject: "bad" };
const STATUS_TABS: [Status, string][] = [
  ["", "All candidates"],
  ["todo", "To decide"],
  ["shortlisted", "Shortlisted"],
  ["rejected", "Rejected"],
];

function initials(label: string): string {
  const digits = label.replace(/\D/g, "");
  return digits ? digits.slice(-2) : label.slice(0, 2).toUpperCase();
}

function rowTone(r: Row): string {
  const s = statusOf(r.state);
  if (s === "shortlisted") return "good";
  if (s === "rejected") return "bad";
  return TONE[r.band ?? ""] ?? "todo";
}

function rowStatus(r: Row): string {
  if (r.state === "SCORED") {
    return `${r.band ? BAND_LABEL[r.band] : "To decide"}${r.total !== undefined ? ` · ${Math.round(r.total)}` : ""}`;
  }
  return stateLabel(r.state);
}

export async function Workbench(props: {
  filters: Filters;
  selectedId?: string;
  mode: "list" | "review";
  notice?: { done?: string; rescoring?: string };
}) {
  const f = props.filters;
  const queue = await loadQueue(f);
  const listPath = f.job === "all" ? "/" : `/jobs/${f.job}`;
  const listDefault = f.job === "all" ? "all" : f.job; // the list path already says which job
  const candidateQs = (extra: Partial<Filters> = {}) => qs({ ...f, ...extra }, "");
  const selected = props.selectedId ?? queue.rows[0]?.id ?? null;
  // Draw one page of rows (more on "Show more"), always far enough to include the open candidate.
  const shown = Math.max(f.show ?? PAGE, queue.rows.findIndex((r) => r.id === selected) + 1);
  const visible = queue.rows.slice(0, shown);
  const more = queue.rows.length - visible.length;
  const job = queue.job;
  const ranked = queue.ranked;
  const nextUndecided = queue.all.find((r) => r.state === "SCORED" && !r.erased);
  const allCounts = {
    total: queue.all.length,
    todo: queue.all.filter((r) => r.state === "SCORED").length,
    shortlisted: queue.all.filter((r) => AFTER_SHORTLIST.has(r.state)).length,
  };

  return (
    <div className="h-workbench" data-mode={props.mode}>
      <div className="h-hero">
        <div>
          <div className="h-eyebrow">{job ? `Screening · ${job.location}` : "Screening · every open job"}</div>
          <h1 className="h-h1">{job ? job.title : "Your next great hire."}</h1>
          <p className="h-intro">
            {job
              ? `Ranked by how well each CV meets this job's rubric (v${ranked?.rubric_version ?? "?"}). You decide; the AI shows its evidence.`
              : "Ranked by how well each CV meets its job. You decide; the AI shows its evidence. Names stay hidden until you shortlist."}
          </p>
          {ranked ? (
            <p className="h-agree">
              <strong>Agreement with the AI:</strong> {rate(ranked.agreement.rate)} ({ranked.agreement.agreed} of{" "}
              {ranked.agreement.counted}
              {ranked.agreement.overrides ? `, ${ranked.agreement.overrides} overrides` : ""})
            </p>
          ) : null}
          {job && nextUndecided ? (
            <p style={{ margin: "12px 0 0" }}>
              <Link href={`/candidates/${nextUndecided.id}`} className="h-btn primary">
                Review next undecided
              </Link>
            </p>
          ) : null}
        </div>
        <div className="h-stats" aria-label="Candidate counts">
          <div className="h-stat">
            <strong>{String(allCounts.total).padStart(2, "0")}</strong>
            <small>Candidates</small>
          </div>
          <div className="h-stat">
            <strong>{String(allCounts.shortlisted).padStart(2, "0")}</strong>
            <small>Shortlisted</small>
          </div>
          <div className="h-stat">
            <strong>{String(allCounts.todo).padStart(2, "0")}</strong>
            <small>To decide</small>
          </div>
        </div>
      </div>

      {props.notice?.done ? (
        <p role="status" className="h-banner ok">
          Every scored candidate in this job has a decision.
        </p>
      ) : null}
      {props.notice?.rescoring && ranked ? (
        <p role="status" className="h-banner info">
          Rescoring {props.notice.rescoring} candidates against rubric v{ranked.rubric_version}. Refresh in a minute.
        </p>
      ) : null}
      {ranked && ranked.outdated > 0 && job ? (
        <form action={rescore} className="h-banner warn">
          <input type="hidden" name="job_id" value={job.id} />
          <span>{ranked.outdated} undecided candidates were scored on an older rubric.</span>
          <button type="submit" className="h-btn small">
            Rescore with v{ranked.rubric_version}
          </button>
        </form>
      ) : null}

      <div className="h-toolbar">
        <nav className="h-seg" aria-label="Status">
          {STATUS_TABS.map(([s, label]) => (
            <Link key={s || "all"} href={`${listPath}${qs({ ...f, status: s, show: undefined }, listDefault)}`} aria-current={f.status === s}>
              {label} <span>{queue.counts[s]}</span>
            </Link>
          ))}
        </nav>
        <form method="get" action="/filter" className="h-filters" aria-label="Filters">
          {f.status ? <input type="hidden" name="status" value={f.status} /> : null}
          {f.q ? <input type="hidden" name="q" value={f.q} /> : null}
          <label htmlFor="f-job" className="sr-only">
            Job
          </label>
          <select id="f-job" name="job" defaultValue={f.job} className="h-select">
            <option value="all">All open jobs</option>
            {queue.jobs.map((j) => (
              <option key={j.id} value={j.id}>
                {j.title}
              </option>
            ))}
          </select>
          <label htmlFor="f-band" className="sr-only">
            Recommendation
          </label>
          <select id="f-band" name="band" defaultValue={f.band} className="h-select">
            <option value="">Any recommendation</option>
            <option value="advance">Advance</option>
            <option value="maybe">Maybe</option>
            <option value="reject">Reject</option>
          </select>
          {queue.flags.length ? (
            <>
              <label htmlFor="f-flag" className="sr-only">
                Flag
              </label>
              <select id="f-flag" name="flag" defaultValue={f.flag} className="h-select">
                <option value="">Any flag</option>
                {queue.flags.map((x) => (
                  <option key={x} value={x}>
                    {FLAG_LABEL[x] ?? x}
                  </option>
                ))}
              </select>
            </>
          ) : null}
          <button type="submit" className="h-btn">
            Filter
          </button>
        </form>
      </div>

      <Link href={`${listPath}${qs(f, listDefault)}`} className="h-back">
        ← All candidates
      </Link>

      <div className="h-bench" data-mode={props.mode}>
        <aside className="h-queue" aria-label="Candidates">
          <form method="get" action={listPath} className="h-search" role="search">
            {(["status", "band", "flag"] as const).map((k) =>
              f[k] ? <input key={k} type="hidden" name={k} value={f[k]} /> : null,
            )}
            <span aria-hidden="true">⌕</span>
            <label htmlFor="f-q" className="sr-only">
              Find a candidate
            </label>
            <input id="f-q" name="q" type="search" placeholder="Find a candidate number…" defaultValue={f.q} />
          </form>
          <div className="h-qlabel">
            <span>{job ? "Ranked by score" : "Highest score first"}</span>
            <span>{queue.rows.length} people</span>
          </div>
          {visible.length ? (
            visible.map((r) => (
              <Link
                key={r.id}
                href={`/candidates/${r.id}${candidateQs()}`}
                data-row-link
                className="h-row"
                aria-current={r.id === selected}
              >
                <span className="h-avatar" aria-hidden="true">
                  {initials(r.label)}
                </span>
                <span className="h-rinfo">
                  <span className="h-rname">{r.label}</span>
                  <span className="h-rrole">{r.jobTitle}</span>
                  <span className="h-rbot">
                    <span className="h-dot" data-tone={rowTone(r)}>
                      {rowStatus(r)}
                      {r.decision?.override ? " (override)" : ""}
                    </span>
                    <span>{when(r.applied_at)}</span>
                  </span>
                </span>
              </Link>
            ))
          ) : (
            <p className="h-empty">No matching candidates. Try another job, status or number.</p>
          )}
          {more > 0 ? (
            <Link
              href={`${listPath}${qs({ ...f, show: shown + PAGE }, listDefault)}`}
              className="h-btn small"
              style={{ margin: "12px" }}
              scroll={false}
            >
              Show {Math.min(more, PAGE)} more (showing {visible.length} of {queue.rows.length})
            </Link>
          ) : null}
          <p className="h-qfoot">
            Scores are out of 100.
            {queue.unscored ? ` ${queue.unscored} more are still in the pipeline or need review (see To do).` : ""}
          </p>
        </aside>

        {selected ? (
          <CandidateReview
            id={selected}
            rows={queue.rows}
            qsFor={candidateQs()}
            opened={props.selectedId === selected}
          />
        ) : (
          <section className="h-review" aria-label="Candidate review">
            <div className="h-panel">
              <h2 className="h-h2">No candidates found</h2>
              <p className="h-help">Try another job, status or number.</p>
            </div>
          </section>
        )}
      </div>
      <div className="h-footer">
        <span>🔒 Personal details stay hidden until shortlist; every view of them is logged.</span>
        <span>Northwind Talent · private hiring workspace</span>
      </div>
    </div>
  );
}

async function CandidateReview({
  id,
  rows,
  qsFor,
  opened,
}: {
  id: string;
  rows: Row[];
  qsFor: string;
  opened: boolean; // the recruiter opened this candidate (not the list's first row shown by default)
}) {
  const c = await api.get<CandidateDetail>(`/candidates/${id}`);
  // Blind review: contact details are requested only after shortlist (the API refuses
  // before), so they are never in this page for an undecided candidate. Only when the
  // recruiter opened the candidate: a list page showing its first row must not create a
  // logged contact view. Read first, so this view is already in the access log.
  const shortlisted = !c.erased && AFTER_SHORTLIST.has(c.state);
  const contact = shortlisted && opened ? await maybe(api.get<Contact>(`/candidates/${id}/contact`)) : null;
  const emailTab = REJECTED.has(c.state);
  const [score, parse, access, rejection] = await Promise.all([
    maybe(api.get<ScoreDetail>(`/candidates/${id}/score`)),
    maybe(api.get<ParseDetail>(`/candidates/${id}/parse`)),
    api.get<{ events: { what: string; actor_id: string; at: string }[] }>(`/candidates/${id}/access`),
    emailTab ? maybe(api.get<Rejection>(`/candidates/${id}/rejection`)) : Promise.resolve(null),
  ]);
  const at = rows.findIndex((r) => r.id === id);
  const prevHref = at > 0 ? `/candidates/${rows[at - 1].id}${qsFor}` : null;
  const nextHref = at >= 0 && at < rows.length - 1 ? `/candidates/${rows[at + 1].id}${qsFor}` : null;
  const jobTitle = rows[at]?.jobTitle ?? null;
  const flags = [...(score?.flags ?? [])].sort(
    (a, b) => Number(SERIOUS_FLAGS.has(b.kind)) - Number(SERIOUS_FLAGS.has(a.kind)),
  );
  const tone = emailTab ? "bad" : AFTER_SHORTLIST.has(c.state) ? "good" : c.state === "SCORED" ? "todo" : "maybe";

  return (
    <section className="h-review" aria-label="Candidate review">
      <div className="h-rhead">
        <div className="h-kicker">
          <span>
            {at >= 0
              ? `Candidate ${String(at + 1).padStart(2, "0")} of ${String(rows.length).padStart(2, "0")}`
              : "Not in this list"}
          </span>
          <div className="h-mini">
            <Link
              href={prevHref ?? "#"}
              className="h-ib"
              aria-label="Previous candidate"
              aria-disabled={!prevHref}
              tabIndex={prevHref ? undefined : -1}
            >
              ‹
            </Link>
            <Link
              href={nextHref ?? "#"}
              className="h-ib"
              aria-label="Next candidate"
              aria-disabled={!nextHref}
              tabIndex={nextHref ? undefined : -1}
            >
              ›
            </Link>
          </div>
        </div>
        <div className="h-ident">
          <span className="h-avatar" aria-hidden="true">
            {initials(c.display_label)}
          </span>
          <div>
            <h2 className="h-h2">{c.display_label}</h2>
            <p className="h-tline">{jobTitle ?? (c.job_id ? "Job" : "No job yet")}</p>
          </div>
        </div>
        <div className="h-facts">
          {score ? (
            <span className="h-reco">
              <strong>{score.total.toFixed(1)}</strong>
              <span>AI recommendation: {BAND_LABEL[score.band]}</span>
            </span>
          ) : (
            <span className="h-reco">No score yet</span>
          )}
          <span className="h-dot" data-tone={tone}>
            {stateLabel(c.state)}
          </span>
          {at >= 0 ? <span>Rank {at + 1} of {rows.length}</span> : null}
          {flags.length ? (
            <span aria-label="Flags" style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {flags.map((x) => (
                <span key={x.kind} className={`h-flag${SERIOUS_FLAGS.has(x.kind) ? " serious" : ""}`}>
                  {FLAG_LABEL[x.kind] ?? x.kind}
                  {x.text ? `: ${x.text}` : ""}
                </span>
              ))}
            </span>
          ) : null}
        </div>
        {c.erased ? (
          <p role="status" className="h-note">
            This candidate&apos;s personal data was erased. Scores remain for the audit record.
          </p>
        ) : null}
        {contact ? (
          <section aria-labelledby="contact-h" className="h-contact">
            <h2 id="contact-h">Contact (shown after shortlist; this view is logged)</h2>
            <p>
              {contact.name} · {contact.email} · {contact.phone}
            </p>
            <p className="h-help" style={{ color: "inherit" }}>
              Contact details viewed {access.events.length} time{access.events.length === 1 ? "" : "s"}
              {access.events.length ? `, last by ${access.events[access.events.length - 1].actor_id}` : ""}.
            </p>
          </section>
        ) : shortlisted ? (
          <p className="h-note">
            Shortlisted.{" "}
            <Link href={`/candidates/${id}${qsFor}`} style={{ color: "var(--h-blue)" }}>
              Open this candidate to see contact details
            </Link>{" "}
            (the view is logged).
          </p>
        ) : null}
      </div>

      <ReviewTabs
        key={`${id}:${c.state_version}`}
        candidateId={id}
        state={c.state}
        version={c.state_version}
        criteria={score?.criteria ?? null}
        reasons={score?.reasons ?? []}
        answers={score?.answers ?? []}
        text={parse?.redacted_text ?? ""}
        meta={
          score
            ? `Rubric v${score.rubric_version} · prompt ${score.prompt_id} ${score.prompt_version} · model ${score.model}`
            : null
        }
        audit={c.audit}
        access={access.events}
        rejection={rejection}
        emailTab={emailTab}
      />

      <ReviewPanel
        candidateId={id}
        jobId={c.job_id}
        state={c.state}
        version={c.state_version}
        band={score?.band ?? null}
        prevHref={prevHref}
        nextHref={nextHref}
        erased={c.erased}
      />
    </section>
  );
}
