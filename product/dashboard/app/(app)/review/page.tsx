import Link from "next/link";

import { api } from "@/lib/api";

import { resolve } from "../actions";

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
  const q = await api.get<Queue>("/review-queue");
  return (
    <>
      <h1 className="text-2xl font-semibold">Review queue</h1>
      <p className="mt-1 text-sm text-zinc-700 dark:text-zinc-400">
        Candidates the pipeline could not finish on its own. Retry sends them back to the step that failed.
      </p>
      {s.error ? (
        <p role="alert" className="mt-3 rounded bg-rose-100 px-3 py-2 text-rose-900 dark:bg-rose-900 dark:text-rose-100">
          {s.error}
        </p>
      ) : null}
      {s.done ? (
        <p role="status" className="mt-3 rounded bg-emerald-100 px-3 py-2 text-emerald-900 dark:bg-emerald-900 dark:text-emerald-100">
          Done.
        </p>
      ) : null}
      {q.candidates.length === 0 ? (
        <p className="mt-4">Nothing needs review.</p>
      ) : (
        <table className="mt-4 w-full border-collapse text-sm">
          <caption className="sr-only">Candidates that need review</caption>
          <thead>
            <tr className="border-b border-zinc-300 text-left dark:border-zinc-700">
              <th scope="col" className="py-2 pr-3">Candidate</th>
              <th scope="col" className="py-2 pr-3">Job</th>
              <th scope="col" className="py-2 pr-3">Why</th>
              <th scope="col" className="py-2 pr-3">Action</th>
            </tr>
          </thead>
          <tbody>
            {q.candidates.map((c) => (
              <tr key={c.id} className="border-b border-zinc-200 align-top dark:border-zinc-800">
                <td className="py-2 pr-3">
                  <Link href={`/candidates/${c.id}`} className="text-blue-800 underline dark:text-blue-300">
                    {c.label}
                  </Link>
                </td>
                <td className="py-2 pr-3">{c.job_title ?? "none"}</td>
                <td className="py-2 pr-3">{c.reason}</td>
                <td className="py-2 pr-3">
                  <form action={resolve} className="flex flex-wrap items-center gap-2">
                    <input type="hidden" name="candidate_id" value={c.id} />
                    <input type="hidden" name="expected_version" value={c.state_version} />
                    <label className="sr-only" htmlFor={`reason-${c.id}`}>
                      Reason
                    </label>
                    <input
                      id={`reason-${c.id}`}
                      name="reason"
                      placeholder="Reason (optional)"
                      className="w-48 rounded border border-zinc-400 bg-white px-2 py-1 dark:border-zinc-600 dark:bg-zinc-900"
                    />
                    {c.return_state ? (
                      <button name="action" value="retry" className="rounded border border-zinc-500 px-2 py-1">
                        Retry
                      </button>
                    ) : null}
                    <button name="action" value="reject" className="rounded bg-rose-700 px-2 py-1 text-white">
                      Reject
                    </button>
                  </form>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {q.jobs.length ? (
        <>
          <h2 className="mt-8 text-lg font-semibold">Jobs whose rubric could not be built</h2>
          <ul className="mt-2 list-disc pl-6 text-sm">
            {q.jobs.map((j) => (
              <li key={j.id}>{j.title} (supply a rubric through the API)</li>
            ))}
          </ul>
        </>
      ) : null}
    </>
  );
}
