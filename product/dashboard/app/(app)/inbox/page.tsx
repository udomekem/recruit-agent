// Inbox (phase 5B UI design). The connection itself is built in the second half of
// phase 5B (brief Q1: redesign first); until then this page says what is coming.
export default function InboxPage() {
  return (
    <>
      <div className="h-hero">
        <div>
          <div className="h-eyebrow">Connected inbox</div>
          <h1 className="h-h1">CVs, straight from your email.</h1>
          <p className="h-intro">
            Connect the inbox where applications arrive. New CVs will be read, matched to an open job and scored.
            Read only: nothing is ever sent from your mailbox.
          </p>
        </div>
      </div>
      <section className="h-card" aria-labelledby="connect-h">
        <div className="h-chead">
          <h2 id="connect-h">Connect your inbox</h2>
          <span className="h-pill">Coming next in phase 5B</span>
        </div>
        <ul className="h-list">
          <li>
            <span>
              <span className="h-t1">Gmail</span>
              <span className="h-t2"> · Google Workspace or a Gmail address</span>
            </span>
            <button type="button" className="h-btn" disabled>
              Connect
            </button>
          </li>
          <li>
            <span>
              <span className="h-t1">Microsoft 365</span>
              <span className="h-t2"> · Outlook, Exchange Online</span>
            </span>
            <span className="h-pill">Coming soon</span>
          </li>
        </ul>
      </section>
      <section className="h-card" aria-labelledby="how-h">
        <div className="h-chead">
          <h2 id="how-h">How it will work</h2>
        </div>
        <ul className="h-list">
          <li>
            <span className="h-t2">
              Only emails with the label you pick (for example &ldquo;Applications&rdquo;) are read.
            </span>
          </li>
          <li>
            <span className="h-t2">
              Jobs are matched by a job code or job email address, then the Seek or Indeed subject, then the AI.
              When it is unsure, you choose.
            </span>
          </li>
          <li>
            <span className="h-t2">
              CVs get the same redaction and scoring as the apply page, and each sender gets our privacy notice.
            </span>
          </li>
        </ul>
      </section>
    </>
  );
}
