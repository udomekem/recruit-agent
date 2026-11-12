import Link from "next/link";

/** The hira wordmark (phase 5B UI design Q1: the product is called hira). */
export function Brand() {
  return (
    <Link href="/" className="h-brand" aria-label="hira home">
      <span className="h-mark" aria-hidden="true">
        <b />
        <b />
        <b />
      </span>
      hira
    </Link>
  );
}
