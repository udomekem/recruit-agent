import "server-only";

import { createHash, createHmac, timingSafeEqual } from "node:crypto";
import { cookies, headers } from "next/headers";
import { redirect } from "next/navigation";

// Phase 4 design section 2: one recruiter account. The password and the signing key are
// server only settings; the browser gets a signed, httpOnly session cookie and nothing else.

const COOKIE = "ra_session";
const LIFETIME_S = 8 * 60 * 60;
const MAX_FAILS = 5;
const LOCK_MS = 15 * 60 * 1000;

function secret(): string {
  const s = process.env.SESSION_SECRET ?? "";
  if (s.length < 32) throw new Error("SESSION_SECRET is not set (run make local-env)");
  return s;
}

function sign(payload: string): string {
  return createHmac("sha256", secret()).update(payload).digest("base64url");
}

function same(a: string, b: string): boolean {
  const da = createHash("sha256").update(a).digest();
  const db = createHash("sha256").update(b).digest();
  return timingSafeEqual(da, db);
}

export async function hasSession(): Promise<boolean> {
  const raw = (await cookies()).get(COOKIE)?.value ?? "";
  const [payload, mac] = raw.split(".");
  if (!payload || !mac || !same(sign(payload), mac)) return false;
  try {
    const { exp } = JSON.parse(Buffer.from(payload, "base64url").toString()) as { exp: number };
    return typeof exp === "number" && exp > Date.now() / 1000;
  } catch {
    return false;
  }
}

/** Call at the top of every page and server action except sign in. */
export async function requireSession(): Promise<void> {
  if (!(await hasSession())) redirect("/login");
}

// Brute force guard (design: 5 failures per 15 minutes). In memory: one process locally.
// Phase 10 (Vercel, many instances) needs a shared store.
const fails = new Map<string, { n: number; until: number }>();

async function clientKey(): Promise<string> {
  const h = await headers();
  return (h.get("x-forwarded-for") ?? "").split(",")[0].trim() || "local";
}

export type SignInResult = { ok: true } | { ok: false; error: string };

export async function signIn(password: string): Promise<SignInResult> {
  const key = await clientKey();
  const now = Date.now();
  const f = fails.get(key);
  if (f && f.n >= MAX_FAILS && f.until > now) {
    return { ok: false, error: "Too many attempts. Try again in 15 minutes." };
  }
  const expected = process.env.DASHBOARD_PASSWORD ?? "";
  if (!expected || !same(password, expected)) {
    const n = f && f.until > now ? f.n + 1 : 1;
    fails.set(key, { n, until: now + LOCK_MS });
    return { ok: false, error: "That password is not right." };
  }
  fails.delete(key);
  const payload = Buffer.from(JSON.stringify({ exp: Math.floor(now / 1000) + LIFETIME_S })).toString(
    "base64url",
  );
  (await cookies()).set(COOKIE, `${payload}.${sign(payload)}`, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.COOKIE_SECURE === "1",
    path: "/",
    maxAge: LIFETIME_S,
  });
  return { ok: true };
}

export async function signOut(): Promise<void> {
  (await cookies()).delete(COOKIE);
}
