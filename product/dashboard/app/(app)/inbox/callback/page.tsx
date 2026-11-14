import { redirect } from "next/navigation";

import { api, ApiError } from "@/lib/api";

// Google sends the recruiter back here after sign in. The code and state go to the API,
// which checks the state (one time, this recruiter, 10 minutes), the scope (read only
// Gmail, nothing else) and stores the token encrypted. Needs a dashboard session.
export default async function GmailCallback({
  searchParams,
}: {
  searchParams: Promise<{ code?: string; state?: string; error?: string }>;
}) {
  const s = await searchParams;
  if (s.error || !s.code || !s.state) {
    redirect(`/inbox?error=${encodeURIComponent("Google sign in was cancelled or refused; nothing was connected.")}`);
  }
  let problem: string | null = null;
  try {
    await api.post("/inbox/gmail/callback", { code: s.code, state: s.state });
  } catch (e) {
    if (!(e instanceof ApiError)) throw e;
    problem = e.detail;
  }
  if (problem) redirect(`/inbox?error=${encodeURIComponent(problem)}`);
  redirect(`/inbox?done=${encodeURIComponent("Gmail connected. Choose the label to read.")}`);
}
