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
    <ul aria-label="Checks" className="h-checks">
      {checks.map((c) => (
        <li key={c.rule} data-ok={c.passed}>
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
      <section aria-label="Rejection email">
        <h2 className="h-panel-title">Rejection email</h2>
        <p role="status" className="h-note">The email is being drafted. Reload in a few seconds.</p>
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
    <section aria-labelledby="email-h">
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "baseline", gap: 12 }}>
        <h2 id="email-h" className="h-panel-title" style={{ margin: 0 }}>
          {sentView ? "Rejection email sent" : "Rejection email draft"}
        </h2>
        <span className="h-astatus">
          version {draft.version} by {draft.source === "agent" ? `the writer (${draft.prompt})` : draft.source === "template" ? "the plain template" : `you (${draft.actor_id})`}
        </span>
      </div>

      {draft.needs_edit && !sentView ? (
        <p role="note" className="h-banner warn" style={{ marginTop: 12 }}>
          Read this before sending: plain template used because {draft.fallback_reason}.
        </p>
      ) : null}

      {draft.erased ? (
        <p className="h-note" style={{ marginTop: 12 }}>The email text was erased with the candidate&apos;s data.</p>
      ) : editing ? (
        <div style={{ marginTop: 12 }}>
          <label htmlFor="email-body" className="h-label">
            Email text (the greeting, contact line, deletion line and sign off are added automatically)
          </label>
          <textarea
            id="email-body"
            ref={editRef}
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={10}
            maxLength={4000}
            className="h-input"
          />
          <div className="h-actions" style={{ marginTop: 10 }}>
            <button type="button" disabled={pending} onClick={save} className="h-btn primary">
              {pending ? "Checking" : "Save"}
            </button>
            <button type="button" onClick={() => setEditing(false)} className="h-btn">
              Cancel <kbd>Esc</kbd>
            </button>
          </div>
        </div>
      ) : (
        <pre aria-label="Email as it will read" className="h-email">
          {outbox ? `Subject: ${outbox.subject}\n\n` : ""}
          {draft.preview}
        </pre>
      )}

      {draft.reasons.length && !draft.erased ? (
        <div>
          <h3 className="h-section" style={{ marginTop: 18 }}>Reasons used</h3>
          <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>
            {draft.reasons.map((r) => (
              <li key={r.source_id}>
                {r.requirement} <span className="h-astatus">({r.kind === "answer" ? "screening answer" : "requirement"})</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {!draft.erased ? <Checks checks={draft.checks} /> : null}

      {error ? (
        <p role="alert" className="h-error">
          {error}
        </p>
      ) : null}

      {props.state === "REJECTION_DRAFTED" && !editing ? (
        <div className="h-actions" style={{ marginTop: 16, alignItems: "center" }}>
          <button
            type="button"
            ref={sendRef}
            data-send
            disabled={!canSend || pending}
            onClick={send}
            className="h-btn primary"
          >
            {pending ? "Sending" : "Send email"} <kbd>Enter</kbd>
          </button>
          <button
            type="button"
            onClick={() => {
              setBody(draft.body);
              setEditing(true);
            }}
            className="h-btn"
          >
            Edit <kbd>e</kbd>
          </button>
          <span className="h-astatus">The name and address are filled in when it is sent.</span>
        </div>
      ) : null}

      {outbox ? (
        <div style={{ marginTop: 16, fontSize: 13 }}>
          <p style={{ margin: 0 }}>
            <strong>{STATUS_LABEL[outbox.status] ?? outbox.status}</strong> · sent by {outbox.actor_id} at {when(outbox.queued_at)}
            {outbox.sent_at ? ` · delivered ${when(outbox.sent_at)}` : ""} · {outbox.attempts} attempt{outbox.attempts === 1 ? "" : "s"} ({outbox.provider})
          </p>
          {outbox.status === "failed" ? (
            <form action={retryDelivery} className="h-inline-form" style={{ marginTop: 8 }}>
              <input type="hidden" name="candidate_id" value={props.candidateId} />
              <input type="hidden" name="back" value={`/candidates/${props.candidateId}`} />
              <span className="h-error" style={{ margin: 0 }}>{outbox.last_error}</span>
              <button className="h-btn small">Retry delivery</button>
            </form>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
