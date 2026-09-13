"use client";

import { Check, ExternalLink, Pencil, Trash2, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Badge } from "@/components/Badge";
import { API_BASE_URL } from "@/lib/apiBase";
import { browserApiFetch } from "@/lib/browserApi";
import { recommendationRequestHref } from "@/lib/recommendationParams";
import type { RecommendationScenarioRead } from "@/types/api";

type RecommendationScenarioListProps = {
  scenarios: RecommendationScenarioRead[];
};

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(new Date(value));
}

export function RecommendationScenarioList({
  scenarios
}: RecommendationScenarioListProps) {
  const router = useRouter();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draftName, setDraftName] = useState("");
  const [draftDescription, setDraftDescription] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  function startEditing(scenario: RecommendationScenarioRead) {
    setEditingId(scenario.id);
    setDraftName(scenario.name);
    setDraftDescription(scenario.description ?? "");
    setStatus(null);
  }

  function stopEditing() {
    setEditingId(null);
    setDraftName("");
    setDraftDescription("");
  }

  async function updateScenario(event: FormEvent<HTMLFormElement>, scenarioId: string) {
    event.preventDefault();
    const trimmedName = draftName.trim();
    if (!trimmedName) {
      setStatus("Scenario name is required.");
      return;
    }

    setBusyId(scenarioId);
    setStatus(null);
    try {
      const response = await browserApiFetch(`${API_BASE_URL}/recommendations/scenarios/${scenarioId}`, {
        body: JSON.stringify({
          name: trimmedName,
          description: draftDescription.trim() || null
        }),
        headers: { "Content-Type": "application/json" },
        method: "PATCH"
      });
      if (!response.ok) {
        setStatus("Update failed.");
        return;
      }
      setStatus("Scenario updated.");
      stopEditing();
      router.refresh();
    } catch {
      setStatus("Update failed.");
    } finally {
      setBusyId(null);
    }
  }

  async function deleteScenario(scenario: RecommendationScenarioRead) {
    const confirmed = window.confirm(`Delete scenario "${scenario.name}"?`);
    if (!confirmed) return;

    setBusyId(scenario.id);
    setStatus(null);
    try {
      const response = await browserApiFetch(`${API_BASE_URL}/recommendations/scenarios/${scenario.id}`, {
        method: "DELETE"
      });
      if (!response.ok) {
        setStatus("Delete failed.");
        return;
      }
      setStatus("Scenario deleted.");
      if (editingId === scenario.id) stopEditing();
      router.refresh();
    } catch {
      setStatus("Delete failed.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section className="rounded-lg border border-line bg-panel p-4 shadow-soft">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-base font-semibold text-ink">Saved Scenarios</h2>
        <Badge tone="neutral">{scenarios.length}</Badge>
      </div>
      {status ? <p className="mt-2 text-xs text-neutral-500">{status}</p> : null}
      <div className="mt-3 grid gap-2">
        {scenarios.map((scenario) => {
          const isEditing = editingId === scenario.id;
          return (
            <div
              className="rounded-md border border-line px-3 py-3 text-sm"
              key={scenario.id}
            >
              {isEditing ? (
                <form className="grid gap-3" onSubmit={(event) => updateScenario(event, scenario.id)}>
                  <label className="grid gap-1.5 text-xs font-medium uppercase text-neutral-500">
                    Name
                    <input
                      className="h-10 rounded-md border border-line bg-white px-3 text-sm normal-case text-ink outline-none focus:border-teal"
                      maxLength={180}
                      onChange={(event) => setDraftName(event.target.value)}
                      value={draftName}
                    />
                  </label>
                  <label className="grid gap-1.5 text-xs font-medium uppercase text-neutral-500">
                    Notes
                    <textarea
                      className="min-h-20 rounded-md border border-line bg-white px-3 py-2 text-sm normal-case text-ink outline-none focus:border-teal"
                      onChange={(event) => setDraftDescription(event.target.value)}
                      value={draftDescription}
                    />
                  </label>
                  <div className="flex justify-end gap-2">
                    <button
                      className="inline-flex h-9 items-center gap-2 rounded-md border border-line bg-white px-3 text-sm font-semibold text-ink hover:border-teal"
                      onClick={stopEditing}
                      type="button"
                    >
                      <X size={15} />
                      Cancel
                    </button>
                    <button
                      className="inline-flex h-9 items-center gap-2 rounded-md bg-teal px-3 text-sm font-semibold text-white hover:bg-neutral-700 disabled:cursor-not-allowed disabled:opacity-60"
                      disabled={busyId === scenario.id}
                      type="submit"
                    >
                      <Check size={15} />
                      Save
                    </button>
                  </div>
                </form>
              ) : (
                <>
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="font-medium text-ink">{scenario.name}</div>
                      {scenario.description ? (
                        <div className="mt-1 line-clamp-2 text-neutral-600">
                          {scenario.description}
                        </div>
                      ) : null}
                    </div>
                    <Badge tone="teal">Top {scenario.request.top_k}</Badge>
                  </div>
                  <div className="mt-2 text-xs text-neutral-500">
                    {formatDate(scenario.updated_at)}
                  </div>
                  <div className="mt-3 flex flex-wrap justify-end gap-2">
                    <Link
                      className="inline-flex h-9 items-center gap-2 rounded-md border border-line bg-white px-3 text-sm font-semibold text-ink hover:border-teal"
                      href={recommendationRequestHref(scenario.request)}
                    >
                      <ExternalLink size={15} />
                      Open
                    </Link>
                    <button
                      className="inline-flex h-9 items-center gap-2 rounded-md border border-line bg-white px-3 text-sm font-semibold text-ink hover:border-teal"
                      onClick={() => startEditing(scenario)}
                      type="button"
                    >
                      <Pencil size={15} />
                      Edit
                    </button>
                    <button
                      className="inline-flex h-9 items-center gap-2 rounded-md border border-line bg-white px-3 text-sm font-semibold text-rose hover:border-rose disabled:cursor-not-allowed disabled:opacity-60"
                      disabled={busyId === scenario.id}
                      onClick={() => deleteScenario(scenario)}
                      type="button"
                    >
                      <Trash2 size={15} />
                      Delete
                    </button>
                  </div>
                </>
              )}
            </div>
          );
        })}
        {!scenarios.length ? (
          <p className="rounded-md border border-line px-3 py-3 text-sm text-neutral-600">
            No saved scenarios.
          </p>
        ) : null}
      </div>
    </section>
  );
}
