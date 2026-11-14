import "server-only";

// Server side API client. The recruiter token and the API address never reach the
// browser: no public (browser exposed) variables, and this module refuses to load in
// client code.

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(detail);
  }
}

function config(): { url: string; token: string } {
  const url = process.env.API_URL ?? "http://localhost:8000";
  const token = process.env.RECRUITER_TOKEN ?? "";
  if (!token) throw new Error("RECRUITER_TOKEN is not set (run make local-env)");
  return { url, token };
}

async function call<T>(method: "GET" | "POST" | "PUT", path: string, body?: unknown): Promise<T> {
  const { url, token } = config();
  const res = await fetch(`${url}${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
    cache: "no-store",
  });
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) {
    const detail =
      typeof data?.detail === "string"
        ? data.detail
        : Array.isArray(data?.detail)
          ? data.detail.map((d: { msg?: string }) => d.msg).join("; ")
          : `request failed (${res.status})`;
    throw new ApiError(res.status, detail);
  }
  return data as T;
}

export const api = {
  get: <T>(path: string) => call<T>("GET", path),
  post: <T>(path: string, body?: unknown) => call<T>("POST", path, body),
  put: <T>(path: string, body?: unknown) => call<T>("PUT", path, body),
};

// ---- response shapes (only the fields the dashboard uses) ----------------------------

export type Agreement = {
  decided: number;
  counted: number;
  agreed: number;
  overrides: number;
  maybe_or_none: number;
  rate: number | null;
};

export type Flag = { kind: string; text: string };

export type JobSummary = {
  id: string;
  title: string;
  code: string | null;
  state: string;
  location: string;
  approved_rubric_version: number | null;
  candidates: number;
  by_state: Record<string, number>;
  undecided: number;
  needs_review: number;
  agreement: Agreement;
};

export type RankedRow = {
  id: string;
  label: string;
  state: string;
  state_version: number;
  applied_at: string;
  erased: boolean;
  rank?: number;
  total?: number;
  band?: "advance" | "maybe" | "reject";
  flags?: Flag[];
  knockouts?: { key: string; outcome: string }[];
  rubric_version?: number;
  decision?: { decision: string; recommended: string; override: boolean };
};

export type Ranked = {
  job_id: string;
  rubric_version: number | null;
  outdated: number;
  agreement: Agreement;
  scored: RankedRow[];
  unscored: RankedRow[];
};

export type Audit = {
  transition_id: string;
  from_state: string | null;
  to_state: string;
  actor_type: string;
  actor_id: string;
  reason: string;
  occurred_at: string;
};

export type CandidateDetail = {
  id: string;
  state: string;
  state_version: number;
  display_label: string;
  job_id: string | null;
  erased: boolean;
  audit: Audit[];
};

export type ScoreCriterion = {
  criterion_id: string;
  text: string | null;
  kind: string | null;
  weight: number | null;
  verdict: "met" | "partly_met" | "not_met";
  points: number;
  reason: string | null;
  quote: string | null;
};

export type ScoreDetail = {
  total: number;
  band: "advance" | "maybe" | "reject";
  reasons: string[];
  flags: Flag[];
  criteria: ScoreCriterion[];
  answers: { key: string; value?: unknown; rule: string | null; outcome: string; note?: string }[];
  rubric_version: number;
  prompt_id: string;
  prompt_version: string;
  model: string;
  erased: boolean;
};

export type ParseDetail = { redacted_text: string | null; status: string };

export type Contact = { name: string | null; email: string | null; phone: string | null };

// ---- rejection emails (phase 5) --------------------------------------------------------

export type Check = { rule: string; passed: boolean; detail: string };

export type Draft = {
  id: string;
  version: number;
  source: "agent" | "template" | "recruiter";
  reasons: { source_id: string; kind: string; requirement: string; sentence: string }[];
  body: string;
  preview: string;
  checks: Check[];
  fallback_reason: string | null;
  needs_edit: boolean;
  prompt: string | null;
  model: string | null;
  actor_id: string;
  erased: boolean;
  created_at: string;
};

export type Outbox = {
  id: string;
  status: "queued" | "sending" | "sent" | "failed" | "cancelled";
  provider: string;
  subject: string;
  attempts: number;
  last_error: string | null;
  actor_id: string;
  queued_at: string;
  sent_at: string | null;
};

export type Rejection = { draft: Draft | null; versions: number; outbox: Outbox | null };

export type RejectionQueue = {
  drafts: {
    id: string;
    label: string;
    job_id: string | null;
    job_title: string | null;
    state_version: number;
    source: string | null;
    needs_edit: boolean;
    fallback_reason: string | null;
  }[];
  undelivered: { id: string; label: string; job_title: string | null; attempts: number; last_error: string | null }[];
};

// ---- connected inbox (phase 5B) ------------------------------------------------------------

export type MailboxOut = {
  id: string;
  provider: "gmail" | "mailpit" | "fake";
  address: string;
  label: string | null;
  status: "active" | "paused" | "needs_label" | "needs_reconnect" | "disconnected";
  last_polled_at: string | null;
  last_error: string | null;
  connected_by: string;
  connected_at: string;
};

export type InboxAttachmentOut = {
  outcome: "ingested" | "duplicate" | "skipped";
  note: string;
  candidate_id: string | null;
  label: string | null;
  state: string | null;
  state_version: number | null;
  job_title: string | null;
  needs_job: boolean;
  suggested: string[];
  match: string | null;
};

export type InboxMessageOut = {
  id: string;
  mailbox_id: string;
  subject: string;
  sender_kind: "seek" | "indeed" | "direct" | "other";
  status: "received" | "working" | "not_a_cv" | "ingested" | "duplicate" | "failed";
  route: string | null;
  detail: string;
  received_at: string;
  attachments: InboxAttachmentOut[];
};

export type InboxPage = {
  mailboxes: MailboxOut[];
  messages: InboxMessageOut[];
  open_jobs: { id: string; title: string; code: string | null }[];
  can_connect: { gmail: boolean; mailpit: boolean };
};
