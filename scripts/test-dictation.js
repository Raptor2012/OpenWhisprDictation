// Supported Windows local-dictation regression gate. The upstream cross-platform
// suite remains available through npm test, including removed cloud features.
const { spawnSync } = require("node:child_process");
const path = require("node:path");

const files = [
  "helpers/clipboardRestore",
  "helpers/noExternalFieldMonitoring",
  "helpers/localGemmaDefault",
  "helpers/localNetworkBoundary",
  "helpers/localOnlyDictation",
  "helpers/localDictationPipeline",
  "helpers/nativeListenerKeys",
  "helpers/hotkeyValidation",
  "helpers/dictationIdentity",
  "helpers/windowsKeyManagerMouse",
  "helpers/hotkeyActivationMode",
  "helpers/hotkeyStartup",
  "helpers/correctionLearner",
  "helpers/bundledGpuPacks",
  "helpers/audioManagerCancelLifecycle",
  "helpers/audioManagerInterruptedRecording",
  "helpers/audioManagerNoAudioLifecycle",
  "helpers/audioManagerPcmTapLifecycle",
  "helpers/audioManagerPreviewFinalization",
  "helpers/useAudioRecordingLatency",
  "helpers/audioManagerRawWav",
  "helpers/cleanupRouteConfig",
  "utils/vocabularyAliases",
  "utils/snippets",
  "components/controlPanelWindowMode",
].map((file) => `test/${file}.test.js`);

const result = spawnSync(
  process.execPath,
  ["--import", "tsx", "--test", "--test-concurrency=4", "--test-timeout=60000", ...files],
  { cwd: path.resolve(__dirname, ".."), stdio: "inherit" }
);
if (result.error) console.error(result.error.message);
process.exitCode = result.status ?? 1;
