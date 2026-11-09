import Link from "next/link";

import { api, type JobSummary } from "@/lib/api";
import { rate } from "@/lib/format";

export default async function JobsPage() {
  const { jobs } = await api.get<{ jobs: JobSummary[] }>("/jobs");
  return (
    <>
      <h1 className="text-2xl font-semibold">Jobs</h1>
      {jobs.length === 0 ? (
        <p className="mt-4">No jobs yet. Create one through the API, or run the demo seed.</p>
      ) : (
        <table className="mt-4 w-full border-collapse text-sm">
          <caption className="sr-only">Jobs with candidate counts and agreement rate</caption>
          <thead>
            <tr className="border-b border-zinc-300 text-left dark:border-zinc-700">
              <th scope="col" className="py-2 pr-4">Job</th>
              <th scope="col" className="py-2 pr-4">State</th>
              <th scope="col" className="py-2 pr-4">Rubric</th>
              <th scope="col" className="py-2 pr-4 text-right">Candidates</th>
              <th scope="col" className="py-2 pr-4 text-right">To decide</th>
              <th scope="col" className="py-2 pr-4 text-right">Needs review</th>
              <th scope="col" className="py-2 pr-4 text-right">Agreement</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((j) => (
              <tr key={j.id} className="border-b border-zinc-200 dark:border-zinc-800">
                <td className="py-2 pr-4">
                  <Link href={`/jobs/${j.id}`} className="font-medium text-blue-800 underline dark:text-blue-300">
                    {j.title}
                  </Link>
                  <div className="text-zinc-700 dark:text-zinc-400">{j.location}</div>
                </td>
                <td className="py-2 pr-4">{j.state.toLowerCase().replaceAll("_", " ")}</td>
                <td className="py-2 pr-4">
                  {j.approved_rubric_version ? `v${j.approved_rubric_version}` : "not approved"}
                </td>
                <td className="py-2 pr-4 text-right">{j.candidates}</td>
                <td className="py-2 pr-4 text-right">{j.undecided}</td>
                <td className="py-2 pr-4 text-right">{j.needs_review}</td>
                <td className="py-2 pr-4 text-right">
                  {rate(j.agreement.rate)}
                  {j.agreement.overrides ? ` (${j.agreement.overrides} overrides)` : ""}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
