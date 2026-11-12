import { readFilters } from "@/lib/workbench";

import { Workbench } from "./workbench";

// Candidates across every open job (phase 5B UI design: the default view).
export default async function CandidatesPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | undefined>>;
}) {
  const s = await searchParams;
  return <Workbench filters={readFilters({ ...s, job: "all" })} mode="list" />;
}
