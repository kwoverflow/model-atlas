// Structural-only export after the shared reader's browser packaging failed.
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const [pluginRoot, artifactPath, htmlPath] = process.argv.slice(2);
if (!pluginRoot || !artifactPath || !htmlPath) {
  throw new Error("Expected plugin root, artifact JSON path, and output HTML path");
}
if (existsSync(htmlPath) || existsSync(`${htmlPath}.verification.json`)) {
  throw new Error("Output already exists");
}
const scriptRoot = resolve(pluginRoot, "skills/build-report/scripts");
const { buildPortableArtifact } = await import(pathToFileURL(resolve(scriptRoot, "build_portable_artifact.mjs")));
const { verifyPortableArtifactStructure } = await import(pathToFileURL(resolve(scriptRoot, "verify_portable_artifact.mjs")));
const artifact = JSON.parse(readFileSync(artifactPath, "utf8"));
writeFileSync(htmlPath, buildPortableArtifact(artifact), { encoding: "utf8", flag: "wx" });
const verification = verifyPortableArtifactStructure({ artifactPath, htmlPath });
const receipt = {
  mode: "semantic_fallback",
  prior_delivery_failure: "reader_timeout: shared reader remained in fallback",
  structural_verification: verification,
  browser_verification: "not_performed",
  chart_svg_extraction: "not_performed",
  interaction_and_layout_verified: false,
};
writeFileSync(`${htmlPath}.verification.json`, JSON.stringify(receipt, null, 2), { encoding: "utf8", flag: "wx" });
process.stdout.write(JSON.stringify(receipt));
