import Link from "next/link";

import { api, ApiError, type InboxMessageOut, type InboxPage, type MailboxOut } from "@/lib/api";
import { when } from "@/lib/format";

import {
  connectMailpit,
  disconnectMailbox,
  pickJob,
  pollNow,
  setLabel,
  setMailboxStatus,
  startGmail,
} from "../actions";

// Inbox (phase 5B UI design): connect a mailbox, pick the one label that is read, and see
// what arrived. Subjects are shown redacted; names stay hidden until shortlist.

const STATUS_LABEL: Record<string, string> = {
  received: "Waiting",
  working: "Reading",
  not_a_cv: "Not a CV",
  ingested: "Added",
  duplicate: "Duplicate",
  failed: "Could not read",
};
const STATUS_TONE: Record<string, string> = {
  ingested: "good",
  duplicate: "maybe",
  not_a_cv: "",
  failed: "bad",
  received: "todo",
  working: "todo",
};
const SENDER: Record<string, string> = { seek: "Seek", indeed: "Indeed", direct: "Direct email", other: "Email" };
const MAILBOX_STATUS: Record<string, string> = {
  active: "Reading every 2 minutes",
  paused: "Paused",
  needs_label: "Choose a label to start",
  needs_reconnect: "Access ended: reconnect",
};

async function labelsFor(m: MailboxOut): Promise<string[] | null> {
  if (m.status !== "needs_label" && m.status !== "active" && m.status !== "paused") return null;
  try {
    return (await api.get<{ labels: string[] }>(`/inbox/mailboxes/${m.id}/labels`)).labels;
  } catch (e) {
    if (e instanceof ApiError) return null;
    throw e;
  }
}

export default async function Inbox({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; done?: string }>;
}) {
  const s = await searchParams;
  const page = await api.get<InboxPage>("/inbox");
  const labels = await Promise.all(page.mailboxes.map(labelsFor));
  const matched = page.messages.filter((m) => m.status === "ingested").length;
  const needJob = page.messages.flatMap((m) => m.attachments).filter((a) => a.needs_job).length;

  return (
    <>
      <div className="h-hero">
        <div>
          <div className="h-eyebrow">Connected inbox</div>
          <h1 className="h-h1">CVs, straight from your email.</h1>
          <p className="h-intro">
            Connect the inbox where applications arrive. New CVs are read, matched to an open job and scored. Read
            only: nothing is ever sent from, moved in or deleted from your mailbox.
          </p>
        </div>
        <div className="h-stats" aria-label="Inbox counts">
          <div className="h-stat">
            <strong>{String(page.messages.length).padStart(2, "0")}</strong>
            <small>Emails</small>
          </div>
          <div className="h-stat">
            <strong>{String(matched).padStart(2, "0")}</strong>
            <small>CVs added</small>
          </div>
          <div className="h-stat">
            <strong>{String(needJob).padStart(2, "0")}</strong>
            <small>Need a job</small>
          </div>
        </div>
      </div>
      {s.error ? (
        <p role="alert" className="h-banner bad">
          {s.error}
        </p>
      ) : null}
      {s.done ? (
        <p role="status" className="h-banner ok">
          {s.done}
        </p>
      ) : null}

      {page.mailboxes.length === 0 ? <Connect canGmail={page.can_connect.gmail} canMailpit={page.can_connect.mailpit} /> : null}

      {page.mailboxes.map((m, i) => (
        <section key={m.id} className="h-card" aria-label={`Mailbox ${m.address}`}>
          <div className="h-chead">
            <div>
              <h2>{m.address}</h2>
              <small>
                {m.provider === "gmail" ? "Gmail" : m.provider === "mailpit" ? "Test inbox (Mailpit)" : m.provider} · read
                only{m.label ? ` · label “${m.label}”` : ""}
              </small>
            </div>
            <span className={`h-pill${m.status === "active" ? " ok" : m.status === "needs_reconnect" ? " warn" : ""}`}>
              {MAILBOX_STATUS[m.status] ?? m.status}
              {m.status === "active" && m.last_polled_at ? ` · last ${when(m.last_polled_at)}` : ""}
            </span>
          </div>
          <ul className="h-list">
            {m.status === "needs_reconnect" ? (
              <li>
                <span className="h-t2">{m.last_error ?? "The access was revoked or expired."}</span>
                <form action={startGmail}>
                  <button className="h-btn primary">Reconnect Gmail</button>
                </form>
              </li>
            ) : null}
            {labels[i] ? (
              <li>
                <form action={setLabel} className="h-inline-form">
                  <input type="hidden" name="mailbox_id" value={m.id} />
                  <label htmlFor={`label-${m.id}`} className="h-t1">
                    Read emails with this label
                  </label>
                  <select id={`label-${m.id}`} name="label" defaultValue={m.label ?? ""} className="h-select" required>
                    <option value="" disabled>
                      Choose a label
                    </option>
                    {labels[i]!.map((l) => (
                      <option key={l} value={l}>
                        {l}
                      </option>
                    ))}
                  </select>
                  <button className="h-btn small">Save</button>
                </form>
                <span className="h-t2">Only this label is read, never the rest of the mailbox.</span>
              </li>
            ) : null}
            {m.status !== "needs_label" && m.status !== "needs_reconnect" ? (
              <li>
                <span className="h-t2">{m.last_error ? `Last problem: ${m.last_error}` : "Working normally."}</span>
                <span className="h-inline-form">
                  {m.status === "active" ? (
                    <form action={pollNow}>
                      <input type="hidden" name="mailbox_id" value={m.id} />
                      <button className="h-btn small">Check now</button>
                    </form>
                  ) : null}
                  <form action={setMailboxStatus}>
                    <input type="hidden" name="mailbox_id" value={m.id} />
                    <input type="hidden" name="status" value={m.status === "paused" ? "active" : "paused"} />
                    <button className="h-btn small">{m.status === "paused" ? "Resume" : "Pause"}</button>
                  </form>
                  <form action={disconnectMailbox}>
                    <input type="hidden" name="mailbox_id" value={m.id} />
                    <button className="h-btn small danger">Disconnect</button>
                  </form>
                </span>
              </li>
            ) : null}
          </ul>
        </section>
      ))}

      {page.mailboxes.length ? <Messages messages={page.messages} jobs={page.open_jobs} /> : null}

      <div className="h-footer">
        <span>🔒 Read only access to one label. Disconnecting deletes the access token.</span>
        <span>Jobs are matched by code, job address, Seek or Indeed subject, then the AI; when unsure, you choose.</span>
      </div>
    </>
  );
}

