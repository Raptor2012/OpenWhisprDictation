const test = require("node:test");
const assert = require("node:assert/strict");
const {
  localDictationAllowed,
  localCleanupAllowed,
} = require("../../src/helpers/localOnlyDictation.mjs");
test("dictation rejects cloud and managed transcription", () => {
  assert.equal(localDictationAllowed({ useLocalWhisper: true }, null), true);
  assert.equal(localDictationAllowed({ useLocalWhisper: false }, null), false);
  assert.equal(localDictationAllowed({ useLocalWhisper: true }, { kind: "managed" }), false);
});
test("cleanup permits only local model without agent or translation", () => {
  assert.equal(localCleanupAllowed({ mode: "local" }, false, false), true);
  assert.equal(localCleanupAllowed({ mode: "providers" }, false, false), false);
  assert.equal(localCleanupAllowed({ mode: "local" }, true, false), false);
  assert.equal(localCleanupAllowed({ mode: "local" }, false, true), false);
});
