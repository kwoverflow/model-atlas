import { AlertCircle, CheckCircle2, Circle } from "lucide-react";
import Link from "next/link";

import type { ControlPlaneOverview } from "@/types/api";

const stepIcon = {
  complete: CheckCircle2,
  attention: AlertCircle,
  not_started: Circle
};

export function WorkflowStepper({ steps }: { steps: ControlPlaneOverview["workflow_steps"] }) {
  return (
    <section className="rounded-lg border border-line bg-panel shadow-soft">
      <div className="border-b border-line px-5 py-4">
        <h2 className="text-base font-semibold text-ink">Release workflow</h2>
      </div>
      <ol className="grid divide-y divide-line lg:grid-cols-6 lg:divide-x lg:divide-y-0">
        {steps.map((step, index) => {
          const Icon = stepIcon[step.status];
          return (
            <li key={step.key}>
              <Link
                href={step.href}
                className="flex min-h-24 items-start gap-3 px-4 py-4 hover:bg-neutral-50"
              >
                <Icon
                  size={18}
                  className={
                    step.status === "complete"
                      ? "text-teal"
                      : step.status === "attention"
                        ? "text-amber"
                        : "text-neutral-400"
                  }
                  aria-hidden="true"
                />
                <span>
                  <span className="block text-xs font-medium text-neutral-500">Step {index + 1}</span>
                  <span className="mt-1 block text-sm font-semibold leading-5 text-ink">
                    {step.label}
                  </span>
                </span>
              </Link>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
