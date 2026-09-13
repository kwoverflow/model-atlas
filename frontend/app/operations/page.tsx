import { Badge } from "@/components/Badge";
import { OperationalReliabilityConsole } from "@/components/OperationalReliabilityConsole";

export default function OperationsPage() {
  return (
    <>
      <section className="border-b border-line pb-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold text-ink">Operations</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-neutral-600">
              Durable control-plane history, explicit identity and worker SLOs, incident
              transitions, and owned paging delivery evidence.
            </p>
          </div>
          <Badge tone="violet">Sprint 5H-H</Badge>
        </div>
      </section>
      <OperationalReliabilityConsole />
    </>
  );
}
