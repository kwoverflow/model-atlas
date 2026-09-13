type SummaryCardProps = {
  label: string;
  value: string | number;
  detail?: string;
  tone?: "neutral" | "teal" | "amber" | "rose" | "violet";
};

const toneClasses = {
  neutral: "border-neutral-300 bg-neutral-100 text-neutral-600",
  teal: "border-teal/30 bg-teal/5 text-teal",
  amber: "border-amber/30 bg-amber/5 text-amber",
  rose: "border-rose/30 bg-rose/5 text-rose",
  violet: "border-violet/30 bg-violet/5 text-violet"
};

export function SummaryCard({ label, value, detail, tone = "teal" }: SummaryCardProps) {
  return (
    <article className="min-h-28 min-w-0 rounded-lg border border-line bg-panel p-4 shadow-soft">
      <div className={`mb-3 h-1.5 w-12 rounded-full border ${toneClasses[tone]}`} />
      <div className="break-words text-xs font-medium uppercase text-neutral-500">{label}</div>
      <div className="mt-2 break-words text-xl font-semibold text-ink">{value}</div>
      {detail ? <div className="mt-2 break-words text-sm text-neutral-600">{detail}</div> : null}
    </article>
  );
}
