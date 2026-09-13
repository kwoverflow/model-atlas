import { Badge } from "@/components/Badge";
import { SessionAdministrationConsole } from "@/components/SessionAdministrationConsole";

export default function SessionAdministrationPage() {
  return (
    <>
      <section className="border-b border-line pb-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold text-ink">Browser Sessions</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-neutral-600">
              Govern shared OIDC sessions, retention state, revocation scope, and lifecycle audit
              evidence.
            </p>
          </div>
          <Badge tone="violet">Sprint 5H-E</Badge>
        </div>
      </section>

      <SessionAdministrationConsole />
    </>
  );
}
