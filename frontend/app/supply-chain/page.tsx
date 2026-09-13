import { Badge } from "@/components/Badge";
import { SupplyChainConsole } from "@/components/SupplyChainConsole";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function SupplyChainPage() {
  const [overview, runtimeAttestations, attestations, receipts] = await Promise.all([
    api.supplyChainOverview(),
    api.modelArtifactAttestations(),
    api.modelSupplyChainAttestations(),
    api.productionEvidenceReceipts()
  ]);

  return (
    <>
      <section className="border-b border-line pb-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold text-ink">Supply Chain</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-neutral-600">
              Publisher signatures, CycloneDX SBOMs, revocations, and production capture receipts.
            </p>
          </div>
          <Badge
            tone={overview.production_eligible_attestation_count ? "teal" : "amber"}
          >
            {overview.production_eligible_attestation_count
              ? "production trust verified"
              : "production trust pending"}
          </Badge>
        </div>
      </section>

      <SupplyChainConsole
        overview={overview}
        runtimeAttestations={runtimeAttestations}
        initialAttestations={attestations}
        initialReceipts={receipts}
      />
    </>
  );
}
