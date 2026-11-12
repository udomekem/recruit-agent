import "server-only";

import { api, type JobSummary, type Ranked, type RankedRow } from "./api";

// The candidate queue for the workbench (phase 5B UI design): one job or every job,
// filtered by status, band, flag and a label search. Ranking stays the API's.

export type Status = "" | "todo" | "shortlisted" | "rejected";

export const AFTER_SHORTLIST = new Set([
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
export const REJECTED = new Set(["REJECTED", "REJECTION_DRAFTED", "REJECTION_SENT"]);

export type Filters = { job: string; status: Status; band: string; flag: string; q: string };

export type Row = RankedRow & { jobId: string; jobTitle: string };

export type Queue = {
  jobs: JobSummary[];
  job: JobSummary | null; // the one job in view, or null for every job
  ranked: Ranked | null; // that job's ranking (agreement, outdated) when one job is in view
  all: Row[]; // every scored row in scope, before the status and other filters
  rows: Row[]; // what the list shows
  counts: Record<Status, number>;
  unscored: number;
  flags: string[];
};

export function readFilters(s: Record<string, string | undefined>, defaultJob = "all"): Filters {
  const status = (["todo", "shortlisted", "rejected"] as const).find((x) => x === s.status) ?? "";
  return {
    job: s.job || defaultJob,
    status,
    band: ["advance", "maybe", "reject"].includes(s.band ?? "") ? s.band! : "",
    flag: s.flag ?? "",
    q: (s.q ?? "").slice(0, 60),
  };
}

export function statusOf(state: string): Status {
  if (state === "SCORED") return "todo";
  if (AFTER_SHORTLIST.has(state)) return "shortlisted";
  if (REJECTED.has(state)) return "rejected";
  return "";
}

/** Query string for a filter set, without empty values. */
export function qs(f: Partial<Filters> & { tab?: string }, defaultJob = "all"): string {
  const p = new URLSearchParams();
  if (f.job && f.job !== defaultJob) p.set("job", f.job);
  for (const k of ["status", "band", "flag", "q", "tab"] as const) {
    const v = f[k];
    if (v) p.set(k, v);
  }
  const s = p.toString();
  return s ? `?${s}` : "";
}

export async function loadQueue(f: Filters): Promise<Queue> {
  const { jobs } = await api.get<{ jobs: JobSummary[] }>("/jobs");
  const inView = f.job === "all" ? jobs : jobs.filter((j) => j.id === f.job);
  const ranked = await Promise.all(inView.map((j) => api.get<Ranked>(`/jobs/${j.id}/candidates`)));
  const all: Row[] = [];
  let unscored = 0;
  inView.forEach((j, i) => {
    unscored += ranked[i].unscored.length;
    for (const r of ranked[i].scored) all.push({ ...r, jobId: j.id, jobTitle: j.title });
  });
  // One job keeps the API's rank; every job sorts by score so the best rise to the top.
  if (inView.length > 1) all.sort((a, b) => (b.total ?? -1) - (a.total ?? -1));
  const q = f.q.trim().toLowerCase();
  const base = all.filter(
    (r) =>
      (!f.band || r.band === f.band) &&
      (!f.flag || (r.flags ?? []).some((x) => x.kind === f.flag)) &&
      (!q || r.label.toLowerCase().includes(q)),
  );
  const counts: Record<Status, number> = { "": base.length, todo: 0, shortlisted: 0, rejected: 0 };
  for (const r of base) {
    const s = statusOf(r.state);
    if (s) counts[s] += 1;
  }
  return {
    jobs,
    job: f.job === "all" ? null : (inView[0] ?? null),
    ranked: inView.length === 1 && f.job !== "all" ? ranked[0] : null,
    all,
    rows: f.status ? base.filter((r) => statusOf(r.state) === f.status) : base,
    counts,
    unscored,
    flags: [...new Set(all.flatMap((r) => (r.flags ?? []).map((x) => x.kind)))],
  };
}
