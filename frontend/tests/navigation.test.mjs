import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import test from "node:test";
import { runInNewContext } from "node:vm";
import ts from "typescript";

const require = createRequire(import.meta.url);

// Execute the actual handlers with API/router doubles, without adding a DOM test stack.
function loadFunction(file, name, bindings) {
  const text = readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
  const source = ts.createSourceFile(file, text, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  let declaration;
  function find(node) {
    if (ts.isFunctionDeclaration(node) && node.name?.text === name) declaration = node;
    else ts.forEachChild(node, find);
  }
  find(source);
  assert.ok(declaration, `${file}: ${name}`);
  const { outputText } = ts.transpileModule(
    `${declaration.getText(source)}\nmodule.exports = ${name};`,
    { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } },
  );
  const compiledModule = { exports: {} };
  runInNewContext(outputText, { module: compiledModule, exports: compiledModule.exports, require, URLSearchParams, ...bindings });
  return compiledModule.exports;
}

function environment(ok = true) {
  const navigation = [];
  const requests = [];
  const payload = {
    status: "queued",
    manifest: { digest_value: "verified-digest" },
    deployment_configuration: { id: "observed-config" },
  };
  const noop = () => {};
  return {
    navigation, requests,
    bindings: {
      router: { push: (href) => navigation.push(href), refresh: () => navigation.push("refresh") },
      API_BASE_URL: "http://fixture.invalid/api/v1",
      browserApiFetch: async (url, options) => {
        requests.push({ url, body: JSON.parse(options.body) });
        return { ok, json: async () => payload };
      },
      responseError: async () => "fixture failure",
      errorMessage: () => "fixture failure",
      pollAgentJob: async () => ({ status: "completed", result_json: { benchmark_run_id: "result-run" } }),
      setBusyId: noop, setNotice: noop, setJobs: noop, setStatus: noop, setSummary: noop, setBusy: noop,
      benchmarkRunId: "selected-run",
      file: { name: "labels.json", text: async () => "[]" },
      configurationId: "source-config", baseUrl: "http://fixture.invalid", modelName: "fixture-model", suiteId: "suite",
      decision: "REQUEST_CHANGES", decidedBy: "fixture-reviewer", signerRole: "QA Lead",
      ticketReference: "", signatureStatement: "fixture signature", decisionReason: "fixture reason",
      notes: "", replacesReleaseDecisionId: undefined, gateEvaluationId: "selected-gate",
    },
  };
}

const flows = [
  { file: "AgentApprovalControlPanel", handler: "resume", args: [{ id: "checkpoint", version: 2 }], href: "/benchmark-executions/result-run" },
  { file: "JudgeLabelImportForm", handler: "submit", args: [true], href: "/judge-labels?benchmark_run_id=selected-run" },
  { file: "ModelValidationConsole", handler: "attestRuntime", args: [], href: "/model-validation?deployment_configuration_id=observed-config&evaluation_suite_id=suite" },
  { file: "ReleaseDecisionForm", handler: "submit", args: [{ preventDefault() {} }], href: "/release-decisions?gate_evaluation_id=selected-gate" },
];

for (const flow of flows) {
  test(`${flow.file}: successful action navigates and refreshes server data`, async () => {
    const { bindings, navigation, requests } = environment();
    await loadFunction(`components/${flow.file}.tsx`, flow.handler, bindings)(...flow.args);
    assert.deepEqual(navigation, [flow.href, "refresh"]);
    assert.equal(requests.length, 1);
  });

  test(`${flow.file}: rejected action does not navigate`, async () => {
    const { bindings, navigation } = environment(false);
    await loadFunction(`components/${flow.file}.tsx`, flow.handler, bindings)(...flow.args);
    assert.deepEqual(navigation, []);
  });
}

test("judge-label dry run never navigates or applies labels", async () => {
  const { bindings, navigation, requests } = environment();
  await loadFunction("components/JudgeLabelImportForm.tsx", "submit", bindings)(false);
  assert.deepEqual(navigation, []);
  assert.equal(requests[0].body.apply_labels, false);
});

test("failed resume job never opens a result page", async () => {
  const { bindings, navigation } = environment();
  bindings.pollAgentJob = async () => ({ status: "failed", last_error: "fixture failure" });
  await loadFunction("components/AgentApprovalControlPanel.tsx", "resume", bindings)({ id: "checkpoint", version: 2 });
  assert.deepEqual(navigation, []);
});

test("incomplete runtime attestation does not send a request", async () => {
  const { bindings, navigation, requests } = environment();
  bindings.modelName = "";
  await loadFunction("components/ModelValidationConsole.tsx", "attestRuntime", bindings)();
  assert.deepEqual(navigation, []);
  assert.deepEqual(requests, []);
});

test("validation navigation resets state when the configuration or server report changes", async () => {
  const Console = () => null;
  let hash = "report-one";
  const page = loadFunction("app/model-validation/page.tsx", "ModelValidationPage", {
    Badge: () => null,
    ModelValidationConsole: Console,
    api: {
      deploymentConfigurations: async () => ["source-config", "observed-config"].map((id) => ({ id, workload_profile_id: "workload" })),
      evaluationSuites: async () => [{ id: "suite", workload_profile_id: "workload", is_synthetic: false }],
      benchmarkTasks: async () => [], promptVersions: async () => [],
      modelValidationReport: async () => ({ report_hash: hash }),
    },
  });
  async function consoleFor(configuration) {
    const result = await page({ searchParams: Promise.resolve({ deployment_configuration_id: configuration, evaluation_suite_id: "suite" }) });
    return result.props.children.find((element) => element.type === Console);
  }
  const original = await consoleFor("source-config");
  assert.equal((await consoleFor("source-config")).key, original.key);
  const observed = await consoleFor("observed-config");
  assert.equal(observed.props.initialConfigurationId, "observed-config");
  assert.notEqual(observed.key, original.key);
  hash = "report-two";
  assert.notEqual((await consoleFor("observed-config")).key, observed.key);
});
