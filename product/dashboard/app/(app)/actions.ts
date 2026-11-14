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

// ---- rejection emails (phase 5) --------------------------------------------------------

export async function saveDraft(input: {
  candidateId: string;
  body: string;
  expectedDraftVersion: number;
}): Promise<ActionResult> {
  await requireSession();
  try {
    await api.put(`/candidates/${input.candidateId}/rejection`, {
      body: input.body,
      expected_draft_version: input.expectedDraftVersion,
    });
  } catch (e) {
    if (e instanceof ApiError && e.status === 422) {
      return { error: `Not saved. ${e.detail}` };
    }
    return message(e);
  }
  revalidatePath(`/candidates/${input.candidateId}`);
  return {};
}

export async function sendRejection(input: {
  candidateId: string;
  expectedVersion: number;
}): Promise<ActionResult> {
  await requireSession();
  try {
    await api.post(`/candidates/${input.candidateId}/send-rejection`, {
      reason: "rejection email sent",
      expected_version: input.expectedVersion,
    });
  } catch (e) {
    return message(e);
  }
  revalidatePath(`/candidates/${input.candidateId}`);
  revalidatePath("/review");
  return {};
}

export async function retryDelivery(form: FormData): Promise<void> {
  await requireSession();
  const id = String(form.get("candidate_id"));
  const back = String(form.get("back") ?? `/candidates/${id}`);
  try {
    await api.post(`/candidates/${id}/rejection/retry-delivery`);
  } catch (e) {
    const r = message(e);
    redirect(`/review?error=${encodeURIComponent(r.error ?? "failed")}`);
  }
  revalidatePath("/review");
  redirect(/^\/[a-z]/.test(back) ? back : "/review"); // same site paths only
}

// ---- connected inbox (phase 5B) ------------------------------------------------------------

const UUID = /^[0-9a-f-]{36}$/;

function idOf(form: FormData, key: string): string {
  const v = String(form.get(key) ?? "");
  if (!UUID.test(v)) redirect(`/inbox?error=${encodeURIComponent("unknown item")}`);
  return v;
}

async function inboxCall(fn: () => Promise<unknown>, done: string): Promise<void> {
  await requireSession();
  try {
    await fn();
  } catch (e) {
    const r = message(e);
    redirect(`/inbox?error=${encodeURIComponent(r.error ?? "failed")}`);
  }
  revalidatePath("/inbox");
  redirect(`/inbox?done=${encodeURIComponent(done)}`);
}

export async function connectMailpit(form: FormData): Promise<void> {
  const label = String(form.get("label") ?? "Applications").trim() || "Applications";
  await inboxCall(() => api.post("/inbox/mailpit", { label }), "The test inbox is connected.");
}

export async function startGmail(): Promise<void> {
  await requireSession();
  let url = "";
  try {
    url = (await api.post<{ url: string }>("/inbox/gmail/start")).url;
  } catch (e) {
    const r = message(e);
    redirect(`/inbox?error=${encodeURIComponent(r.error ?? "failed")}`);
  }
  // Only ever Google's own sign in page (the API builds the address).
  if (!url.startsWith("https://accounts.google.com/")) redirect("/inbox?error=unexpected%20sign%20in%20address");
  redirect(url);
}

export async function setLabel(form: FormData): Promise<void> {
  const id = idOf(form, "mailbox_id");
  const label = String(form.get("label") ?? "").trim();
  await inboxCall(() => api.put(`/inbox/mailboxes/${id}`, { label }), `Reading the label "${label}".`);
}

export async function setMailboxStatus(form: FormData): Promise<void> {
  const id = idOf(form, "mailbox_id");
  const status = String(form.get("status")) === "paused" ? "paused" : "active";
  await inboxCall(
    () => api.put(`/inbox/mailboxes/${id}`, { status }),
    status === "paused" ? "Paused." : "Reading again.",
  );
}

export async function pollNow(form: FormData): Promise<void> {
  const id = idOf(form, "mailbox_id");
  await inboxCall(() => api.post(`/inbox/mailboxes/${id}/poll`), "Checking now. Refresh in a moment.");
}

export async function disconnectMailbox(form: FormData): Promise<void> {
  const id = idOf(form, "mailbox_id");
  await inboxCall(() => api.post(`/inbox/mailboxes/${id}/disconnect`), "Disconnected. The access was deleted.");
}

export async function pickJob(form: FormData): Promise<void> {
  const id = idOf(form, "candidate_id");
  const jobId = idOf(form, "job_id");
  await inboxCall(
    () => api.post(`/candidates/${id}/pick-job`, { job_id: jobId, expected_version: Number(form.get("expected_version")) }),
    "Job set. The CV is being scored.",
  );
}
