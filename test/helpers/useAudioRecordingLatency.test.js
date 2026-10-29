const test = require("node:test");
const assert = require("node:assert/strict");
const React = require("react");
const { createRoot } = require("react-dom/client");
const {
  createRendererServer,
  installBrowserGlobals,
  installHookDom,
} = require("../lib/rendererTestHarness");

async function mountRecording(t) {
  let root;
  t.after(async () => {
    if (root) await React.act(async () => root.unmount());
  });
  const handlers = {};
  const subscribe = (name) => (handler) => {
    handlers[name] = handler;
    return () => {};
  };
  const { window } = installBrowserGlobals(t, {
    window: {
      electronAPI: {
        onToggleDictation: subscribe("toggle"),
        onToggleVoiceAgent: subscribe("agent"),
        onToggleTranslation: subscribe("translation"),
        onStartDictation: subscribe("start"),
        onPrepareDictation: subscribe("prepare"),
        onCancelDictationPreparation: subscribe("cancelPrepare"),
        onStopDictation: subscribe("stop"),
      },
    },
  });
  const container = installHookDom(t);
  const vite = await createRendererServer(t, {
    cachePrefix: "dictation-no-frame-latency-",
    mockModules: {
      "/utils/visualFrame": "export const waitForVisualFrames = () => new Promise(() => {});",
      "/helpers/audioManager": `
        export default class AudioManager {
          constructor() { this.state = {}; this.calls = []; globalThis.__latencyManager = this; }
          getState() { return this.state; }
          getRecordingAudioLevel() { return null; }
          setCallbacks(callbacks) { this.callbacks = callbacks; }
          prepareMicCapture() { this.calls.push('prepare'); }
          cancelPreparedMicCapture() { this.calls.push('cancel-prepare'); }
          setVoiceAgentRequested(value) { this.voiceAgentRequested = value; }
          setAssistantSelectionContext() {}
          setTranslationRequested(value) { this.translationRequested = value; }
          isSttConfigStale() { return false; }
          shouldUseStreaming() { return false; }
          async startRecording() {
            this.calls.push('start'); this.state = { isRecording: true };
            this.callbacks.onStateChange(this.state); return true;
          }
          stopRecording() {
            this.calls.push('stop'); this.state = { isRecording: false };
            this.callbacks.onStateChange(this.state); return true;
          }
          cleanup() {}
        }
      `,
    },
  });
  t.after(() => {
    delete globalThis.__latencyManager;
  });
  const { useAudioRecording } = await vite.ssrLoadModule("/hooks/useAudioRecording.js");
  let api;
  const toast = () => {};
  function Harness() {
    api = useAudioRecording(toast);
    return null;
  }
  root = createRoot(container);
  await React.act(async () => root.render(React.createElement(Harness)));
  return {
    get api() {
      return api;
    },
    manager: globalThis.__latencyManager,
    handlers,
    window,
  };
}

test("recording start, stop and mouse preparation never wait for a painting window", async (t) => {
  const fixture = await mountRecording(t);
  let starting;
  await React.act(async () => {
    starting = fixture.api.startRecording();
    await new Promise(setImmediate);
  });
  assert.deepEqual(
    fixture.manager.calls,
    ["prepare", "start"],
    "open the microphone even when compositor frames never arrive"
  );
  assert.equal(await starting, true);

  let stopping;
  await React.act(async () => {
    stopping = fixture.api.stopRecording();
    await new Promise(setImmediate);
  });
  assert.equal(
    fixture.manager.calls.at(-1),
    "stop",
    "release the microphone without waiting for an animation"
  );
  assert.equal(await stopping, true);

  fixture.manager.calls.length = 0;
  await React.act(async () => {
    void fixture.handlers.prepare({ inputKind: "dictation" });
    await new Promise(setImmediate);
  });
  assert.deepEqual(fixture.manager.calls, ["prepare"]);
});

test("cancelled preparation cannot start capture after the target lookup finishes", async (t) => {
  const fixture = await mountRecording(t);
  let resolveTarget;
  fixture.window.electronAPI.captureDictationTarget = () =>
    new Promise((resolve) => {
      resolveTarget = resolve;
    });
  let starting;
  await React.act(async () => {
    starting = fixture.api.startRecording();
    await new Promise(setImmediate);
  });
  assert.equal(typeof resolveTarget, "function");
  await React.act(async () => {
    fixture.handlers.cancelPrepare();
    resolveTarget();
    assert.equal(await starting, false);
  });
  assert.equal(fixture.manager.calls.includes("start"), false);
  assert.equal(
    fixture.manager.calls.includes("cancel-prepare"),
    true,
    JSON.stringify(fixture.manager.calls)
  );
});
