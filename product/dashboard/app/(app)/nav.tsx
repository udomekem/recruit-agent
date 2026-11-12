"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

// Header navigation (phase 5B UI design): tabs in the header, no sidebar.
const ITEMS = [
  { href: "/", label: "Candidates", match: (p: string) => p === "/" || p.startsWith("/candidates") },
  { href: "/jobs", label: "Jobs", match: (p: string) => p.startsWith("/jobs") },
  { href: "/inbox", label: "Inbox", match: (p: string) => p.startsWith("/inbox") },
  { href: "/review", label: "To do", match: (p: string) => p.startsWith("/review") },
];

export function Nav() {
  const path = usePathname() ?? "/";
  return (
    <nav aria-label="Main" className="h-nav">
      {ITEMS.map((i) => (
        <Link key={i.href} href={i.href} aria-current={i.match(path) ? "page" : undefined}>
          {i.label}
        </Link>
      ))}
    </nav>
  );
}
