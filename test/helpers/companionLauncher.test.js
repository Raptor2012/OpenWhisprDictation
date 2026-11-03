const test = require("node:test");
const assert = require("node:assert/strict");
const { buildCompanionSpawn, launchCompanion } = require("../../src/helpers/companionLauncher");

test("no command configured launches nothing", () => {
  assert.equal(buildCompanionSpawn(undefined), null);
  assert.equal(buildCompanionSpawn("   "), null);
  assert.equal(launchCompanion({ env: {}, spawnFn: () => assert.fail("spawned") }), false);
});

test("a Windows script runs through cmd with its path quoted", () => {
  const plan = buildCompanionSpawn('"D:\\Tools\\Start My Orb.cmd"', "win32");
  assert.deepEqual(plan.args, ["/d", "/s", "/c", '""D:\\Tools\\Start My Orb.cmd""']);
  assert.equal(plan.options.windowsVerbatimArguments, true);
  assert.equal(plan.options.detached, true);
  assert.equal(plan.options.windowsHide, true);
});

test("an executable is spawned directly from its own folder", () => {
  const plan = buildCompanionSpawn("/opt/orb/orb", "linux");
  assert.equal(plan.file, "/opt/orb/orb");
  assert.deepEqual(plan.args, []);
  assert.equal(plan.options.cwd, "/opt/orb");
});

test("a missing companion is skipped, a present one is spawned and released", () => {
  const env = { OPENWHISPR_COMPANION_COMMAND: "/opt/orb/orb" };
  const logger = { warn() {} };
  assert.equal(launchCompanion({ env, logger, exists: () => false, spawnFn: () => assert.fail() }), false);
  let unrefd = false;
  const ok = launchCompanion({
    env,
    logger,
    exists: () => true,
    spawnFn: () => ({ on() {}, unref: () => (unrefd = true) }),
  });
  assert.equal(ok, true);
  assert.equal(unrefd, true);
});
