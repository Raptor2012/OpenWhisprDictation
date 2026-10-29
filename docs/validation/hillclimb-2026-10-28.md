# Speed + accuracy hill-climb — state for resume (2026-10-28)

Goal from user: fastest response with best cleanup. Hardware is not a constraint; GPU is fine.

## Benchmark assets (all untracked, reusable)
- `benchmark-audio/*.wav`: the user's 37 real dictations (16 kHz mono, converted from
  `%APPDATA%\OpenWhisprDictation\audio\*.webm`). `db-baseline.json` = app transcripts.
- `benchmark-scripts/asr-compare.js <label> <modelId> <modelDir> [online|offline]`
  → `benchmark-audio/result-<label>.json`. Env `OPENWHISPR_ASR_THREADS`, `OPENWHISPR_ASR_EXTRA_ARGS`
  (both knobs were added to `src/helpers/parakeetWsServer.js`, default behavior unchanged).
- `benchmark-scripts/asr-split.js` (parallel split decode test).
- `benchmark-scripts/cleanup-compare.py <label> <gguf> [draft]` → `benchmark-audio/cleanup-<label>.json`.
  Env `BENCH_LLAMA` (binary), `BENCH_THREADS`.
- Models: `benchmark-models/sherpa-onnx-nemo-parakeet-unified-en-0.6b-int8-non-streaming`,
  Cohere transcribe (downloaded + extracted, NOT yet benchmarked), `benchmark-models/llm/*.gguf`
  (Qwen3.5 0.8B/2B, LFM2.5 1.2B, LFM2 2.6B, Gemma 4 E2B).

## Speech-to-text results (CPU, i9-14900HX)
| Model | ms per audio second | Accuracy on user clips |
| --- | --- | --- |
| Parakeet Unified EN, 8 threads | ~97 | Best (thread, briefing call, call with Eva, deploy) |
| Parakeet Unified EN, 4 / 6 / 10 / 12 threads | 104 / 119 / 112 / 157 | same text |
| Parakeet TDT v3, 8 threads | ~105 | Worse ("trade", "beeping card", "quality paper") |
| Nemotron EN streaming 560 ms (current profile) | live finish ~250 ms | Worst ("First time I took", "quite harsh") |
- 8 threads is the sweet spot (P-cores). Splitting a clip into 2 parallel halves: 28% faster but
  every text degraded → rejected. Beam search / hotwords: no clear gain, adds deletions → rejected
  (hotwords need `--bpe-vocab`; synthesized one at `benchmark-audio/bpe.vocab` works).
- Mic level is low (peaks −18 to −25 dBFS, RMS −35 to −45). Untested: gain-normalize before decode.
- GPU sherpa build exists (`sherpa-onnx-v1.13.8-cuda-12.x-...-win-x64-cuda.tar.bz2`), not tried;
  int8 models may fall back to CPU ops on CUDA.

## Cleanup results (GPU Vulkan, isolated)
| Model | GPU median / max | CPU(8t) median / max | Quality |
| --- | --- | --- | --- |
| Gemma 4 E4B QAT + MTP draft (current) | 191 / 447 ms | 1137 / 2978 ms | Best; only one doing self-corrections |
| Gemma 4 E2B | 225 / 507 | 888 / 2140 | misses corrections |
| LFM2 2.6B | 165 / 426 | 770 / 1839 | changes meaning — unsafe |
| Qwen3.5 2B | 210 / 391 | – | drops words |
| Qwen3.5 0.8B | 207 / 384 | – | barely cleans |
| LFM2.5 1.2B | 105 / 212 | – | leaks system prompt — unsafe |
Decision: keep Gemma E4B on GPU.

## Done 2026-10-29
- Unified EN copied into `%USERPROFILE%\.cache\openwhispr\parakeet-models\parakeet-unified-en-0.6b` (added only).
- Defaults: `main.js` `PARAKEET_MODEL ||= "parakeet-unified-en-0.6b"` and `OPENWHISPR_ASR_THREADS ||= "8"` on
  16+ core CPUs; `settingsStore.ts` default plus one-time migration (`_dictationUnifiedEnMigrated`) off the
  two Nemotron streaming models. Tests: `test/helpers/dictationAsrDefault.test.js` (4 pass).
- Typecheck, renderer build, `npm run test:dictation` (273 pass) green. Packaged via
  `electron-builder.next-win.json` (output `dist-next`), swapped in: new build at `dist\win-unpacked`,
  rollback at `dist\win-unpacked-before-unified-20261029`. Relaunched and verified: sherpa offline server on
  Unified EN with `--num-threads=8`, Gemma E4B on Vulkan with MTP draft, MouseButton5 listener; `.env`
  migrated to `PARAKEET_MODEL=parakeet-unified-en-0.6b`.
- Rejected: peak normalisation (11/37 texts changed, mixed, no clear gain); Cohere Transcribe (cleaner raw
  text but ~260 ms per audio second vs 97 ms; measured while another decode ran, so partly inflated).

## Next hill-climb ideas
0. DONE, rejected: CUDA sherpa build + NVIDIA CUDA 12.9 runtime/cuDNN 9.27 DLLs (from pip wheels, copied
   next to the binary under `benchmark-models/sherpa-cuda`, nothing installed system-wide). Unified EN int8 with
   `--provider=cuda`: RTF 0.169 vs 0.098 on CPU 8 threads, startup 12.9 s. int8 ops run poorly on CUDA.
   Only worth revisiting with an fp16/fp32 export of the model.
1. (superseded) CUDA sherpa build (`sherpa-onnx-v1.13.8-cuda-12.x-cudnn-9.x-onnxruntime1.28.2-win-x64-cuda.tar.bz2`) with
   Unified EN: could cut the ~0.5 s decode of a 5 s clip. Check int8 ops don't fall back to CPU.
2. Re-time Cohere alone (no concurrent load) to confirm the gap.
3. Measure real stop-to-paste in the app log (`Recording start timing` / processing timings) after the user's
   next dictations, to see whether decode or cleanup now dominates.
