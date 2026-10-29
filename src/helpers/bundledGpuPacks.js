const fs = require("fs");
const path = require("path");

/**
 * This local-only build cannot download GPU runtimes at run time, so a GPU
 * pack may ship inside the app bundle. On first launch it is copied into the
 * pack's normal `userData/bin/<dirName>/` directory, after which the existing
 * GpuBinaryManager logic (status, delete, failure handling) applies unchanged.
 *
 * The copy is staged beside the final directory and swapped in with a single
 * rename, so an interrupted copy never leaves a half-installed pack that
 * isDownloaded() would report as present.
 */
function resolveBundledPackDir(dirName, { resourcesPath = process.resourcesPath } = {}) {
  const candidates = [];
  if (resourcesPath) candidates.push(path.join(resourcesPath, "bin", dirName));
  candidates.push(path.join(__dirname, "..", "..", "resources", "bin", dirName));
  for (const candidate of candidates) {
    try {
      if (fs.statSync(candidate).isDirectory()) return candidate;
    } catch {}
  }
  return null;
}

/**
 * @returns {"present" | "seeded" | "unavailable" | "failed"}
 */
function seedBundledGpuPack({ manager, bundledDir, logger }) {
  if (manager.isDownloaded()) return "present";
  if (!bundledDir) return "unavailable";
  const assetConfig = manager._getAssetConfig?.();
  if (!assetConfig) return "unavailable";
  if (!fs.existsSync(path.join(bundledDir, assetConfig.outputName))) return "unavailable";

  const target = manager.binDir;
  const staging = `${target}.seed-${process.pid}`;
  try {
    fs.rmSync(staging, { recursive: true, force: true });
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.cpSync(bundledDir, staging, { recursive: true });
    // A pack left behind by a previous install (binary missing or incomplete)
    // is replaced rather than merged.
    fs.rmSync(target, { recursive: true, force: true });
    fs.renameSync(staging, target);
  } catch (error) {
    logger?.warn?.("Bundled GPU pack could not be installed", {
      pack: manager.config?.name,
      error: error?.message,
    });
    try {
      fs.rmSync(staging, { recursive: true, force: true });
    } catch {}
    return "failed";
  }
  return manager.isDownloaded() ? "seeded" : "failed";
}

module.exports = { resolveBundledPackDir, seedBundledGpuPack };
