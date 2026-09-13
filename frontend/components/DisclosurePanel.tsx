import { ChevronDown } from "lucide-react";

export function DisclosurePanel({
  title,
  children,
  open = false
}: {
  title: string;
  children: React.ReactNode;
  open?: boolean;
}) {
  return (
    <details open={open} className="group rounded-lg border border-line bg-panel shadow-soft">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-5 py-4 text-sm font-semibold text-ink">
        {title}
        <ChevronDown size={18} className="text-neutral-500 transition-transform group-open:rotate-180" aria-hidden="true" />
      </summary>
      <div className="border-t border-line p-5">{children}</div>
    </details>
  );
}
