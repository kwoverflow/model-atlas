import { StructuredRequestLab } from "@/components/StructuredRequestLab";

export const dynamic = "force-dynamic";

export default async function StructuredRequestsPage({
  searchParams,
}: {
  searchParams: Promise<{ request_id?: string }>;
}) {
  const params = await searchParams;
  return <StructuredRequestLab initialId={params.request_id} />;
}
