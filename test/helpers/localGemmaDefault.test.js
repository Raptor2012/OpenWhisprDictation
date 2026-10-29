const test = require('node:test');
const assert = require('node:assert/strict');
const { createRendererServer, installBrowserGlobals } = require('../lib/rendererTestHarness');
test('fresh settings resolve local Gemma cleanup', async t => {
  installBrowserGlobals(t);
  const vite = await createRendererServer(t, { cachePrefix: 'local-gemma-default-' });
  const { useSettingsStore, selectResolvedLLMConfig } = await vite.ssrLoadModule('/stores/settingsStore.ts');
  const state = useSettingsStore.getState();
  assert.equal(state.transcriptionMode, 'local');
  assert.equal(state.useLocalWhisper, true);
  assert.equal(state.localTranscriptionProvider, 'nvidia');
  const config = selectResolvedLLMConfig(state, 'dictationCleanup');
  assert.equal(config.mode, 'local');
  assert.equal(config.provider, 'gemma');
  assert.equal(config.model, 'gemma-4-e4b-it-qat-q4_0');
});
