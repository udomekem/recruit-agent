"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, useTransition } from "react";

import { BAND_LABEL } from "@/lib/format";

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

export function ReviewPanel(props: {
  candidateId: string;
  jobId: string | null;
  state: string;
  version: number;
  band: string | null;
  prev: string | null;
  next: string | null;
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
      if (e.key === "j" && props.next) router.push(`/candidates/${props.next}`);
      else if (e.key === "k" && props.prev) router.push(`/candidates/${props.prev}`);
      else if (e.key === "s" && canDecide) open("shortlist");
      else if (e.key === "r" && canDecide) open("reject");
      else return;
      e.preventDefault();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  return (
    <section aria-label="Decision" className="mt-4 rounded border border-zinc-300 bg-white p-3 dark:border-zinc-700 dark:bg-zinc-900">
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <button
          type="button"
          disabled={!props.prev}
          onClick={() => props.prev && router.push(`/candidates/${props.prev}`)}
          className="rounded border border-zinc-400 px-3 py-1 disabled:opacity-40"
        >
          Previous <kbd>k</kbd>
        </button>
        <button
          type="button"
          disabled={!props.next}
          onClick={() => props.next && router.push(`/candidates/${props.next}`)}
          className="rounded border border-zinc-400 px-3 py-1 disabled:opacity-40"
        >
          Next <kbd>j</kbd>
        </button>
        {canDecide ? (
          <>
            <button
              type="button"
              onClick={() => open("shortlist")}
              className="rounded bg-emerald-700 px-3 py-1 font-medium text-white hover:bg-emerald-800"
            >
              Shortlist <kbd>s</kbd>
            </button>
            <button
              type="button"
              onClick={() => open("reject")}
              className="rounded bg-rose-700 px-3 py-1 font-medium text-white hover:bg-rose-800"
            >
              Reject <kbd>r</kbd>
            </button>
          </>
        ) : (
          <span>Decision made or not available: {props.state.toLowerCase().replaceAll("_", " ")}</span>
        )}
      </div>

      {choice ? (
        <div ref={box} role="dialog" aria-label={`Confirm ${choice}`} className="mt-3 space-y-2">
          <p className="text-sm">
            {choice === "shortlist" ? "Shortlist" : "Reject"} this candidate. AI recommendation:{" "}
            <strong>{props.band ? BAND_LABEL[props.band] : "none"}</strong>.
            {override ? (
              <strong className="ml-1 text-rose-800 dark:text-rose-300">
                This goes against the recommendation: say why (logged for the agreement rate).
              </strong>
            ) : null}
          </p>
          <label htmlFor="reason" className="block text-sm font-medium">
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
            className="w-full rounded border border-zinc-400 bg-white px-2 py-1 text-sm dark:border-zinc-600 dark:bg-zinc-950"
          />
          <p id="reason-help" className="text-xs text-zinc-700 dark:text-zinc-400">
            <kbd>Enter</kbd> confirms, <kbd>Shift</kbd>+<kbd>Enter</kbd> new line, <kbd>Esc</kbd> cancels.
          </p>
          {error ? (
            <p role="alert" className="text-sm text-rose-800 dark:text-rose-300">
              {error}
            </p>
          ) : null}
          <div className="flex gap-2">
            <button
              type="button"
              data-confirm
              disabled={pending}
              onClick={confirm}
              className="rounded bg-blue-700 px-3 py-1 font-medium text-white hover:bg-blue-800 disabled:opacity-60"
            >
              {pending ? "Saving" : `Confirm ${choice}`}
            </button>
            <button type="button" onClick={() => setChoice(null)} className="rounded border border-zinc-400 px-3 py-1">
              Cancel
            </button>
          </div>
        </div>
      ) : null}
    </section>
  );
}
