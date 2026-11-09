"use client";

import { useEffect } from "react";

/** j / k move focus between candidate links in the ranked table; Enter opens one. */
export function RowKeys() {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const t = e.target as HTMLElement;
      if (t.closest("input, textarea, select") || e.ctrlKey || e.metaKey || e.altKey) return;
      if (e.key !== "j" && e.key !== "k") return;
      const links = [...document.querySelectorAll<HTMLAnchorElement>("[data-row-link]")];
      if (!links.length) return;
      const at = links.indexOf(document.activeElement as HTMLAnchorElement);
      const next = e.key === "j" ? Math.min(at + 1, links.length - 1) : Math.max(at - 1, 0);
      links[at < 0 ? 0 : next].focus();
      e.preventDefault();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  return null;
}
