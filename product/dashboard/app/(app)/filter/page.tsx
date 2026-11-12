import { redirect } from "next/navigation";

import { qs, readFilters } from "@/lib/workbench";

// The filter form submits here; the job picks the path (one job or every job).
export default async function FilterRedirect({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | undefined>>;
}) {
  const f = readFilters(await searchParams);
  const job = /^[0-9a-f-]{36}$/.test(f.job) ? f.job : "all";
  redirect(job === "all" ? `/${qs(f)}` : `/jobs/${job}${qs({ ...f, job }, job)}`);
}
