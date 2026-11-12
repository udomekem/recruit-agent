"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, useTransition } from "react";

import { BAND_LABEL, stateLabel } from "@/lib/format";

import { decide } from "../../actions";

type Choice = "shortlist" | "reject";
const MIN_REASON = 10; // the API enforces the same for overrides

function isOverride(band: string | null, choice: Choice): boolean {
  return (band === "reject" && choice === "shortlist") || (band === "advance" && choice === "reject");
}

function defaultReason(band: string | null, choice: Choice): string {
  if (!band) return "";
  if (band === "maybe") return `Recommendation was maybe; decided to ${choice}`;
  return `Agrees with the recommendation: ${band}`;
}

/** The decision bar at the foot of the review panel. Keys: s shortlist, r reject, Enter
 * confirms, Esc cancels, j and k next and previous in the list. */
export function ReviewPanel(props: {
  candidateId: string;
  jobId: string | null;
  state: string;
  version: number;
  band: string | null;
  prevHref: string | null;
  nextHref: string | null;
  erased: boolean;
}) {
  const router = useRouter();
  const [choice, setChoice] = useState<Choice | null>(null);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, start] = useTransition();
  const box = useRef<HTMLDivElement>(null);
  const reasonRef = useRef<HTMLTextAreaElement>(null);
  const canDecide = props.state === "SCORED" && !props.erased && props.jobId !== null;
  const override = choice ? isOverride(props.band, choice) : false;
  const tooShort = override && reason.trim().length < MIN_REASON;

  function open(c: Choice) {
    setChoice(c);
    setError(null);
    setReason(isOverride(props.band, c) ? "" : defaultReason(props.band, c));
  }

  function confirm() {
    if (!choice || !props.jobId || pending) return;
    if (tooShort || !reason.trim()) {
      setError(`This goes against the AI's recommendation. Give a reason of at least ${MIN_REASON} characters.`);
      reasonRef.current?.focus();
      return;
    }
    start(async () => {
      const r = await decide({
        candidateId: props.candidateId,
        jobId: props.jobId!,
        choice,
        reason: reason.trim(),
        expectedVersion: props.version,
      });
      if (r?.error) setError(r.error);
    });
  }

  useEffect(() => {
    if (choice) {
      if (override) reasonRef.current?.focus();
      else box.current?.querySelector<HTMLButtonElement>("[data-confirm]")?.focus();
    }
  }, [choice, override]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const typing = (e.target as HTMLElement).closest("input, textarea, select");
      if (e.key === "Escape") {
        setChoice(null);
        return;
      }
      if (e.key === "Enter" && choice && !(typing && e.shiftKey)) {
        if (typing && (e.target as HTMLElement).tagName !== "TEXTAREA") return;
        e.preventDefault();
        confirm();
        return;
      }
      if (typing) return;
      if (e.key === "j" && props.nextHref) router.push(props.nextHref);
      else if (e.key === "k" && props.prevHref) router.push(props.prevHref);
      else if (e.key === "s" && canDecide) open("shortlist");
      else if (e.key === "r" && canDecide) open("reject");
      else return;
      e.preventDefault();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  return (
    <section aria-label="Decision" className="h-bottom">
      {choice ? (
        <div ref={box} role="dialog" aria-label={`Confirm ${choice}`} style={{ marginBottom: 12 }}>
          <p style={{ margin: 0, fontSize: 13 }}>
            {choice === "shortlist" ? "Shortlist" : "Reject"} this candidate. AI recommendation:{" "}
            <strong>{props.band ? BAND_LABEL[props.band] : "none"}</strong>.
            {override ? (
              <strong style={{ marginLeft: 4, color: "var(--h-red)" }}>
                This goes against the recommendation: say why (logged for the agreement rate).
              </strong>
            ) : null}
          </p>
          {choice === "reject" ? (
            <p className="h-help">
              Only job related reasons. The AI drafts a rejection email from the requirements this
              person did not meet; you read it before anything is sent.
            </p>
          ) : null}
          <label htmlFor="reason" className="h-label">
            Reason
          </label>
          <textarea
            id="reason"
            ref={reasonRef}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={2}
            maxLength={2000}
            required
            aria-invalid={tooShort}
            aria-describedby="reason-help"
            className="h-input"
          />
          <p id="reason-help" className="h-help">
            <kbd>Enter</kbd> confirms, <kbd>Shift</kbd>+<kbd>Enter</kbd> new line, <kbd>Esc</kbd> cancels.
          </p>
          {error ? (
            <p role="alert" className="h-error">
              {error}
            </p>
          ) : null}
          <div className="h-actions" style={{ marginTop: 10, justifyContent: "flex-end" }}>
            <button type="button" onClick={() => setChoice(null)} className="h-btn">
              Cancel
            </button>
            <button
              type="button"
              data-confirm
              disabled={pending}
              onClick={confirm}
              className={`h-btn ${choice === "reject" ? "danger" : "primary"}`}
            >
              {pending ? "Saving" : `Confirm ${choice}`}
            </button>
          </div>
        </div>
      ) : null}
      <div className="h-bottom-row">
        <span className="h-astatus">
          {canDecide ? (
            <>
              Your decision. <kbd>s</kbd> shortlist, <kbd>r</kbd> reject, <kbd>j</kbd> <kbd>k</kbd> next and previous
            </>
          ) : (
            <>Decision made or not available: {stateLabel(props.state).toLowerCase()}</>
          )}
        </span>
        {canDecide && !choice ? (
          <div className="h-actions">
            <button type="button" onClick={() => open("reject")} className="h-btn">
              ✕ Reject
            </button>
            <button type="button" onClick={() => open("shortlist")} className="h-btn primary">
              ✓ Shortlist
            </button>
          </div>
        ) : null}
      </div>
    </section>
  );
}
