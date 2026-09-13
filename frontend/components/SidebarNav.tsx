"use client";

import {
  BarChart3,
  BellRing,
  Activity,
  BookOpenCheck,
  ChevronDown,
  ClipboardCheck,
  ClipboardList,
  Cpu,
  Database,
  FileCheck2,
  FlaskConical,
  GitBranch,
  GitCompare,
  Gauge,
  History,
  LockKeyhole,
  KeyRound,
  PackageCheck,
  PlayCircle,
  Rocket,
  ShieldCheck,
  Trophy,
  UserCog,
  type LucideIcon
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { OperatorIdentityStatus } from "@/components/OperatorIdentityStatus";

export type NavigationItem = {
  href: string;
  activePrefix?: string;
  label: string;
  icon: LucideIcon;
};

export type NavigationGroup = {
  label: string;
  items: NavigationItem[];
  collapsible?: boolean;
};

export const overviewItem: NavigationItem = {
  href: "/",
  label: "Overview",
  icon: Database
};

export const navigationGroups: NavigationGroup[] = [
  {
    label: "Core Evaluation",
    items: [
      { href: "/reference-workload", label: "Reference Workload", icon: BookOpenCheck },
      { href: "/workloads", label: "Workloads", icon: ClipboardList },
      { href: "/deployments", label: "Deployment Configurations", icon: Rocket },
      { href: "/model-validation", label: "Model Validation", icon: FlaskConical },
      {
        href: "/deployment-gates/new",
        activePrefix: "/deployment-gates",
        label: "Deployment Gates",
        icon: ShieldCheck
      },
      { href: "/release-readiness", label: "Release Readiness", icon: FileCheck2 },
      { href: "/release-decisions", label: "Release Decisions", icon: FileCheck2 }
    ]
  },
  {
    label: "Discovery",
    items: [
      { href: "/models", label: "Models", icon: Cpu },
      { href: "/benchmarks", label: "Benchmarks", icon: BarChart3 },
      { href: "/recommendations", label: "Candidate Discovery", icon: Trophy }
    ]
  },
  {
    label: "Advanced Lab",
    collapsible: true,
    items: [
      { href: "/benchmark-executions/new", label: "Execute Benchmark", icon: PlayCircle },
      { href: "/runtime-reliability", label: "Runtime Reliability", icon: Gauge },
      { href: "/structured-requests", label: "Request Contracts", icon: ClipboardCheck },
      { href: "/judge-labels", label: "Judge Review", icon: ClipboardCheck },
      { href: "/prompt-regressions", label: "Prompt Regression", icon: GitCompare },
      { href: "/deployment-baselines", label: "Baselines", icon: History },
      { href: "/supply-chain", label: "Supply Chain", icon: PackageCheck },
      { href: "/trust-registry", label: "Trust Registry", icon: KeyRound },
      { href: "/isolation", label: "Isolation Policies", icon: LockKeyhole },
      { href: "/operations", label: "Operations", icon: BellRing },
      { href: "/session-administration", label: "Browser Sessions", icon: UserCog },
      { href: "/agent-jobs", label: "Agent Jobs", icon: Activity },
      { href: "/experiment-lineage", label: "Experiment Lineage", icon: GitBranch }
    ]
  }
];

export function isActivePath(pathname: string, item: NavigationItem): boolean {
  if (item.href === "/") return pathname === "/";
  return pathname.startsWith(item.activePrefix ?? item.href);
}

export function Brand() {
  return (
    <Link href="/" className="flex min-w-0 items-center gap-3 rounded-md focus-visible:outline-none">
      <span className="grid h-9 w-9 shrink-0 place-items-center rounded-md bg-ink text-white">
        <Database size={18} aria-hidden="true" />
      </span>
      <span className="min-w-0">
        <span className="block text-sm font-semibold text-ink">Model Atlas</span>
        <span className="block truncate text-xs text-neutral-500">Local EvalOps control plane</span>
      </span>
    </Link>
  );
}

export function NavigationLinks({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const advancedGroup = navigationGroups.find((group) => group.collapsible);
  const advancedActive = Boolean(
    advancedGroup?.items.some((item) => isActivePath(pathname, item))
  );
  const [advancedOpen, setAdvancedOpen] = useState(advancedActive);

  return (
    <nav aria-label="Primary navigation" className="grid gap-5">
      <NavigationLink item={overviewItem} pathname={pathname} onNavigate={onNavigate} />
      {navigationGroups.map((group) => {
        const open = !group.collapsible || advancedOpen || advancedActive;
        return (
          <div key={group.label}>
            {group.collapsible ? (
              <button
                type="button"
                onClick={() => setAdvancedOpen((current) => !current)}
                aria-expanded={open}
                className="mb-2 flex min-h-9 w-full items-center justify-between rounded-md px-3 text-xs font-semibold uppercase text-neutral-500 hover:bg-neutral-100"
              >
                <span>{group.label}</span>
                <ChevronDown
                  size={15}
                  className={`transition-transform ${open ? "rotate-180" : ""}`}
                  aria-hidden="true"
                />
              </button>
            ) : (
              <div className="mb-2 px-3 text-xs font-semibold uppercase text-neutral-400">
                {group.label}
              </div>
            )}
            {open ? (
              <div className="grid gap-1">
                {group.items.map((item) => (
                  <NavigationLink
                    key={item.href}
                    item={item}
                    pathname={pathname}
                    onNavigate={onNavigate}
                  />
                ))}
              </div>
            ) : null}
          </div>
        );
      })}
    </nav>
  );
}

function NavigationLink({
  item,
  pathname,
  onNavigate
}: {
  item: NavigationItem;
  pathname: string;
  onNavigate?: () => void;
}) {
  const active = isActivePath(pathname, item);
  const Icon = item.icon;
  return (
    <Link
      href={item.href}
      onClick={onNavigate}
      aria-current={active ? "page" : undefined}
      className={`flex min-h-10 items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
        active
          ? "bg-neutral-900 text-white"
          : "text-neutral-700 hover:bg-neutral-100 hover:text-ink"
      }`}
    >
      <Icon size={17} aria-hidden="true" />
      <span>{item.label}</span>
    </Link>
  );
}

export function SidebarNav() {
  return (
    <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 border-r border-line bg-panel lg:flex lg:flex-col">
      <div className="border-b border-line px-5 py-4">
        <Brand />
      </div>
      <div className="flex-1 overflow-y-auto px-3 py-5">
        <NavigationLinks />
      </div>
      <div className="border-t border-line px-5 py-4">
        <OperatorIdentityStatus />
        <p className="mt-3 text-xs leading-5 text-neutral-500">
          Evidence and policy stay separate from release authorization.
        </p>
      </div>
    </aside>
  );
}
