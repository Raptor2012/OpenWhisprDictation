const test = require("node:test");
const assert = require("node:assert/strict");
const { createRendererServer, installBrowserGlobals } = require("../lib/rendererTestHarness");

// Load the actual renderer graph and settings resolver: a CommonJS-only guard
// must not break local decoding or silently bypass the configured cleanup.
test("local dictation decodes, cleans up and retains raw text without cloud fallback", async (t) => {
  const { window } = installBrowserGlobals(t);
  const vite = await createRendererServer(t, {
    cachePrefix: "dictation-local-pipeline-",
    mockModules: {
      "/utils/logger":
        "export default { debug() {}, info() {}, warn() {}, error() {}, logReasoning() {} };",
    },
  });
  const AudioManager = (await vite.ssrLoadModule("/helpers/audioManager.js")).default;
  const service = (await vite.ssrLoadModule("/services/ReasoningService.ts")).default;
  t.after(() => service.destroy());
  const { useSettingsStore } = await vite.ssrLoadModule("/stores/settingsStore.ts");
  const { usePolicyStore } = await vite.ssrLoadModule("/stores/policyStore.ts");
  usePolicyStore.setState({ status: "unmanaged", policy: null });
  useSettingsStore.setState({
    useLocalWhisper: true,
    localTranscriptionProvider: "nvidia",
    preferredLanguage: "en",
    useCleanupModel: true,
    cleanupMode: "local",
    cleanupProvider: "local",
    cleanupModel: "gemma-4-e4b-it-qat-q4_0",
    useDictationAgent: false,
    customPrompts: { cleanup: "" },
    allowOpenAIFallback: true, // Old preferences must never re-enable uploads.
  });
  const raw = "um send the report by friday";
  const cleaned = "Send the report by Friday.";
  const manager = Object.assign(Object.create(AudioManager.prototype), {
    voiceAgentRequested: false,
    translationRequested: false,
    pendingCleanupFailure: null,
    isReasoningAvailable: async () => true,
  });
  const audio = new Blob([new Uint8Array([1, 2, 3])], { type: "audio/webm" });
  let cleanups = 0;
  let cloudCleanups = 0;
  window.electronAPI.transcribeLocalParakeet = async (buffer) => {
    assert.deepEqual([...new Uint8Array(buffer)], [1, 2, 3]);
    return { success: true, text: raw };
  };
  window.electronAPI.processLocalReasoning = async () => {
    cleanups++;
    return { success: true, text: cleaned };
  };
  manager.processWithOpenAIAPI = async () => assert.fail("audio must stay local");
  window.electronAPI.cloudReason = async () => {
    cloudCleanups++;
    return { success: true, text: raw };
  };

  const result = await manager.processWithLocalParakeet(audio);
  assert.equal(result.text, cleaned);
  assert.equal(result.rawText, raw);
  assert.equal(result.source, "local-parakeet");
  assert.equal(cleanups, 1);

  window.electronAPI.processLocalReasoning = async () => ({
    success: false,
    error: "local cleanup unavailable",
  });
  assert.equal((await manager.processWithLocalParakeet(audio)).text, raw);
  assert.match(
    manager._takePendingResultExtras().cleanupFailure.message,
    /local cleanup unavailable/
  );

  // A stale remote cleanup setting preserves the transcript without invoking it.
  useSettingsStore.setState({ cleanupMode: "openwhispr" });
  assert.equal((await manager.processWithLocalParakeet(audio)).text, raw);
  assert.equal(cleanups, 1);
  assert.equal(cloudCleanups, 0, "stale cleanup preferences must never upload a transcript");

  // A failed local engine cannot fall through to the old cloud fallback.
  window.electronAPI.transcribeLocalParakeet = async () => ({
    success: false,
    message: "engine unavailable",
  });
  await assert.rejects(manager.processWithLocalParakeet(audio), /engine unavailable/);
});
