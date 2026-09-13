import { useMemo } from "react";
import {
  compareQueryText,
  describeCharacter,
  type QueryCharacter,
} from "@/lib/requestTextDiff";

function QueryLine({
  label,
  characters,
  kind,
}: {
  label: string;
  characters: QueryCharacter[];
  kind: "added" | "removed";
}) {
  const action = kind === "added" ? "추가" : "누락";
  const spaces = characters.filter((c) => c.value === " ").length;
  return (
    <div className="min-w-0">
      <h5 className="text-sm font-medium">{label}</h5>
      <p className="mt-1 text-xs text-neutral-500">
        {characters.length} 코드 포인트 · 공백(SP) {spaces}개
      </p>
      <div
        aria-label={`${label} 문자 비교`}
        className="mt-2 min-h-16 max-h-64 overflow-y-auto border-l-2 border-neutral-300 bg-white p-3 font-mono text-sm leading-8 [overflow-wrap:anywhere]"
        dir="ltr"
      >
        {characters.length === 0 && (
          <span className="text-neutral-500">빈 문자열</span>
        )}
        {characters.map((character) => {
          const { code, marker, display } = describeCharacter(character.value);
          const description = `${character.position}번째 · ${code}${marker ? ` · ${marker}` : ""}${character.changed ? ` · ${action}` : ""}`;
          const content = (
            <>
              <span aria-hidden="true">{display}</span>
              <span className="sr-only">
                {description}
                {marker ? "" : ` · ${character.value}`}{" "}
              </span>
            </>
          );
          return character.changed ? (
            <mark
              key={character.position}
              title={description}
              className={
                kind === "added"
                  ? "bg-red-100 text-red-900 underline decoration-2 underline-offset-4"
                  : "bg-amber-100 text-amber-900 underline decoration-dashed decoration-2 underline-offset-4"
              }
            >
              {content}
            </mark>
          ) : (
            <span
              key={character.position}
              title={description}
              className={marker ? "text-neutral-500" : undefined}
            >
              {content}
            </span>
          );
        })}
      </div>
    </div>
  );
}

export function RequestQueryDiff({
  expected,
  submitted,
}: {
  expected: string;
  submitted: string;
}) {
  const difference = useMemo(
    () => compareQueryText(expected, submitted),
    [expected, submitted],
  );
  return (
    <section
      aria-label="query 문자 차이"
      className="min-w-0 border-t border-line pt-4"
    >
      <h4 className="text-sm font-semibold">query 문자 차이</h4>
      <dl className="my-3 flex flex-wrap gap-x-6 gap-y-2 text-xs">
        <div className="flex gap-2 text-red-900">
          <dt>입력에 추가</dt>
          <dd>{difference.added}개</dd>
        </div>
        <div className="flex gap-2 text-amber-900">
          <dt>기준에서 누락</dt>
          <dd>{difference.removed}개</dd>
        </div>
      </dl>
      <div className="grid min-w-0 gap-4 lg:grid-cols-2">
        <QueryLine
          label="기준 query"
          characters={difference.reference}
          kind="removed"
        />
        <QueryLine
          label="제출한 query"
          characters={difference.actual}
          kind="added"
        />
      </div>
      <dl className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-neutral-500">
        {[
          ["SP", "공백"],
          ["TAB", "탭"],
          ["LF", "줄바꿈"],
          ["CR", "캐리지 리턴"],
          ["NBSP", "줄바꿈 없는 공백"],
        ].map(([symbol, name]) => (
          <div className="flex gap-1" key={symbol}>
            <dt className="font-mono">[{symbol}]</dt>
            <dd>{name}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
