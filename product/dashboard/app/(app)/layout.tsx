import Link from "next/link";

import { requireSession } from "@/lib/session";

import { logout } from "./actions";

export const dynamic = "force-dynamic";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  await requireSession();
  return (
    <>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:rounded focus:bg-white focus:px-3 focus:py-2"
      >
        Skip to content
      </a>
      <header className="border-b border-zinc-300 bg-white dark:border-zinc-700 dark:bg-zinc-900">
        <nav
          aria-label="Main"
          className="mx-auto flex max-w-7xl items-center gap-6 px-4 py-3 text-sm"
        >
          <Link href="/" className="text-base font-semibold">
            Northwind Talent
          </Link>
          <Link href="/" className="hover:underline">
            Jobs
          </Link>
          <Link href="/review" className="hover:underline">
            Review queue
          </Link>
          <form action={logout} className="ml-auto">
            <button type="submit" className="hover:underline">
              Sign out
            </button>
          </form>
        </nav>
      </header>
      <main id="main" className="mx-auto max-w-7xl px-4 py-6">
        {children}
      </main>
    </>
  );
}
