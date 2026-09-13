"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";

type ChartDatum = {
  label: string;
  quality: number | null;
  ttft: number | null;
  latency: number | null;
  tps: number | null;
  vram: number | null;
  jsonRate: number | null;
  toolRate: number | null;
};

type MetricChartsProps = {
  data: ChartDatum[];
};

const charts = [
  { title: "Quality Score", key: "quality", color: "#0f766e", suffix: "" },
  { title: "TTFT", key: "ttft", color: "#6d28d9", suffix: " ms" },
  { title: "End-to-end Latency", key: "latency", color: "#2563eb", suffix: " ms" },
  { title: "Tokens/sec", key: "tps", color: "#b45309", suffix: "" },
  { title: "VRAM Usage", key: "vram", color: "#be123c", suffix: " MB" },
  { title: "JSON Validity", key: "jsonRate", color: "#15803d", suffix: "%" },
  { title: "Tool-call Validity", key: "toolRate", color: "#7c2d12", suffix: "%" }
] as const;

export function MetricCharts({ data }: MetricChartsProps) {
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {charts.map((chart) => (
        <section key={chart.key} className="rounded-lg border border-line bg-panel p-4 shadow-soft">
          <h3 className="text-sm font-semibold text-ink">{chart.title}</h3>
          <div className="mt-3 h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data} margin={{ top: 8, right: 8, bottom: 52, left: 8 }}>
                <CartesianGrid stroke="#e5e7eb" vertical={false} />
                <XAxis
                  dataKey="label"
                  tick={{ fontSize: 11, fill: "#525252" }}
                  angle={-35}
                  textAnchor="end"
                  interval={0}
                  height={70}
                />
                <YAxis tick={{ fontSize: 11, fill: "#525252" }} />
                <Tooltip
                  formatter={(value) => [`${Number(value).toFixed(2)}${chart.suffix}`, chart.title]}
                  labelStyle={{ color: "#202124" }}
                />
                <Bar dataKey={chart.key} fill={chart.color} radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>
      ))}
    </div>
  );
}
