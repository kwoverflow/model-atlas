import assert from "node:assert/strict";
import test from "node:test";
import { browserApiFetch } from "../lib/browserApi.ts";

// Synthetic DOM fixture only; no real browser session or network is read.
function fixture(t, documentValue) {
  const previous = Object.getOwnPropertyDescriptor(globalThis, "document");
  if (documentValue === undefined) delete globalThis.document;
  else
    Object.defineProperty(globalThis, "document", {
      value: documentValue,
      configurable: true,
    });
  t.after(() => {
    if (previous) Object.defineProperty(globalThis, "document", previous);
    else delete globalThis.document;
  });
  const calls = [];
  t.mock.method(globalThis, "fetch", async (input, init) => {
    calls.push({ input, init });
    return new Response("{}", { status: 200 });
  });
  return calls;
}

test("GET includes credentials without reading a CSRF cookie", async (t) => {
  const calls = fixture(t, {
    get cookie() {
      throw new Error("GET must not read cookies");
    },
  });
  await browserApiFetch("https://example.invalid/me");
  assert.equal(calls[0].init.credentials, "include");
  assert.equal(calls[0].init.headers.has("x-model-atlas-csrf"), false);
});

for (const method of ["POST", "put", "PATCH", "DELETE"]) {
  test(`${method} includes the exact synthetic CSRF cookie and preserves request fields`, async (t) => {
    const calls = fixture(t, {
      cookie:
        "model_atlas_csrf_extra=wrong; model_atlas_csrf=qa%2Btoken; other=unused",
    });
    const controller = new AbortController();
    const headers = new Headers({ "x-model-atlas-lab-action": "1" });
    await browserApiFetch("https://example.invalid/studies", {
      method,
      headers,
      body: "{}",
      signal: controller.signal,
      credentials: "omit",
    });
    assert.equal(calls.length, 1);
    assert.equal(calls[0].init.credentials, "include");
    assert.equal(calls[0].init.headers.get("x-model-atlas-csrf"), "qa+token");
    assert.equal(calls[0].init.headers.get("x-model-atlas-lab-action"), "1");
    assert.equal(headers.has("x-model-atlas-csrf"), false);
    assert.equal(calls[0].init.body, "{}");
    assert.equal(calls[0].init.signal, controller.signal);
  });
}

test("SSR without document does not invent a CSRF token", async (t) => {
  const calls = fixture(t, undefined);
  await browserApiFetch("https://example.invalid/studies", { method: "POST" });
  assert.equal(calls[0].init.headers.has("x-model-atlas-csrf"), false);
});

test("unrelated cookies do not become a CSRF token", async (t) => {
  const calls = fixture(t, {
    cookie: "other=qa; model_atlas_csrf_extra=wrong",
  });
  await browserApiFetch("https://example.invalid/studies", { method: "POST" });
  assert.equal(calls[0].init.headers.has("x-model-atlas-csrf"), false);
});

test("unauthorized responses are returned unchanged without retrying", async (t) => {
  fixture(t, undefined);
  const denied = new Response("unauthorized", { status: 401 });
  const fetchMock = t.mock.method(globalThis, "fetch", async () => denied);
  assert.equal(await browserApiFetch("https://example.invalid/me"), denied);
  assert.equal(fetchMock.mock.callCount(), 1);
});

test("network rejection is not converted into a successful response", async (t) => {
  fixture(t, undefined);
  const failure = new Error("synthetic transport failure");
  t.mock.method(globalThis, "fetch", async () => {
    throw failure;
  });
  await assert.rejects(
    browserApiFetch("https://example.invalid/me"),
    (error) => error === failure,
  );
});
