// Decode every WAV in benchmark-audio/ with one sherpa-onnx model through the
// app's own ParakeetWsServer wrapper, and write timings + text to a JSON file.
//
//   node benchmark-scripts/asr-compare.js <label> <modelId> <modelDir> [online|offline] [language]
//
// Env: OPENWHISPR_ASR_THREADS overrides the intra-op thread cap.
const fs = require("fs");
const path = require("path");
const Module = require("module");
const os = require("os");

const original = Module._load;
Module._load = function (request, parent, isMain) {
  if (request === "./debugLogger") return { debug() {}, info() {}, warn() {}, error() {}, log() {} };
  if (request === "./safeTempDir") return { getSafeTempDir: () => os.tmpdir() };
  if (request === "./sidecarPidFile") return { write() {}, clear() {} };
  return original.apply(this, arguments);
};

const root = path.join(__dirname, "..");
const Server = require(path.join(root, "src/helpers/parakeetWsServer"));
const audioDir = process.env.BENCH_AUDIO_DIR || path.join(root, "benchmark-audio");

function readWav(file) {
  const wav = fs.readFileSync(file);
  let p = 12;
  let pcm = null;
  while (p + 8 <= wav.length) {
    const size = wav.readUInt32LE(p + 4);
    if (wav.toString("ascii", p, p + 4) === "data") {
      pcm = wav.subarray(p + 8, p + 8 + size);
      break;
    }
    p += 8 + size + (size % 2);
  }
  const samples = Buffer.alloc(pcm.length * 2);
  for (let i = 0; i < pcm.length / 2; i++) samples.writeFloatLE(pcm.readInt16LE(i * 2) / 32768, i * 4);
  return { samples, seconds: pcm.length / 32000 };
}

(async () => {
  const [label, modelId, modelDir, runtime = "offline", language = "en"] = process.argv.slice(2);
  if (!label || !modelId || !modelDir) {
    console.error("usage: asr-compare.js <label> <modelId> <modelDir> [online|offline] [language]");
    process.exit(1);
  }
  const files = fs
    .readdirSync(audioDir)
    .filter((f) => f.endsWith(".wav"))
    .sort((a, b) => Number(a.match(/-(\d+)\.wav$/)[1]) - Number(b.match(/-(\d+)\.wav$/)[1]));
  const server = new Server();
  // Benchmark another sherpa build (e.g. the CUDA one) without touching resources/bin.
  if (process.env.BENCH_SHERPA_BIN) server.getWsBinaryPath = () => process.env.BENCH_SHERPA_BIN;
  const t0 = performance.now();
  await server.start(modelId, modelDir, runtime, language);
  const startupMs = performance.now() - t0;
  const results = [];
  try {
    // Warm-up decode so the first measured clip doesn't pay for lazy init.
    const warm = readWav(path.join(audioDir, files[0]));
    if (runtime === "online") {
      const stream = server.createOnlineStream({ onUpdate() {}, onError() {} });
      stream.sendFloat32(warm.samples);
      await stream.finish();
    } else {
      await server.transcribe(warm.samples, 16000);
    }
    for (const file of files) {
      const clip = Number(file.match(/-(\d+)\.wav$/)[1]);
      const { samples, seconds } = readWav(path.join(audioDir, file));
      const start = performance.now();
      let text;
      let extra = {};
      if (runtime === "online") {
        // Push the audio as fast as the socket takes it; "finishMs" then
        // measures the decode of the tail after the last audio, which is the
        // part a user waits for after releasing the key.
        const stream = server.createOnlineStream({ onUpdate() {}, onError() {} });
        const chunk = 16000 * 4; // 1 s of float32 samples
        for (let i = 0; i < samples.length; i += chunk) stream.sendFloat32(samples.subarray(i, i + chunk));
        const sent = performance.now();
        const result = await stream.finish();
        text = result?.text ?? "";
        extra = { finishMs: Math.round(performance.now() - sent), truncated: !!result?.truncated };
      } else {
        const result = await server.transcribe(samples, 16000);
        text = typeof result === "string" ? result : (result?.text ?? "");
      }
      const ms = Math.round(performance.now() - start);
      results.push({ clip, seconds: Number(seconds.toFixed(2)), ms, rtf: Number((ms / 1000 / seconds).toFixed(3)), text, ...extra });
      process.stderr.write(`${label} clip ${clip}: ${ms} ms (${seconds.toFixed(1)} s)\n`);
    }
  } finally {
    await server.stop();
  }
  const out = {
    label,
    modelId,
    runtime,
    threads: process.env.OPENWHISPR_ASR_THREADS || "default",
    startupMs: Math.round(startupMs),
    results,
  };
  const outFile = path.join(audioDir, `result-${label}.json`);
  fs.writeFileSync(outFile, JSON.stringify(out, null, 1));
  const total = results.reduce((a, r) => a + r.ms, 0);
  const audio = results.reduce((a, r) => a + r.seconds, 0);
  console.log(`${label}: ${results.length} clips, ${audio.toFixed(1)} s audio, ${total} ms decode, RTF ${(total / 1000 / audio).toFixed(3)}, startup ${Math.round(startupMs)} ms -> ${outFile}`);
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
