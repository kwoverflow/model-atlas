"use client";

import { Save } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { API_BASE_URL } from "@/lib/apiBase";
import { browserApiFetch } from "@/lib/browserApi";
import type { RecommendationRequest, RecommendationScenarioRead } from "@/types/api";

type SaveScenarioFormProps = {
  request: RecommendationRequest;
};

export function SaveScenarioForm({ request }: SaveScenarioFormProps) {
  const router = useRouter();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedName = name.trim();
    if (!trimmedName) {
      setStatus("Name is required.");
      return;
    }

    setIsSaving(true);
    setStatus(null);
    try {
      const response = await browserApiFetch(`${API_BASE_URL}/recommendations/scenarios`, {
        body: JSON.stringify({
          name: trimmedName,
          description: description.trim() || null,
          request
        }),
        headers: { "Content-Type": "application/json" },
        method: "POST"
      });

      if (!response.ok) {
        setStatus("Save failed.");
        return;
      }

      const scenario = (await response.json()) as RecommendationScenarioRead;
      setName("");
      setDescription("");
      setStatus(`Saved: ${scenario.name}`);
      router.refresh();
    } catch {
      setStatus("Save failed.");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <section className="rounded-lg border border-line bg-panel p-4 shadow-soft">
      <h2 className="text-base font-semibold text-ink">Save Scenario</h2>
      <form className="mt-3 grid gap-3" onSubmit={handleSubmit}>
        <label className="grid gap-1.5 text-sm font-medium text-ink">
          Scenario name
          <input
            className="h-10 rounded-md border border-line bg-white px-3 text-sm outline-none focus:border-teal"
            maxLength={180}
            onChange={(event) => setName(event.target.value)}
            type="text"
            value={name}
          />
        </label>
        <label className="grid gap-1.5 text-sm font-medium text-ink">
          Notes
          <textarea
            className="min-h-20 rounded-md border border-line bg-white px-3 py-2 text-sm outline-none focus:border-teal"
            onChange={(event) => setDescription(event.target.value)}
            value={description}
          />
        </label>
        <div className="flex items-center justify-between gap-3">
          <p className="text-xs text-neutral-500">{status}</p>
          <button
            className="inline-flex h-10 items-center gap-2 rounded-md bg-teal px-4 text-sm font-semibold text-white hover:bg-neutral-700 disabled:cursor-not-allowed disabled:opacity-60"
            disabled={isSaving}
            type="submit"
          >
            <Save size={16} />
            {isSaving ? "Saving" : "Save"}
          </button>
        </div>
      </form>
    </section>
  );
}
