// Display helpers. No rules live here: bands, overrides and rates come from the API.

export const BAND_LABEL: Record<string, string> = {
  advance: "Advance",
  maybe: "Maybe",
  reject: "Reject",
};

export const BAND_CLASS: Record<string, string> = {
  advance: "bg-emerald-100 text-emerald-900 dark:bg-emerald-900 dark:text-emerald-100",
  maybe: "bg-amber-100 text-amber-900 dark:bg-amber-900 dark:text-amber-100",
  reject: "bg-rose-100 text-rose-900 dark:bg-rose-900 dark:text-rose-100",
};

export const VERDICT_LABEL: Record<string, string> = {
  met: "Met",
  partly_met: "Partly met",
  not_met: "Not met",
};

export const VERDICT_CLASS: Record<string, string> = {
  met: "text-emerald-800 dark:text-emerald-300",
  partly_met: "text-amber-800 dark:text-amber-300",
  not_met: "text-rose-800 dark:text-rose-300",
};

/** Flags that a recruiter must see first. */
export const SERIOUS_FLAGS = new Set(["injection_suspected", "hidden_text"]);

export const FLAG_LABEL: Record<string, string> = {
  injection_suspected: "Possible instructions to the AI",
  hidden_text: "Hidden text removed",
  salary_above_band: "Salary above band",
  location_no: "Location no",
  answers_missing: "Answers missing",
  rubric_outdated: "Older rubric",
  answer_flag: "Answer flag",
};

export const STATE_LABEL: Record<string, string> = {
  APPLIED: "Applied",
  PARSED: "Parsed",
  SCORED: "To decide",
  SHORTLISTED: "Shortlisted",
  REJECTED: "Rejected",
  REJECTION_DRAFTED: "Rejected (email drafted)",
  REJECTION_SENT: "Rejected (email sent)",
  NEEDS_REVIEW: "Needs review",
  WITHDRAWN: "Withdrawn",
};

export function stateLabel(s: string): string {
  return STATE_LABEL[s] ?? s.replaceAll("_", " ").toLowerCase();
}

export function rate(r: number | null): string {
  return r === null ? "no decisions yet" : `${Math.round(r * 100)}%`;
}

export function when(iso: string): string {
  return new Date(iso).toLocaleString("en-AU", {
    timeZone: "Australia/Sydney",
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}
