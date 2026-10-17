import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { createRequire } from "node:module";
import { readFileSync, readdirSync } from "node:fs";
import { resolve, relative, dirname } from "node:path";
import test from "node:test";
import { ESLint } from "eslint";

const require = createRequire(import.meta.url);
const root = resolve(import.meta.dirname, "..");
const vendor = resolve(root, "tooling/next-eslint-plugin");
const upstream = JSON.parse(readFileSync(resolve(vendor, "UPSTREAM.json"), "utf8"));
const installed = dirname(require.resolve("@next/eslint-plugin-next/package.json"));
const { getRootDirs } = require("@next/eslint-plugin-next/lib/utils/get-root-dirs.js");
const context = (rootDir) => ({ cwd: root, settings: { next: { rootDir } } });

test("all upstream files except the documented root resolver are byte-identical", () => {
  const paths = readdirSync(resolve(vendor, "lib"), { recursive: true, withFileTypes: true })
    .filter((entry) => entry.isFile())
    .map((entry) => relative(resolve(vendor, "lib"), resolve(entry.parentPath, entry.name)).replaceAll("\\", "/"));
  assert.deepEqual(paths.sort(), Object.keys(upstream.files).sort());
  const changed = paths.filter((path) => createHash("sha256")
    .update(readFileSync(resolve(vendor, "lib", path))).digest("hex") !== upstream.files[path]);
  assert.deepEqual(changed, ["utils/get-root-dirs.js"]);
  assert.equal(paths.length, 54);
  assert.equal(upstream.version, "16.4.2");
  for (const path of paths) {
    assert.deepEqual(readFileSync(resolve(installed, "lib", path)), readFileSync(resolve(vendor, "lib", path)), path);
  }
});

test("real ESLint config rejects hostile root patterns before linting", async () => {
  const eslint = new ESLint({ cwd: root, overrideConfig: {
    settings: { next: { rootDir: "{".repeat(100_000) } },
  } });
  await assert.rejects(() => eslint.lintText("export default () => <a href='/'>x</a>;", {
    filePath: resolve(root, "components/security-pattern-probe.tsx"),
  }), /explicit directory path/);
});

test("npm resolves the local patch and has no vulnerable glob dependency nodes", () => {
  assert.equal(require("@next/eslint-plugin-next/package.json").version, "16.4.2-model-atlas.1");
  const lock = JSON.parse(readFileSync(resolve(root, "package-lock.json"), "utf8"));
  for (const name of ["braces", "fast-glob", "micromatch", "postcss-nested", "postcss-selector-parser"]) {
    assert.equal(Object.keys(lock.packages).some((path) => path.endsWith(`/node_modules/${name}`) || path === `node_modules/${name}`), false, name);
  }
});

test("default roots, explicit paths and missing directories preserve expected behavior", () => {
  assert.deepEqual(getRootDirs(context(undefined)), [root]);
  assert.deepEqual(getRootDirs(context(".")), [root]);
  assert.deepEqual(getRootDirs(context(root)), [root]);
  assert.deepEqual(getRootDirs(context(["app", "components", 42])), [resolve(root, "app"), resolve(root, "components")]);
  assert.deepEqual(getRootDirs(context("does-not-exist-security-probe")), []);
  assert.deepEqual(getRootDirs(context("package.json")), []);
});

test("glob syntax, oversized inputs and deeply nested braces fail closed", () => {
  for (const input of ["packages/*", "app/?", "app/[a]", "{app,lib}", "!app", "a\0b", "", "{".repeat(100_000), "a".repeat(4097)]) {
    assert.throws(() => getRootDirs(context(input)), /explicit directory path/);
  }
  assert.throws(() => getRootDirs(context(Array(129).fill("app"))), /Too many/);
});

test("Next and React hooks rules still detect real violations through the unchanged config", async () => {
  const eslint = new ESLint({ cwd: root });
  const [result] = await eslint.lintText(`
    "use client";
    import { useState } from "react";
    export default function Probe({ enabled }) {
      if (enabled) useState(0);
      return <><img src="/x.png" alt="x" /><a href="/">x</a><script src="/x.js" /></>;
    }
  `, { filePath: resolve(root, "components/security-probe.tsx") });
  const rules = new Set(result.messages.map((message) => message.ruleId));
  for (const rule of ["react-hooks/rules-of-hooks", "@next/next/no-img-element", "@next/next/no-html-link-for-pages", "@next/next/no-sync-scripts"]) {
    assert.ok(rules.has(rule), `${rule}: ${JSON.stringify(result.messages)}`);
  }
});
