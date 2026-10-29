const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const { seedBundledGpuPack, resolveBundledPackDir } = require("../../src/helpers/bundledGpuPacks");

function makeManager(binRoot) {
  const binDir = path.join(binRoot, "llama-vulkan");
  return {
    config: { name: "Vulkan llama" },
    binDir,
    _getAssetConfig: () => ({ outputName: "llama-server-vulkan.exe" }),
    isDownloaded() {
      return fs.existsSync(path.join(binDir, "llama-server-vulkan.exe"));
    },
  };
}

test("a bundled pack is copied into the user pack directory once", (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "gpu-pack-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const bundled = path.join(root, "resources", "bin", "llama-vulkan");
  fs.mkdirSync(bundled, { recursive: true });
  fs.writeFileSync(path.join(bundled, "llama-server-vulkan.exe"), "exe");
  fs.writeFileSync(path.join(bundled, "ggml-vulkan.dll"), "dll");
  const manager = makeManager(path.join(root, "userData", "bin"));

  assert.equal(seedBundledGpuPack({ manager, bundledDir: bundled }), "seeded");
  assert.deepEqual(fs.readdirSync(manager.binDir).sort(), ["ggml-vulkan.dll", "llama-server-vulkan.exe"]);
  assert.deepEqual(fs.readdirSync(path.join(root, "userData", "bin")), ["llama-vulkan"]);
  // Second launch: already present, nothing copied again.
  assert.equal(seedBundledGpuPack({ manager, bundledDir: bundled }), "present");
});

test("no bundled pack or a bundle without the binary leaves the user directory alone", (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "gpu-pack-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const manager = makeManager(path.join(root, "userData", "bin"));
  assert.equal(seedBundledGpuPack({ manager, bundledDir: null }), "unavailable");
  const emptyBundle = path.join(root, "empty");
  fs.mkdirSync(emptyBundle);
  assert.equal(seedBundledGpuPack({ manager, bundledDir: emptyBundle }), "unavailable");
  assert.equal(fs.existsSync(path.join(root, "userData")), false);
});

test("resolveBundledPackDir prefers the packaged resources directory", (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "gpu-pack-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  fs.mkdirSync(path.join(root, "bin", "llama-vulkan"), { recursive: true });
  assert.equal(
    resolveBundledPackDir("llama-vulkan", { resourcesPath: root }),
    path.join(root, "bin", "llama-vulkan")
  );
  assert.equal(resolveBundledPackDir("no-such-pack", { resourcesPath: root }), null);
});
