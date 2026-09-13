import { RequestWorkflowStudy } from "@/components/RequestWorkflowStudy";

export const dynamic = "force-dynamic";

export default async function RequestWorkflowPage({
  searchParams,
}: {
  searchParams: Promise<{ attempt_id?: string }>;
}) {
  const params = await searchParams;
  return (
    <RequestWorkflowStudy
      key={params.attempt_id ?? "catalog"}
      initialId={params.attempt_id}
    />
  );
}
