const test = require("node:test");
const assert = require("node:assert/strict");
const { createRendererServer, installBrowserGlobals } = require("../lib/rendererTestHarness");

async function loadStore(t, seed = {}) {
  installBrowserGlobals(t);
  for (const [key, value] of Object.entries(seed)) localStorage.setItem(key, value);
  const vite = await createRendererServer(t, { cachePrefix: "dictation-asr-default-" });
  const { useSettingsStore } = await vite.ssrLoadModule("/stores/settingsStore.ts");
  return useSettingsStore.getState();
}

test("fresh profiles use Parakeet Unified EN", async (t) => {
  const state = await loadStore(t);
  assert.equal(state.localTranscriptionProvider, "nvidia");
  assert.equal(state.parakeetModel, "parakeet-unified-en-0.6b");
  assert.equal(localStorage.getItem("_dictationUnifiedEnMigrated"), "1");
});

test("a profile on a streaming Nemotron model moves to Unified EN once", async (t) => {
  const state = await loadStore(t, { parakeetModel: "nemotron-speech-streaming-en-0.6b" });
  assert.equal(state.parakeetModel, "parakeet-unified-en-0.6b");
});

test("a profile that chose another model, or already migrated, is left alone", async (t) => {
  const kept = await loadStore(t, { parakeetModel: "parakeet-tdt-0.6b-v3" });
  assert.equal(kept.parakeetModel, "parakeet-tdt-0.6b-v3");
});

test("after the migration ran, a later Nemotron pick is respected", async (t) => {
  const state = await loadStore(t, {
    parakeetModel: "nemotron-3.5-asr-streaming-0.6b",
    _dictationUnifiedEnMigrated: "1",
  });
  assert.equal(state.parakeetModel, "nemotron-3.5-asr-streaming-0.6b");
});
