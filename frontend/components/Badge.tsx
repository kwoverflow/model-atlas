type BadgeProps = {
  children: React.ReactNode;
  tone?: "neutral" | "teal" | "amber" | "rose" | "violet";
};

const toneClasses = {
  neutral: "border-neutral-300 bg-neutral-50 text-neutral-700",
  teal: "border-teal/30 bg-teal/5 text-teal",
  amber: "border-amber/30 bg-amber/5 text-amber",
  rose: "border-rose/30 bg-rose/5 text-rose",
  violet: "border-violet/30 bg-violet/5 text-violet"
};

export function Badge({ children, tone = "neutral" }: BadgeProps) {
  return (
    <span className={`inline-flex rounded-md border px-2 py-1 text-xs font-medium ${toneClasses[tone]}`}>
      {children}
    </span>
  );
}
