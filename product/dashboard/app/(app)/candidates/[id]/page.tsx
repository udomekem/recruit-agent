import Link from "next/link";

import {
  api,
  ApiError,
  type CandidateDetail,
  type Contact,
  type ParseDetail,
  type Ranked,
  type ScoreDetail,
} from "@/lib/api";
import { BAND_CLASS, BAND_LABEL, FLAG_LABEL, SERIOUS_FLAGS, stateLabel, when } from "@/lib/format";

import { Evidence } from "./evidence";
import { ReviewPanel } from "./review-panel";

async function maybe<T>(p: Promise<T>): Promise<T | null> {
  try {
    return await p;
  } catch (e) {
    if (e instanceof ApiError && [403, 404, 410].includes(e.status)) return null;
    throw e;
  }
}

const AFTER_SHORTLIST = new Set([
  "SHORTLISTED",
  "SCREEN_CALL_QUEUED",
  "SCREEN_CALL_DONE",
  "NO_ANSWER",
  "SCREEN_SCORED",
  "ADVANCED",
  "BOOKING_CALL_QUEUED",
  "BOOKING_CALL_DONE",
  "INTERVIEW_BOOKED",
]);

export default async function CandidatePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const c = await api.get<CandidateDetail>(`/candidates/${id}`);
  // Blind review: contact details are requested only after shortlist (the API refuses
  // before), so they are never in this page for an undecided candidate. Read first, so
  // this view is already in the access log shown below.
  const contact =
    !c.erased && AFTER_SHORTLIST.has(c.state)
      ? await maybe(api.get<Contact>(`/candidates/${id}/contact`))
      : null;
  const [score, parse, ranked, access] = await Promise.all([
    maybe(api.get<ScoreDetail>(`/candidates/${id}/score`)),
    maybe(api.get<ParseDetail>(`/candidates/${id}/parse`)),
    c.job_id ? api.get<Ranked>(`/jobs/${c.job_id}/candidates`) : Promise.resolve(null),
    api.get<{ events: { what: string; actor_id: string; at: string }[] }>(`/candidates/${id}/access`),
  ]);

  const order = ranked?.scored ?? [];
  const at = order.findIndex((r) => r.id === id);
  const prev = at > 0 ? order[at - 1].id : null;
  const next = at >= 0 && at < order.length - 1 ? order[at + 1].id : null;
  const flags = [...(score?.flags ?? [])].sort(
    (a, b) => Number(SERIOUS_FLAGS.has(b.kind)) - Number(SERIOUS_FLAGS.has(a.kind)),
  );

  return (
    <>
      <nav aria-label="Breadcrumb" className="text-sm">
        {c.job_id ? (
          <Link href={`/jobs/${c.job_id}`} className="text-blue-800 underline dark:text-blue-300">
            Back to the ranked list
          </Link>
        ) : null}
      </nav>
      <div className="mt-2 flex flex-wrap items-baseline gap-4">
        <h1 className="text-2xl font-semibold">{c.display_label}</h1>
        {score ? (
          <>
            <span className="text-xl tabular-nums">{score.total.toFixed(1)}</span>
            <span className={`rounded px-2 py-0.5 ${BAND_CLASS[score.band]}`}>
              AI recommendation: {BAND_LABEL[score.band]}
            </span>
          </>
        ) : null}
        <span>{stateLabel(c.state)}</span>
        {at >= 0 ? (
          <span className="text-sm text-zinc-700 dark:text-zinc-400">
            rank {at + 1} of {order.length}
          </span>
        ) : null}
      </div>

      {c.erased ? (
        <p role="status" className="mt-3 rounded bg-zinc-200 px-3 py-2 dark:bg-zinc-800">
          This candidate&apos;s personal data was erased. Scores remain for the audit record.
        </p>
      ) : null}

      {flags.length ? (
        <ul aria-label="Flags" className="mt-3 flex flex-wrap gap-2">
          {flags.map((f) => (
            <li
              key={f.kind}
              className={`rounded px-2 py-1 text-sm ${
                SERIOUS_FLAGS.has(f.kind)
                  ? "bg-rose-700 font-medium text-white"
                  : "bg-zinc-200 text-zinc-900 dark:bg-zinc-700 dark:text-zinc-100"
              }`}
            >
              {FLAG_LABEL[f.kind] ?? f.kind}
              {f.text ? `: ${f.text}` : ""}
            </li>
          ))}
        </ul>
      ) : null}

      <ReviewPanel
        candidateId={id}
        jobId={c.job_id}
        state={c.state}
        version={c.state_version}
        band={score?.band ?? null}
        prev={prev}
        next={next}
        erased={c.erased}
      />

      {contact ? (
        <section aria-labelledby="contact-h" className="mt-4 rounded border border-emerald-400 p-3">
          <h2 id="contact-h" className="font-semibold">Contact (shown after shortlist; this view is logged)</h2>
          <p className="mt-1 text-sm">
            {contact.name} · {contact.email} · {contact.phone}
          </p>
        </section>
      ) : null}

      {score ? (
        <Evidence
          criteria={score.criteria}
          text={parse?.redacted_text ?? ""}
          reasons={score.reasons}
          answers={score.answers}
        />
      ) : (
        <p className="mt-6">No score yet for this candidate.</p>
      )}

      {score ? (
        <p className="mt-4 text-xs text-zinc-700 dark:text-zinc-400">
          Rubric v{score.rubric_version} · prompt {score.prompt_id} {score.prompt_version} · model{" "}
          {score.model}
        </p>
      ) : null}

      <section aria-labelledby="history-h" className="mt-8">
        <h2 id="history-h" className="text-lg font-semibold">History</h2>
        <ol className="mt-2 space-y-1 text-sm">
          {c.audit.map((e, i) => (
            <li key={i}>
              <span className="text-zinc-700 dark:text-zinc-400">{when(e.occurred_at)}</span>{" "}
              <strong>{stateLabel(e.to_state)}</strong> by {e.actor_type.toLowerCase()} ({e.actor_id}):{" "}
              {e.reason}
            </li>
          ))}
          {access.events.map((e, i) => (
            <li key={`a${i}`}>
              <span className="text-zinc-700 dark:text-zinc-400">{when(e.at)}</span>{" "}
              <strong>Contact details viewed</strong> by {e.actor_id}
            </li>
          ))}
        </ol>
      </section>
    </>
  );
}
