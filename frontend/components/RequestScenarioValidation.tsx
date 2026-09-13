"use client";

import { ArrowLeft, FlaskConical, LoaderCircle } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { RequestInputStudy } from "@/components/RequestInputStudy";
import { RequestScenarioResults } from "@/components/RequestScenarioResults";
import { scenarioApi } from "@/lib/requestScenarioApi";
import type {
  ScenarioCatalog,
  ScenarioRun,
  StudyAttempt,
} from "@/types/requestScenarios";

export function RequestScenarioValidation() {
  const [tab, setTab] = useState("runs");
  const [catalog, setCatalog] = useState<ScenarioCatalog | null>(null);
  const [runs, setRuns] = useState<ScenarioRun[]>([]);
  const [attempts, setAttempts] = useState<StudyAttempt[]>([]);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    void Promise.all([
      scenarioApi<ScenarioCatalog>("/catalog"),
      scenarioApi<ScenarioRun[]>("/runs"),
      scenarioApi<StudyAttempt[]>("/studies"),
    ])
      .then(([c, r, a]) => {
        if (active) {
          setCatalog(c);
          setRuns(r);
          setAttempts(a);
        }
      })
      .catch((e: Error) => {
        if (active) setError(e.message);
      })
      .finally(() => {
        if (active) setBusy(false);
      });
    return () => {
      active = false;
    };
  }, []);
  async function run() {
    setBusy(true);
    setError("");
    try {
      const next = await scenarioApi<ScenarioRun>("/runs", "POST");
      setRuns((current) => [next, ...current].slice(0, 20));
    } catch (e) {
      setError(e instanceof Error ? e.message : "검사 실행 실패");
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line pb-5">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold">
            <FlaskConical size={24} />
            요청 시나리오 검증
          </h1>
          <div className="mt-2 flex flex-wrap gap-3 text-xs text-neutral-500">
            <span>로컬 실험</span>
            <span>공식 Gate 미반영</span>
            <span>독립 사용자 검증 전</span>
            <Link
              href="/structured-requests/workflow"
              className="text-teal-800 underline"
            >
              전체 흐름 검증
            </Link>
          </div>
        </div>
        <Link
          className="inline-flex items-center gap-2 text-sm underline"
          href="/structured-requests"
        >
          <ArrowLeft size={16} />
          요청 계약
        </Link>
      </header>
      {error && (
        <p
          role="alert"
          className="border-l-4 border-red-600 bg-red-50 p-4 text-sm text-red-900"
        >
          {error}
        </p>
      )}
      <div
        role="tablist"
        aria-label="시나리오 검증 종류"
        className="flex items-center gap-5 border-b border-line"
      >
        {[
          { id: "runs", label: "자동 검사" },
          { id: "studies", label: "입력 검증" },
        ].map((item) => (
          <button
            role="tab"
            aria-selected={tab === item.id}
            tabIndex={tab === item.id ? 0 : -1}
            aria-controls={`panel-${item.id}`}
            id={`tab-${item.id}`}
            key={item.id}
            className={`min-h-11 border-b-2 text-sm ${tab === item.id ? "border-teal-700 font-semibold text-teal-900" : "border-transparent text-neutral-500"}`}
            onClick={() => setTab(item.id)}
            onKeyDown={(event) => {
              if (
                !["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)
              )
                return;
              event.preventDefault();
              const next =
                event.key === "Home"
                  ? "runs"
                  : event.key === "End"
                    ? "studies"
                    : tab === "runs"
                      ? "studies"
                      : "runs";
              setTab(next);
              event.currentTarget.parentElement
                ?.querySelector<HTMLButtonElement>(`#tab-${next}`)
                ?.focus();
            }}
          >
            {item.label}
          </button>
        ))}
        {busy && (
          <LoaderCircle
            size={16}
            className="animate-spin"
            aria-label="처리 중"
          />
        )}
      </div>
      <div
        role="tabpanel"
        id="panel-runs"
        aria-labelledby="tab-runs"
        hidden={tab !== "runs"}
      >
        <RequestScenarioResults
          runs={runs}
          busy={busy}
          onRun={() => void run()}
        />
      </div>
      <div
        role="tabpanel"
        id="panel-studies"
        aria-labelledby="tab-studies"
        hidden={tab !== "studies"}
      >
        <RequestInputStudy
          tasks={catalog?.tasks ?? []}
          attempts={attempts}
          onChange={(a) =>
            setAttempts((current) =>
              [a, ...current.filter((r) => r.id !== a.id)].slice(0, 20),
            )
          }
        />
      </div>
    </>
  );
}
