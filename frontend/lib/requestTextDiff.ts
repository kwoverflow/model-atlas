import { diffChars } from "diff";

export type QueryCharacter = {
  value: string;
  position: number;
  changed: boolean;
};

const visibleControls: Record<string, string> = {
  " ": "SP",
  "\t": "TAB",
  "\n": "LF",
  "\r": "CR",
  "\u00a0": "NBSP",
};
const invisible =
  /[\p{White_Space}\p{Cc}\p{Cf}\p{Default_Ignorable_Code_Point}]/u;

export function describeCharacter(value: string) {
  const code = `U+${value.codePointAt(0)!.toString(16).toUpperCase().padStart(4, "0")}`;
  const marker =
    visibleControls[value] ?? (invisible.test(value) ? code : null);
  return { code, marker, display: marker ? `[${marker}]` : value };
}

// Expected -> submitted, with no whitespace, case or Unicode normalization.
export function compareQueryText(expected: string, submitted: string) {
  const reference: QueryCharacter[] = [];
  const actual: QueryCharacter[] = [];
  for (const part of diffChars(expected, submitted)) {
    for (const value of part.value) {
      if (!part.added) {
        reference.push({
          value,
          position: reference.length + 1,
          changed: part.removed,
        });
      }
      if (!part.removed) {
        actual.push({
          value,
          position: actual.length + 1,
          changed: part.added,
        });
      }
    }
  }
  return {
    reference,
    actual,
    removed: reference.filter((c) => c.changed).length,
    added: actual.filter((c) => c.changed).length,
  };
}
