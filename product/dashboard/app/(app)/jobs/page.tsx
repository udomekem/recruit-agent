import Link from "next/link";

import { api, type JobSummary } from "@/lib/api";
import { rate } from "@/lib/format";

// The job board (phase 5B UI design). The apply by email address and job codes arrive
// with the connected inbox later in phase 5B.
export default async function JobsPage() {
  const { jobs } = await api.get<{ jobs: JobSummary[] }>("/jobs");
  const total = jobs.reduce((n, j) => n + j.candidates, 0);
  const undecided = jobs.reduce((n, j) => n + j.undecided, 0);
  return (
    <>
      <div className="h-hero">
        <div>
          <div className="h-eyebrow">Job board</div>
          <h1 className="h-h1">Open roles.</h1>
          <p className="h-intro">
            Every job has a rubric built from its ad. Candidates from the apply page, uploads and
            the connected inbox are scored against it. Put a job&apos;s code in an email subject to file a CV under it.
          </p>
        </div>
        <div className="h-stats" aria-label="Job counts">
          <div className="h-stat">
            <strong>{String(jobs.length).padStart(2, "0")}</strong>
            <small>Jobs</small>
          </div>
          <div className="h-stat">
            <strong>{String(total).padStart(2, "0")}</strong>
            <small>Candidates</small>
          </div>
          <div className="h-stat">
            <strong>{String(undecided).padStart(2, "0")}</strong>
            <small>To decide</small>
          </div>
        </div>
      </div>
      <div className="h-card">
        <div className="h-chead">
          <div>
            <h2>Jobs</h2>
            <small>Select a job to review its ranked candidates</small>
          </div>
        </div>
        {jobs.length === 0 ? (
          <p className="h-empty">No jobs yet. Create one through the API, or run the demo seed.</p>
        ) : (
          <table className="h-table">
            <caption className="sr-only">Jobs with candidate counts and agreement rate</caption>
            <thead>
              <tr>
                <th scope="col">Job</th>
                <th scope="col" className="hide-sm">
                  Candidates
                </th>
                <th scope="col">To decide</th>
                <th scope="col" className="hide-sm">
                  Needs review
                </th>
                <th scope="col" className="hide-md hide-sm">
                  Agreement
                </th>
                <th scope="col" className="hide-sm">
                  Rubric
                </th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j) => (
                <tr key={j.id}>
                  <td>
                    <Link href={`/jobs/${j.id}`} className="h-t1">
                      {j.title}
                    </Link>
                    <div className="h-t2">
                      {j.code ? `${j.code} · ` : ""}
                      {j.location} · {j.state.toLowerCase().replaceAll("_", " ")}
                    </div>
                  </td>
                  <td className="num hide-sm">{j.candidates}</td>
                  <td className="num" style={{ color: "var(--h-blue)" }}>
                    {j.undecided}
                  </td>
                  <td className="num hide-sm">{j.needs_review}</td>
                  <td className="hide-md hide-sm">
                    {rate(j.agreement.rate)}
                    {j.agreement.overrides ? ` (${j.agreement.overrides} overrides)` : ""}
                  </td>
                  <td className="hide-sm">
                    <span className={`h-pill${j.approved_rubric_version ? " ok" : " warn"}`}>
                      {j.approved_rubric_version ? `v${j.approved_rubric_version} approved` : "not approved"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
