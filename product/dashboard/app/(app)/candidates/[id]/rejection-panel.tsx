"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, useTransition } from "react";

import type { Check, Rejection } from "@/lib/api";
import { when } from "@/lib/format";

import { retryDelivery, saveDraft, sendRejection } from "../../actions";

const RULE_LABEL: Record<string, string> = {
  H1: "Reasons are real",
  H2: "No protected wording",
  H3: "No harsh wording",
  H4: "No scores",
  H5: "Nothing copied from the CV",
  H6: "No links or contact details",
  H7: "No job offer wording",
  H8: "Length",
};

const STATUS_LABEL: Record<string, string> = {
  queued: "Queued for delivery",
  sending: "Sending",
  sent: "Delivered",
  failed: "Not delivered",
  cancelled: "Cancelled",
};

function Checks({ checks }: { checks: Check[] }) {
  return (
    <ul aria-label="Checks" className="mt-2 grid gap-1 text-xs sm:grid-cols-2">
      {checks.map((c) => (
        <li key={c.rule} className={c.passed ? "text-emerald-800 dark:text-emerald-300" : "font-medium text-rose-800 dark:text-rose-300"}>
          {c.passed ? "Pass" : "Fail"}: {RULE_LABEL[c.rule] ?? c.rule}
          {c.passed ? "" : ` (${c.detail})`}
        </li>
      ))}
    </ul>
  );
}

