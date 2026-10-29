const test = require("node:test");
const assert = require("node:assert/strict");
const EventEmitter = require("node:events");
const path = require("node:path");

// The manager spawns one hook process per watched key. Stub child_process so
// the test can read the spawn arguments without starting any binary.
const spawnCalls = [];
const childProcess = require("node:child_process");
const originalSpawn = childProcess.spawn;

function fakeChild() {
  const child = new EventEmitter();
  child.stdout = new EventEmitter();
  child.stdout.setEncoding = () => {};
  child.stderr = new EventEmitter();
  child.stderr.setEncoding = () => {};
  child.kill = () => {
    child.killed = true;
  };
  return child;
}

function loadManager() {
  childProcess.spawn = (binary, args, options) => {
    spawnCalls.push({ binary, args, options });
    return fakeChild();
  };
  const modulePath = path.join(__dirname, "../../src/helpers/windowsKeyManager.js");
  delete require.cache[require.resolve(modulePath)];
  const WindowsKeyManager = require(modulePath);
  const manager = new WindowsKeyManager();
  manager.isSupported = true;
  manager.resolveListenerBinary = () => "listener.exe";
  return manager;
}

test.afterEach(() => {
  childProcess.spawn = originalSpawn;
  spawnCalls.length = 0;
});

test("a bound side button is swallowed by default and keyboard keys are not", () => {
  const manager = loadManager();
  manager.setKeys(["MouseButton4", "Control+Alt+Space"]);
  assert.deepEqual(
    spawnCalls.map((call) => call.args),
    [
      ["MouseButton4", "--swallow"],
      ["Control+Alt+Space"],
    ]
  );
});

test("turning pass-through on restarts only the mouse listener without the flag", () => {
  const manager = loadManager();
  manager.setKeys(["MouseButton5", "F9"], { swallowMouseButtons: true });
  const mouseChild = manager.listeners.get("MouseButton5");
  const keyChild = manager.listeners.get("F9");
  spawnCalls.length = 0;

  manager.setKeys(["MouseButton5", "F9"], { swallowMouseButtons: false });
  assert.equal(mouseChild.killed, true);
  assert.equal(keyChild.killed, undefined);
  assert.deepEqual(
    spawnCalls.map((call) => call.args),
    [["MouseButton5"]]
  );

  // Same option again: nothing restarts.
  spawnCalls.length = 0;
  manager.setKeys(["MouseButton5", "F9"], { swallowMouseButtons: false });
  assert.deepEqual(spawnCalls, []);
});

test("mouse events route by key like keyboard events", () => {
  const manager = loadManager();
  const seen = [];
  manager.on("key-down", (key) => seen.push(`down:${key}`));
  manager.on("key-up", (key) => seen.push(`up:${key}`));
  manager.setKeys(["MouseButton4"]);
  manager.handleOutputLine("KEY_DOWN", "MouseButton4");
  manager.handleOutputLine("KEY_UP", "MouseButton4");
  assert.deepEqual(seen, ["down:MouseButton4", "up:MouseButton4"]);
});
