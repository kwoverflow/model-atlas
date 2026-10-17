// Mechanical import of the pinned MIT upstream package; never overwrites a patch.
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { cpSync, existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { resolve, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../", import.meta.url));
const work = resolve(root, "tmp/next-eslint-upstream");
const archive = join(work, "next-eslint-plugin-next-16.4.2.tgz");
const integrity = "gCTWlw0e+Y6kajpFyKKgA195jUJCRhlzJE0lV7ufe8a+ghIsANWZ0/FiJwg6DuOG1+OvRbcZDcFBoRh3mNJx0g==";
if (createHash("sha512").update(readFileSync(archive)).digest("base64") !== integrity) {
  throw new Error("Pinned upstream tarball integrity mismatch");
}
const target = resolve(root, "frontend/tooling/next-eslint-plugin");
if (existsSync(target)) throw new Error("Refusing to overwrite the existing security patch");
execFileSync("tar", ["-xzf", archive, "-C", work]);
mkdirSync(target, { recursive: true });
cpSync(join(work, "package/dist"), join(target, "lib"), { recursive: true });
cpSync(resolve(root, "frontend/node_modules/next/license.md"), join(target, "LICENSE.md"));
const files = {};
function walk(dir) {
  for (const item of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, item.name);
    if (item.isDirectory()) walk(path);
    else files[relative(join(target, "lib"), path).replaceAll("\\", "/")] = createHash("sha256").update(readFileSync(path)).digest("hex");
  }
}
walk(join(target, "lib"));
writeFileSync(join(target, "UPSTREAM.json"), `${JSON.stringify({
  package: "@next/eslint-plugin-next", version: "16.4.2",
  tarball: "https://registry.npmjs.org/@next/eslint-plugin-next/-/eslint-plugin-next-16.4.2.tgz",
  integrity: `sha512-${integrity}`,
  changed_file: "utils/get-root-dirs.js", files
}, null, 2)}\n`, { flag: "wx" });
console.log(JSON.stringify({ status: "imported_pinned_upstream", files: Object.keys(files).length }));
