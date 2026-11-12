import { readFilters } from "@/lib/workbench";

import { Workbench } from "../../workbench";

// One job's candidates in the workbench, ranked by the API (phase 4 ranking).
export default async function JobPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<Record<string, string | undefined>>;
}) {
  const { id } = await params;
  const s = await searchParams;
  return (
    <Workbench
      filters={readFilters({ ...s, job: id })}
      mode="list"
      notice={{ done: s.done, rescoring: s.rescoring }}
    />
  );
}
