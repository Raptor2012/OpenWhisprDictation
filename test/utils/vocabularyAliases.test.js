const test = require("node:test");
const assert = require("node:assert/strict");

const {
  aliasesForWord,
  aliasExists,
  addAlias,
  removeAlias,
  retargetAliases,
  removeWordAliases,
} = require("../../src/utils/vocabularyAliases.ts");
const { expandSnippets } = require("../../src/utils/snippets.ts");
const { extractCorrectionPairs } = require("../../src/utils/correctionLearner.js");

test("aliases are the snippets that replace with the word, case-insensitively", () => {
  const snippets = [
    { trigger: "sunk it", replacement: "Sanket" },
    { trigger: "sanket das", replacement: "Sanket Das" },
    { trigger: "sankit", replacement: "sanket" },
  ];
  assert.deepEqual(aliasesForWord("Sanket", snippets), ["sunk it", "sankit"]);
  assert.deepEqual(aliasesForWord("nobody", snippets), []);
  assert.deepEqual(aliasesForWord("  ", snippets), []);
});

test("addAlias rejects empty, self and duplicate triggers", () => {
  const base = [{ trigger: "sunk it", replacement: "Sanket" }];
  assert.equal(addAlias(base, "", "Sanket"), base);
  assert.equal(addAlias(base, "sanket", "Sanket"), base);
  assert.equal(addAlias(base, "Sunk It", "Sanket"), base);
  assert.equal(aliasExists("SUNK IT", base), true);
  const next = addAlias(base, " sankit ", "Sanket");
  assert.deepEqual(next, [...base, { trigger: "sankit", replacement: "Sanket" }]);
});

test("an alias replaces the misheard whole word in a transcript", () => {
  const snippets = addAlias([], "sunk it", "Sanket");
  assert.equal(expandSnippets("Tell sunk it to call me", snippets), "Tell Sanket to call me");
  assert.equal(expandSnippets("Tell Sunk It.", snippets), "Tell Sanket.");
  assert.equal(expandSnippets("debunk it", snippets), "debunk it");
});

test("renaming or removing a word keeps its aliases consistent", () => {
  const snippets = [
    { trigger: "sunk it", replacement: "Sanket" },
    { trigger: "brb", replacement: "be right back" },
  ];
  assert.deepEqual(retargetAliases(snippets, "sanket", "Sanket Das"), [
    { trigger: "sunk it", replacement: "Sanket Das" },
    { trigger: "brb", replacement: "be right back" },
  ]);
  assert.deepEqual(removeWordAliases(snippets, "SANKET"), [
    { trigger: "brb", replacement: "be right back" },
  ]);
  assert.deepEqual(removeAlias(snippets, "Sunk it"), [
    { trigger: "brb", replacement: "be right back" },
  ]);
});

test("correction pairs keep what was heard beside the corrected spelling", () => {
  const pairs = extractCorrectionPairs(
    "Please ask Shunade about the Kubernetes rollout",
    "Please ask Sinead about the Kubernetes rollout",
    []
  );
  assert.deepEqual(pairs, [{ heard: "Shunade", corrected: "Sinead" }]);
  // Words already in the dictionary are not proposed again.
  assert.deepEqual(
    extractCorrectionPairs("ask Shunade now", "ask Sinead now", ["sinead"]),
    []
  );
});