export function RejectionPanel(props: {
  candidateId: string;
  state: string;
  version: number;
  rejection: Rejection | null;
}) {
  const router = useRouter();
  const draft = props.rejection?.draft ?? null;
  const outbox = props.rejection?.outbox ?? null;
  const [editing, setEditing] = useState(false);
  const [body, setBody] = useState(draft?.body ?? "");
  const [error, setError] = useState<string | null>(null);
  const [pending, start] = useTransition();
  const sendRef = useRef<HTMLButtonElement>(null);
  const editRef = useRef<HTMLTextAreaElement>(null);
  const canSend = props.state === "REJECTION_DRAFTED" && draft !== null && !draft.erased && draft.checks.every((c) => c.passed);

  useEffect(() => {
    if (editing) editRef.current?.focus();
    else if (canSend) sendRef.current?.focus(); // Enter sends: the draft box is the confirm step
  }, [editing, canSend, draft?.version]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      if ((e.target as HTMLElement).closest("input, textarea, select")) {
        if (e.key === "Escape") setEditing(false);
        return;
      }
      if (e.key === "e" && props.state === "REJECTION_DRAFTED" && draft) {
        e.preventDefault();
        setBody(draft.body);
        setEditing(true);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  if (props.state === "REJECTED") {
    return (
      <section aria-label="Rejection email" className="mt-4 rounded border border-zinc-300 p-3 dark:border-zinc-700">
        <h2 className="font-semibold">Rejection email</h2>
        <p role="status" className="mt-1 text-sm">The email is being drafted. Reload in a few seconds.</p>
      </section>
    );
  }
  if (!draft) return null;

  function save() {
    setError(null);
    start(async () => {
      const r = await saveDraft({ candidateId: props.candidateId, body, expectedDraftVersion: draft!.version });
      if (r?.error) setError(r.error);
      else {
        setEditing(false);
        router.refresh();
      }
    });
  }

  function send() {
    setError(null);
    start(async () => {
      const r = await sendRejection({ candidateId: props.candidateId, expectedVersion: props.version });
      if (r?.error) setError(r.error);
      else router.refresh();
    });
  }

  const sentView = props.state === "REJECTION_SENT";
  return (
    <section aria-labelledby="email-h" className="mt-4 rounded border border-zinc-300 bg-white p-3 dark:border-zinc-700 dark:bg-zinc-900">
      <div className="flex flex-wrap items-baseline gap-3">
        <h2 id="email-h" className="font-semibold">
          {sentView ? "Rejection email sent" : "Rejection email draft"}
        </h2>
        <span className="text-xs text-zinc-700 dark:text-zinc-400">
          version {draft.version} by {draft.source === "agent" ? `the writer (${draft.prompt})` : draft.source === "template" ? "the plain template" : `you (${draft.actor_id})`}
        </span>
      </div>

      {draft.needs_edit && !sentView ? (
        <p role="note" className="mt-2 rounded bg-amber-100 px-3 py-2 text-sm text-amber-950 dark:bg-amber-900 dark:text-amber-50">
          Read this before sending: plain template used because {draft.fallback_reason}.
        </p>
      ) : null}

      {draft.erased ? (
        <p className="mt-2 text-sm">The email text was erased with the candidate&apos;s data.</p>
      ) : editing ? (
        <div className="mt-2 space-y-2">
          <label htmlFor="email-body" className="block text-sm font-medium">
            Email text (the greeting, contact line, deletion line and sign off are added automatically)
          </label>
          <textarea
            id="email-body"
            ref={editRef}
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={10}
            maxLength={4000}
            className="w-full rounded border border-zinc-400 bg-white px-2 py-1 text-sm dark:border-zinc-600 dark:bg-zinc-950"
          />
          <div className="flex gap-2">
            <button type="button" disabled={pending} onClick={save} className="rounded bg-blue-700 px-3 py-1 font-medium text-white hover:bg-blue-800 disabled:opacity-60">
              {pending ? "Checking" : "Save"}
            </button>
            <button type="button" onClick={() => setEditing(false)} className="rounded border border-zinc-400 px-3 py-1">
              Cancel <kbd>Esc</kbd>
            </button>
          </div>
        </div>
      ) : (
        <pre aria-label="Email as it will read" className="mt-2 whitespace-pre-wrap rounded bg-zinc-50 p-3 font-sans text-sm dark:bg-zinc-950">
          {outbox ? `Subject: ${outbox.subject}\n\n` : ""}
          {draft.preview}
        </pre>
      )}

      {draft.reasons.length && !draft.erased ? (
        <div className="mt-2 text-sm">
          <h3 className="font-medium">Reasons used</h3>
          <ul className="mt-1 list-disc pl-6">
            {draft.reasons.map((r) => (
              <li key={r.source_id}>
                {r.requirement} <span className="text-zinc-700 dark:text-zinc-400">({r.kind === "answer" ? "screening answer" : "requirement"})</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {!draft.erased ? <Checks checks={draft.checks} /> : null}

      {error ? (
        <p role="alert" className="mt-2 text-sm text-rose-800 dark:text-rose-300">
          {error}
        </p>
      ) : null}

      {props.state === "REJECTION_DRAFTED" && !editing ? (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            type="button"
            ref={sendRef}
            data-send
            disabled={!canSend || pending}
            onClick={send}
            className="rounded bg-rose-700 px-3 py-1 font-medium text-white hover:bg-rose-800 disabled:opacity-60"
          >
            {pending ? "Sending" : "Send email"} <kbd>Enter</kbd>
          </button>
          <button
            type="button"
            onClick={() => {
              setBody(draft.body);
              setEditing(true);
            }}
            className="rounded border border-zinc-400 px-3 py-1"
          >
            Edit <kbd>e</kbd>
          </button>
          <span className="text-xs text-zinc-700 dark:text-zinc-400">The name and address are filled in when it is sent.</span>
        </div>
      ) : null}

      {outbox ? (
        <div className="mt-3 text-sm">
          <p>
            <strong>{STATUS_LABEL[outbox.status] ?? outbox.status}</strong> · sent by {outbox.actor_id} at {when(outbox.queued_at)}
            {outbox.sent_at ? ` · delivered ${when(outbox.sent_at)}` : ""} · {outbox.attempts} attempt{outbox.attempts === 1 ? "" : "s"} ({outbox.provider})
          </p>
          {outbox.status === "failed" ? (
            <form action={retryDelivery} className="mt-2 flex items-center gap-2">
              <input type="hidden" name="candidate_id" value={props.candidateId} />
              <input type="hidden" name="back" value={`/candidates/${props.candidateId}`} />
              <span className="text-rose-800 dark:text-rose-300">{outbox.last_error}</span>
              <button className="rounded border border-zinc-500 px-2 py-1">Retry delivery</button>
            </form>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
