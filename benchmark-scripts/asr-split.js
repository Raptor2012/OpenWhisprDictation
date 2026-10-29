// Does splitting a clip at a pause and decoding both halves concurrently cut
// the wall time of the final decode without hurting the text?
//
//   node benchmark-scripts/asr-split.js <modelDir> [minSecondsToSplit=5]
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
const { splitAtPauses } = require(path.join(root, "src/helpers/parakeetSegmentation"));
const audioDir = path.join(root, "benchmark-audio");

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
  const [modelDir, minSplit = "5"] = process.argv.slice(2);
  const files = fs
    .readdirSync(audioDir)
    .filter((f) => f.endsWith(".wav"))
    .sort((a, b) => Number(a.match(/-(\d+)\.wav$/)[1]) - Number(b.match(/-(\d+)\.wav$/)[1]));
  const server = new Server();
  await server.start("parakeet-tdt-0.6b-v3", modelDir, "offline", "en");
  const rows = [];
  try {
    const warm = readWav(path.join(audioDir, files[0]));
    await server.transcribe(warm.samples, 16000);
    for (const file of files) {
      const clip = Number(file.match(/-(\d+)\.wav$/)[1]);
      const { samples, seconds } = readWav(path.join(audioDir, file));
      if (seconds < Number(minSplit) || seconds > 30) continue;
      let t = performance.now();
      const whole = await server.transcribe(samples, 16000);
      const wholeMs = Math.round(performance.now() - t);
      const half = Math.ceil(seconds / 2);
      const segments = splitAtPauses(samples, { sampleRate: 16000, maxSegmentSeconds: half });
      t = performance.now();
      const parts = await Promise.all(segments.map((s) => server.transcribe(s, 16000)));
      const splitMs = Math.round(performance.now() - t);
      const splitText = parts.map((p) => p.text).filter(Boolean).join(" ");
      rows.push({ clip, seconds, wholeMs, splitMs, segments: segments.length, whole: whole.text, split: splitText });
      console.log(`#${clip} ${seconds.toFixed(1)}s whole ${wholeMs} ms | split(${segments.length}) ${splitMs} ms | same=${whole.text === splitText}`);
      if (whole.text !== splitText) console.log(`   W: ${whole.text}\n   S: ${splitText}`);
    }
  } finally {
    await server.stop();
  }
  fs.writeFileSync(path.join(audioDir, "result-split.json"), JSON.stringify(rows, null, 1));
  const w = rows.reduce((a, r) => a + r.wholeMs, 0);
  const s = rows.reduce((a, r) => a + r.splitMs, 0);
  console.log(`total whole ${w} ms vs split ${s} ms (${Math.round((1 - s / w) * 100)}% faster), ${rows.filter((r) => r.whole !== r.split).length}/${rows.length} texts differ`);
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
