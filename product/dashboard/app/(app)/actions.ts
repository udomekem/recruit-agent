"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { api, ApiError, type Ranked } from "@/lib/api";
import { requireSession, signOut } from "@/lib/session";

export async function logout(): Promise<void> {
  await signOut();
  redirect("/login");
}

export type ActionResult = { error?: string; conflict?: boolean };

function message(e: unknown): ActionResult {
  if (e instanceof ApiError) {
    if (e.status === 409) {
      return {
        conflict: true,
        error: "This candidate changed since you opened it. Reload to see the latest.",
      };
    }
    return { error: e.detail };
  }
  throw e;
}

/** The next candidate to decide after `current`, in rank order (wrapping round). */
async function nextUndecided(jobId: string, current: string): Promise<string | null> {
  const ranked = await api.get<Ranked>(`/jobs/${jobId}/candidates`);
  const rows = ranked.scored;
  const at = rows.findIndex((r) => r.id === current);
  const ordered = [...rows.slice(at + 1), ...rows.slice(0, Math.max(at, 0))];
  return ordered.find((r) => r.state === "SCORED" && !r.erased)?.id ?? null;
}

export async function decide(input: {
  candidateId: string;
  jobId: string;
  choice: "shortlist" | "reject";
  reason: string;
  expectedVersion: number;
}): Promise<ActionResult> {
  await requireSession();
  try {
    await api.post(`/candidates/${input.candidateId}/${input.choice}`, {
      reason: input.reason,
      expected_version: input.expectedVersion,
    });
  } catch (e) {
    return message(e);
  }
  revalidatePath(`/jobs/${input.jobId}`);
  const next = await nextUndecided(input.jobId, input.candidateId);
  redirect(next ? `/candidates/${next}` : `/jobs/${input.jobId}?done=1`);
}

export async function resolve(form: FormData): Promise<void> {
  await requireSession();
  const id = String(form.get("candidate_id"));
  const action = String(form.get("action")) === "retry" ? "resolve-retry" : "reject";
  const reason = String(form.get("reason") ?? "").trim() || "Resolved from the review queue";
  try {
    await api.post(`/candidates/${id}/${action}`, {
      reason,
      expected_version: Number(form.get("expected_version")),
    });
  } catch (e) {
    const r = message(e);
    redirect(`/review?error=${encodeURIComponent(r.error ?? "failed")}`);
  }
  revalidatePath("/review");
  redirect("/review?done=1");
}

export async function rescore(form: FormData): Promise<void> {
  await requireSession();
  const jobId = String(form.get("job_id"));
  const res = await api.post<{ queued: number }>(`/jobs/${jobId}/rescore`);
  redirect(`/jobs/${jobId}?rescoring=${res.queued}`);
}
