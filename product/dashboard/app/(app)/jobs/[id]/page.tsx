import Link from "next/link";

import { api, type Ranked, type RankedRow } from "@/lib/api";
import { BAND_CLASS, BAND_LABEL, FLAG_LABEL, SERIOUS_FLAGS, rate, stateLabel } from "@/lib/format";

import { rescore } from "../../actions";
import { RowKeys } from "./row-keys";

type Search = { band?: string; flag?: string; state?: string; done?: string; rescoring?: string };

function matches(r: RankedRow, s: Search): boolean {
  if (s.band && r.band !== s.band) return false;
  if (s.state && r.state !== s.state) return false;
  if (s.flag && !(r.flags ?? []).some((f) => f.kind === s.flag)) return false;
  return true;
}

export default async function JobPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<Search>;
}) {
  const { id } = await params;
  const s = await searchParams;
  const [ranked, job] = await Promise.all([
    api.get<Ranked>(`/jobs/${id}/candidates`),
    api.get<{ title: string; location: string }>(`/jobs/${id}`),
  ]);
  const rows = ranked.scored.filter((r) => matches(r, s));
  const next = ranked.scored.find((r) => r.state === "SCORED" && !r.erased);
  const a = ranked.agreement;
  const flags = [...new Set(ranked.scored.flatMap((r) => (r.flags ?? []).map((f) => f.kind)))];

  return (
    <>
      <div className="flex flex-wrap items-baseline gap-4">
        <h1 className="text-2xl font-semibold">{job.title}</h1>
        <span className="text-zinc-700 dark:text-zinc-400">{job.location}</span>
        <span className="text-zinc-700 dark:text-zinc-400">rubric v{ranked.rubric_version}</span>
      </div>

      <section aria-label="Summary" className="mt-3 flex flex-wrap items-center gap-6 text-sm">
        <p>
          <strong>Agreement with the AI:</strong> {rate(a.rate)} ({a.agreed} of {a.counted}
          {a.overrides ? `, ${a.overrides} overrides` : ""})
        </p>
        <p>
          <strong>To decide:</strong> {ranked.scored.filter((r) => r.state === "SCORED").length}
        </p>
        {next ? (
          <Link
            href={`/candidates/${next.id}`}
            className="rounded bg-blue-700 px-3 py-1.5 font-medium text-white hover:bg-blue-800"
          >
            Review next undecided
          </Link>
        ) : null}
      </section>

      {s.done ? (
        <p role="status" className="mt-3 rounded bg-emerald-100 px-3 py-2 text-emerald-900 dark:bg-emerald-900 dark:text-emerald-100">
          Every scored candidate in this job has a decision.
        </p>
      ) : null}
      {s.rescoring ? (
        <p role="status" className="mt-3 rounded bg-blue-100 px-3 py-2 text-blue-900 dark:bg-blue-900 dark:text-blue-100">
          Rescoring {s.rescoring} candidates against rubric v{ranked.rubric_version}. Refresh in a minute.
        </p>
      ) : null}
      {ranked.outdated > 0 ? (
        <form action={rescore} className="mt-3 flex items-center gap-3 rounded bg-amber-100 px-3 py-2 text-amber-950 dark:bg-amber-900 dark:text-amber-50">
          <input type="hidden" name="job_id" value={id} />
          <span>
            {ranked.outdated} undecided candidates were scored on an older rubric.
          </span>
          <button type="submit" className="rounded bg-amber-800 px-3 py-1 text-white hover:bg-amber-900">
            Rescore with v{ranked.rubric_version}
          </button>
        </form>
      ) : null}

      <form method="get" className="mt-4 flex flex-wrap items-end gap-3 text-sm" aria-label="Filters">
        <label htmlFor="f-band" className="flex flex-col">
          Band
          <select id="f-band" name="band" defaultValue={s.band ?? ""} className="rounded border border-zinc-400 bg-white px-2 py-1 dark:border-zinc-600 dark:bg-zinc-900">
            <option value="">All</option>
            <option value="advance">Advance</option>
            <option value="maybe">Maybe</option>
            <option value="reject">Reject</option>
          </select>
        </label>
        <label htmlFor="f-state" className="flex flex-col">
          State
          <select id="f-state" name="state" defaultValue={s.state ?? ""} className="rounded border border-zinc-400 bg-white px-2 py-1 dark:border-zinc-600 dark:bg-zinc-900">
            <option value="">All</option>
            <option value="SCORED">To decide</option>
            <option value="SHORTLISTED">Shortlisted</option>
            <option value="REJECTION_DRAFTED">Rejected</option>
          </select>
        </label>
        <label htmlFor="f-flag" className="flex flex-col">
          Flag
          <select id="f-flag" name="flag" defaultValue={s.flag ?? ""} className="rounded border border-zinc-400 bg-white px-2 py-1 dark:border-zinc-600 dark:bg-zinc-900">
            <option value="">Any</option>
            {flags.map((f) => (
              <option key={f} value={f}>
                {FLAG_LABEL[f] ?? f}
              </option>
            ))}
          </select>
        </label>
        <button type="submit" className="rounded border border-zinc-500 px-3 py-1">
          Filter
        </button>
        <span className="text-zinc-700 dark:text-zinc-400">
          Keys: <kbd>j</kbd> <kbd>k</kbd> move, <kbd>Enter</kbd> open
        </span>
      </form>

      <table className="mt-4 w-full border-collapse text-sm" id="ranked">
        <caption className="sr-only">Candidates ranked by score</caption>
        <thead>
          <tr className="border-b border-zinc-300 text-left dark:border-zinc-700">
            <th scope="col" className="py-2 pr-3">Rank</th>
            <th scope="col" className="py-2 pr-3">Candidate</th>
            <th scope="col" className="py-2 pr-3 text-right">Score</th>
            <th scope="col" className="py-2 pr-3">Recommendation</th>
            <th scope="col" className="py-2 pr-3">Flags</th>
            <th scope="col" className="py-2 pr-3">Knockouts</th>
            <th scope="col" className="py-2 pr-3">State</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} data-row className="border-b border-zinc-200 dark:border-zinc-800">
              <td className="py-2 pr-3">{r.rank}</td>
              <td className="py-2 pr-3">
                <Link href={`/candidates/${r.id}`} data-row-link className="font-medium text-blue-800 underline dark:text-blue-300">
                  {r.label}
                </Link>
              </td>
              <td className="py-2 pr-3 text-right tabular-nums">{r.total?.toFixed(1)}</td>
              <td className="py-2 pr-3">
                {r.band ? (
                  <span className={`rounded px-2 py-0.5 ${BAND_CLASS[r.band]}`}>{BAND_LABEL[r.band]}</span>
                ) : null}
              </td>
              <td className="py-2 pr-3">
                {(r.flags ?? []).map((f) => (
                  <span
                    key={f.kind}
                    className={`mr-1 inline-block rounded px-1.5 py-0.5 text-xs ${
                      SERIOUS_FLAGS.has(f.kind)
                        ? "bg-rose-700 text-white"
                        : "bg-zinc-200 text-zinc-900 dark:bg-zinc-700 dark:text-zinc-100"
                    }`}
                  >
                    {FLAG_LABEL[f.kind] ?? f.kind}
                  </span>
                ))}
              </td>
              <td className="py-2 pr-3">
                {(r.knockouts ?? [])
                  .filter((k) => k.outcome !== "pass")
                  .map((k) => `${k.key.replaceAll("_", " ")}: ${k.outcome.replaceAll("_", " ")}`)
                  .join(", ") || "none"}
              </td>
              <td className="py-2 pr-3">
                {stateLabel(r.state)}
                {r.decision?.override ? " (override)" : ""}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {ranked.unscored.length ? (
        <p className="mt-4 text-sm text-zinc-700 dark:text-zinc-400">
          {ranked.unscored.length} candidates are not scored yet (still in the pipeline or needing review).
        </p>
      ) : null}
      <RowKeys />
    </>
  );
}
