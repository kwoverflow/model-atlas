import { Download } from "lucide-react";

import { API_BASE_URL } from "@/lib/apiBase";

type RecommendationExportActionsProps = {
  params: URLSearchParams;
};

export function RecommendationExportActions({ params }: RecommendationExportActionsProps) {
  const query = params.toString();
  const markdownHref = `${API_BASE_URL}/recommendations/report/export.md${
    query ? `?${query}` : ""
  }`;
  const pdfHref = `${API_BASE_URL}/recommendations/report/export.pdf${
    query ? `?${query}` : ""
  }`;

  return (
    <section className="rounded-lg border border-line bg-panel p-4 shadow-soft">
      <h2 className="text-base font-semibold text-ink">Export Report</h2>
      <div className="mt-3 grid gap-2">
        <a
          className="inline-flex h-10 w-full items-center justify-center gap-2 rounded-md bg-ink px-4 text-sm font-semibold text-white hover:bg-neutral-700"
          download
          href={markdownHref}
        >
          <Download size={16} />
          Markdown
        </a>
        <a
          className="inline-flex h-10 w-full items-center justify-center gap-2 rounded-md border border-line bg-white px-4 text-sm font-semibold text-ink hover:border-teal"
          download
          href={pdfHref}
        >
          <Download size={16} />
          PDF
        </a>
      </div>
    </section>
  );
}