function Connect({ canGmail, canMailpit }: { canGmail: boolean; canMailpit: boolean }) {
  return (
    <section className="h-card" aria-labelledby="connect-h">
      <div className="h-chead">
        <h2 id="connect-h">Connect your inbox</h2>
        <small>Seek and Indeed can email applications to any address</small>
      </div>
      <ul className="h-list">
        <li>
          <span>
            <span className="h-t1">Gmail</span>
            <span className="h-t2"> · Google Workspace or a Gmail address</span>
          </span>
          {canGmail ? (
            <form action={startGmail}>
              <button className="h-btn primary">Sign in with Google</button>
            </form>
          ) : (
            <span className="h-pill">Needs the Google OAuth client in .env</span>
          )}
        </li>
        <li>
          <span>
            <span className="h-t1">Microsoft 365</span>
            <span className="h-t2"> · Outlook, Exchange Online</span>
          </span>
          <span className="h-pill">Coming soon</span>
        </li>
        {canMailpit ? (
          <li>
            <span>
              <span className="h-t1">Test inbox (Mailpit)</span>
              <span className="h-t2"> · local only; emails tagged “Applications” are read</span>
            </span>
            <form action={connectMailpit}>
              <input type="hidden" name="label" value="Applications" />
              <button className="h-btn">Connect the test inbox</button>
            </form>
          </li>
        ) : null}
      </ul>
    </section>
  );
}

function Messages({ messages, jobs }: { messages: InboxMessageOut[]; jobs: InboxPage["open_jobs"] }) {
  const ordered = [...messages].sort(
    (a, b) => Number(b.attachments.some((x) => x.needs_job)) - Number(a.attachments.some((x) => x.needs_job)),
  );
  return (
    <section className="h-card" aria-labelledby="mail-h">
      <div className="h-chead">
        <h2 id="mail-h">Recent emails</h2>
        <small>Subjects with names and contact details removed</small>
      </div>
      {ordered.length === 0 ? (
        <p className="h-empty">Nothing yet. New emails under the label appear within 2 minutes.</p>
      ) : (
        <table className="h-table">
          <caption className="sr-only">Emails read from the connected inbox</caption>
          <thead>
            <tr>
              <th scope="col">Email</th>
              <th scope="col">Job</th>
              <th scope="col" className="hide-md hide-sm">
                How it was matched
              </th>
              <th scope="col">Status</th>
            </tr>
          </thead>
          <tbody>
            {ordered.map((m) => (
              <tr key={m.id}>
                <td>
                  <div className="h-t1">{m.subject || "(no subject)"}</div>
                  <div className="h-t2">
                    {SENDER[m.sender_kind]} · {when(m.received_at)}
                  </div>
                </td>
                <td>
                  {m.attachments.length === 0 ? (
                    <span className="h-t2">None</span>
                  ) : (
                    m.attachments.map((a, i) =>
                      a.needs_job && a.candidate_id ? (
                        <form key={i} action={pickJob} className="h-inline-form">
                          <input type="hidden" name="candidate_id" value={a.candidate_id} />
                          <input type="hidden" name="expected_version" value={a.state_version ?? 0} />
                          <label htmlFor={`job-${a.candidate_id}`} className="sr-only">
                            Choose a job for {a.label}
                          </label>
                          <select id={`job-${a.candidate_id}`} name="job_id" className="h-select" required defaultValue="">
                            <option value="" disabled>
                              Choose a job…
                            </option>
                            {[...jobs]
                              .sort((x, y) => Number(a.suggested.includes(y.id)) - Number(a.suggested.includes(x.id)))
                              .map((j) => (
                                <option key={j.id} value={j.id}>
                                  {a.suggested.includes(j.id) ? "Suggested: " : ""}
                                  {j.title}
                                </option>
                              ))}
                          </select>
                          <button className="h-btn small primary">Set job</button>
                        </form>
                      ) : (
                        <div key={i}>
                          {a.candidate_id ? (
                            <Link href={`/candidates/${a.candidate_id}`} className="h-t1">
                              {a.label}
                            </Link>
                          ) : null}
                          <div className="h-t2">{a.job_title ?? (a.outcome === "skipped" ? a.note : "Matching…")}</div>
                        </div>
                      ),
                    )
                  )}
                </td>
                <td className="hide-md hide-sm">
                  <span className="h-t2">
                    {m.attachments.find((a) => a.match)?.match ?? m.detail}
                  </span>
                </td>
                <td>
                  <span className="h-dot" data-tone={m.attachments.some((a) => a.needs_job) ? "maybe" : STATUS_TONE[m.status]}>
                    {m.attachments.some((a) => a.needs_job) ? "Needs a job" : (STATUS_LABEL[m.status] ?? m.status)}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
