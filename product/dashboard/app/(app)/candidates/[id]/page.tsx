import { api, type CandidateDetail } from "@/lib/api";
import { readFilters } from "@/lib/workbench";

import { Workbench } from "../../workbench";

// One candidate open in the workbench. Without a job in the address, the list is the
// candidate's own job (as the phase 4 candidate page), so previous and next stay in it.
export default async function CandidatePage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<Record<string, string | undefined>>;
}) {
  const { id } = await params;
  const s = await searchParams;
  const c = await api.get<CandidateDetail>(`/candidates/${id}`);
  const filters = readFilters(s, c.job_id ?? "all");
  return <Workbench filters={filters} selectedId={id} mode="review" />;
}
