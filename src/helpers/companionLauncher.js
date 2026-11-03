// Starts a companion program alongside the app (e.g. a voice orb that reacts to
// dictations). Configured by OPENWHISPR_COMPANION_COMMAND: the path to an
// executable, or to a .cmd/.bat script on Windows. The companion is detached and
// outlives the app; it is expected to guard against running twice itself, since
// it is launched again whenever the app is opened.

const fs = require("fs");
const path = require("path");
const { spawn } = require("child_process");

function buildCompanionSpawn(command, platform = process.platform) {
  if (typeof command !== "string") return null;
  const target = command.trim().replace(/^"(.*)"$/, "$1");
  if (!target) return null;
  const options = {
    cwd: path.dirname(target),
    detached: true,
    stdio: "ignore",
    windowsHide: true,
  };
  if (platform === "win32" && /\.(cmd|bat)$/i.test(target)) {
    return {
      file: process.env.ComSpec || "cmd.exe",
      args: ["/d", "/s", "/c", `""${target}""`],
      options: { ...options, windowsVerbatimArguments: true },
    };
  }
  return { file: target, args: [], options };
}

function launchCompanion({ env = process.env, logger = console, spawnFn = spawn, exists = fs.existsSync } = {}) {
  const plan = buildCompanionSpawn(env.OPENWHISPR_COMPANION_COMMAND);
  if (!plan) return false;
  const target = env.OPENWHISPR_COMPANION_COMMAND.trim().replace(/^"(.*)"$/, "$1");
  if (!exists(target)) {
    logger.warn?.("Companion not found", { target });
    return false;
  }
  try {
    const child = spawnFn(plan.file, plan.args, plan.options);
    child.on?.("error", (error) => logger.warn?.("Companion failed to start", { error: error.message }));
    child.unref?.();
    return true;
  } catch (error) {
    logger.warn?.("Companion failed to start", { error: error.message });
    return false;
  }
}

module.exports = { buildCompanionSpawn, launchCompanion };
