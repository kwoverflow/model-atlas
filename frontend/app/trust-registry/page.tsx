import { Badge } from "@/components/Badge";
import { TrustRegistryConsole } from "@/components/TrustRegistryConsole";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function TrustRegistryPage() {
  const [overview, sources, schedules, syncs, roots, attestations, proofs] = await Promise.all([
    api.trustRegistryOverview(),
    api.evidenceTrustSources(),
    api.evidenceTrustSourceSchedules(),
    api.evidenceTrustSourceSyncs(),
    api.evidenceTrustRoots(),
    api.modelSupplyChainAttestations(),
    api.transparencyProofs()
  ]);

  return (
    <>
      <section className="border-b border-line pb-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold text-ink">Trust Registry</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-neutral-600">
              Federated JWKS sources, managed signing keys, lifecycle events, and verifiable
              transparency inclusion.
            </p>
          </div>
          <Badge tone="teal">Sprint 5H-D</Badge>
        </div>
      </section>

      <TrustRegistryConsole
        overview={overview}
        sources={sources}
        schedules={schedules}
        syncs={syncs}
        roots={roots}
        attestations={attestations}
        proofs={proofs}
      />
    </>
  );
}
