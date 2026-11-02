import test from "node:test";
import assert from "node:assert/strict";
import { fastCleanup, isFastCleanupEligible } from "../../src/utils/fastCleanup.js";

test("short plain dictations are eligible", () => {
  assert.equal(isFastCleanupEligible("continue the work that you were doing"), true);
  assert.equal(isFastCleanupEligible("uh can you fix it"), true);
});

test("long, numeric or risky dictations go to the model", () => {
  assert.equal(isFastCleanupEligible("one two three four five six seven eight nine"), false);
  assert.equal(isFastCleanupEligible("send it friday no wait monday"), false);
  assert.equal(isFastCleanupEligible("spawn some sub regions"), false);
  assert.equal(isFastCleanupEligible("tap the org again"), false);
  assert.equal(isFastCleanupEligible("set it to 5"), false);
  assert.equal(isFastCleanupEligible(""), false);
});

test("fillers and stutters go, casing and end punctuation are added", () => {
  assert.equal(
    fastCleanup("uh continue the the work that you were doing"),
    "Continue the work that you were doing."
  );
  assert.equal(fastCleanup("um can you fix it"), "Can you fix it?");
  assert.equal(fastCleanup("Looks good, ship it."), "Looks good, ship it.");
});

test("filler-only input becomes empty", () => {
  assert.equal(fastCleanup("uh um"), "");
});
