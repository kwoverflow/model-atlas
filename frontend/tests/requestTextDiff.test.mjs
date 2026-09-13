import assert from "node:assert/strict";
import test from "node:test";
import { compareQueryText, describeCharacter } from "../lib/requestTextDiff.ts";

const cases = [
  ["identical", "ticket", "ticket", 0, 0],
  ["empty", "", "", 0, 0],
  ["insertion", "ab", "axb", 1, 0],
  ["deletion", "axb", "ab", 0, 1],
  ["replacement", "cat", "cut", 1, 1],
  ["leading and trailing spaces", "query", " query ", 2, 0],
  [
    "double space",
    "\uc815\uae30 \uc810\uac80 \uc54c\ub9bc",
    "\uc815\uae30  \uc810\uac80 \uc54c\ub9bc",
    1,
    0,
  ],
  ["tab versus space", "a b", "a\tb", 1, 1],
  ["CRLF versus LF", "a\nb", "a\r\nb", 1, 0],
  ["NBSP versus space", "a b", "a\u00a0b", 1, 1],
  ["zero width space", "ab", "a\u200bb", 1, 0],
  ["astral code point", "a\u{1f600}b", "ab", 0, 1],
  ["canonical equivalents remain different", "\u00e9", "e\u0301", 2, 1],
  ["case remains different", "Low", "low", 1, 1],
  ["all missing", "abc", "", 0, 3],
  ["all added", "", "abc", 3, 0],
  [
    "maximum-length different queries",
    "a".repeat(1000),
    "b".repeat(1000),
    1000,
    1000,
  ],
];

for (const [name, expected, submitted, added, removed] of cases) {
  test(name, () => {
    const result = compareQueryText(expected, submitted);
    assert.equal(result.added, added);
    assert.equal(result.removed, removed);
    assert.equal(result.reference.map((c) => c.value).join(""), expected);
    assert.equal(result.actual.map((c) => c.value).join(""), submitted);
    for (const row of [result.reference, result.actual]) {
      assert.deepEqual(
        row.map((c) => c.position),
        row.map((_, i) => i + 1),
      );
    }
  });
}

test("the pilot's doubled space is located precisely", () => {
  const result = compareQueryText(
    "\uc815\uae30 \uc810\uac80 \uc54c\ub9bc",
    "\uc815\uae30  \uc810\uac80 \uc54c\ub9bc",
  );
  assert.deepEqual(
    result.actual.filter((c) => c.changed),
    [{ value: " ", position: 4, changed: true }],
  );
  assert.equal(result.reference.length, 8);
  assert.equal(result.actual.length, 9);
});

test("invisible characters have distinct labels without changing raw values", () => {
  for (const [value, marker] of [
    [" ", "SP"],
    ["\t", "TAB"],
    ["\n", "LF"],
    ["\r", "CR"],
    ["\u00a0", "NBSP"],
    ["\u200b", "U+200B"],
    ["\u202e", "U+202E"],
    ["\u0000", "U+0000"],
    ["\ufe0f", "U+FE0F"],
  ]) {
    assert.equal(describeCharacter(value).display, `[${marker}]`);
  }
  assert.deepEqual(describeCharacter("a"), {
    code: "U+0061",
    marker: null,
    display: "a",
  });
});

test("many short inputs reconstruct exactly and only align equal characters", () => {
  const inputs = ["", "a", "b", " ", "\t", "\u200b", "\uc815", "\u{1f600}"];
  const combinations = inputs.flatMap((a) => inputs.map((b) => a + b));
  for (const expected of combinations) {
    for (const submitted of combinations) {
      const result = compareQueryText(expected, submitted);
      assert.equal(result.reference.map((c) => c.value).join(""), expected);
      assert.equal(result.actual.map((c) => c.value).join(""), submitted);
      assert.deepEqual(
        result.reference.filter((c) => !c.changed).map((c) => c.value),
        result.actual.filter((c) => !c.changed).map((c) => c.value),
      );
    }
  }
});
