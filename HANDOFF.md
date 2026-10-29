# Windows dictation handoff (2026-10-28, updated after delivery pass)

Full delivery notes, launch, rollback, validation and limitations:
**`docs/windows-dictation-README.md`**. This file only records state for the next
person picking the work up.

## Intent and authorization (unchanged)
Separate dedicated Windows dictation-only app derived from OpenWhispr; preserve the
original app, its data, licenses and models. Fully local transcription and cleanup;
compact ready/capturing/processing/result/error UI with asynchronous cues; mouse or
keyboard activation, hold/toggle; vocabulary with preferred spellings and spoken
aliases; learning only from confirmed corrections; paste only into a verified
writable, non-password field, else clipboard and copyable preview. Never claim
unvalidated behavior.

## State
- Latest authorized microphone preference: **60-second warm hold** is now
  enabled in the running profile (Preferences -> Keep Microphone Warm ->
  1 minute), verified in the app UI after the user explicitly selected this
  tradeoff. This supersedes earlier notes saying warm hold remains off. The
  first capture after a longer idle still opens the device cold; between nearby
  recordings the mic stays open without recording/transcribing idle speech.
- User's latest preference is English-only output. The running derivative's
  saved settings now select `nemotron-speech-streaming-en-0.6b` and
  `DICTATION_LANGUAGE=en-US`, changed through the app UI and verified in `.env`.
  Its four model files were copied from the existing English benchmark folder
  into the shared cache and SHA-256 verified. The multilingual models remain.
  This profile preference overrides the multilingual fresh-install default;
  no rebuild was needed. Actual speech quality awaits the user's next test.
- Checkout `D:\Teacher\OpenWhisprDictation`, upstream `66e03c10…`, branch main, all
  work uncommitted (`git status --short`). Native binaries in `resources/bin` are
  git-ignored and were compiled/copied locally (key listener with `--swallow`,
  fast-paste with `--safe-paste`, `llama-vulkan/` runtime copied from the installed
  app, same llama.cpp build 9763). Do not overwrite them with upstream prebuilts.
- Artifact: `dist\win-unpacked\OpenWhispr Dictation.exe` (unsigned, 808 MB).
  Rebuild: `npm run build:renderer` then
  `npx electron-builder --win --dir --config electron-builder.unsigned-win.json --publish never`
  (unset `ELECTRON_RUN_AS_NODE` in the shell first; the Claude shell sets it).
- Derivative data: `%APPDATA%\OpenWhisprDictation` (created by the smoke runs; the
  test-only hotkey and debug log level were removed from its `.env`; it already
  holds the seeded Vulkan runtime and `LLAMA_VULKAN_ENABLED=true`).
- Shared cache `%USERPROFILE%\.cache\openwhispr`: nothing deleted or moved.
  `parakeet-models\nemotron-3.5-asr-streaming-0.6b` was added (the original app
  will list it). Gemma, the Gemma MTP draft and the Ollama Qwen blob are untouched.
  `benchmark-models/` (≈2 GB of pinned model archives and extracted models, plus
  `bench.js`/`live.js`) is untracked and only needed for re-running the
  transcription benchmarks; it may be deleted.
- Original OpenWhispr (installed, `C:\Users\Sanket\AppData\Local\Programs\OpenWhispr`)
  was running throughout and never stopped. It hooks `Control+Super`, so the
  derivative's default hotkey is `Control+Alt+Space`.

## Done in this pass
1. Settings IPC can no longer start meeting detectors; stt-config fetch removed;
   smoke runs (dev and packaged) are free of errors, detectors and cloud calls.
2. Nemotron 3.5 streaming model is the default and lives in the shared cache
   (added, not moved). Streaming UI/local server were validated only at startup.
3. Spoken aliases (snippets, `src/utils/vocabularyAliases.ts`, Dictionary view
   "heard as…") and confirmed corrections (home screen "Fix spelling" → proposals →
   "Add selected" → Undo toast). Tests in `test/utils/vocabularyAliases.test.js`.
4. Windows mouse side buttons: hook, tap/hold routing, default swallow of the
   button's Back/Forward action with a Settings toggle (pass-through), tests in
   `test/helpers/windowsKeyManagerMouse.test.js`. Validator accepts win32.
5. Safe paste: target-unverified path localized, no fallback injection.
6. Cleanup model section restored in Settings (dictation cleanup tab only);
   bundled Vulkan llama runtime seeded on first launch (`bundledGpuPacks.js`).
7. Typecheck, renderer build, 273 focused tests pass; packaged build built and
   smoke-launched. Cleanup latency measured (0.2–1.4 s warm on the RTX 4070).
8. Hardcoded UI strings moved to `src/locales/en/translation.json`
   (`dictationApp.*`); other locales fall back to English.
9. Continuation fixed the renderer guard's CommonJS/ESM mismatch
   (`localOnlyDictation.mjs`), which caused 259 full-suite failures. Added the
   bounded `npm run test:dictation` command and a real renderer integration test
   for local decode/cleanup/failure preservation and zero cloud uploads. Startup
   test extraction now handles CRLF. Final ASAR source parity: 605 files, zero
   mismatches; final packaged startup warms both models without app-level errors
   or warnings. Full-suite evidence and remaining failures are in
   `docs/validation/windows-dictation-tests.md`.
10. Full diagnostic rerun completed: 9,034 tests, 8,384 passes, 107 failures,
    542 skips and one todo. Three stalled cloud workers were stopped, so this
    is not a clean full-suite pass. Exact failure names, error excerpts and
    classifications are in `docs/validation/windows-dictation-full-suite-failures.md`.

## Still open (needs the user at the machine, see README "Not validated")
- Latest latency repair: removed compositor waits from preparation/start/stop,
  including cancellation protection during target lookup. 273 supported tests
  and 27 affected hook tests pass. Keep model loaded was enabled, while mic warm
  hold remains off. The rebuilt app is installed at the usual path; rollback is
  `dist/win-unpacked-before-latency-20261028`. Warm service measurements and test
  limits: `docs/validation/windows-dictation-latency.md`. Physical latency is
  awaiting the user's next trial.
- Real microphone capture, device changes, sleep/resume, first-word clipping.
- Physical Mouse Button 4/5 hold/toggle/rebind and the pass-through toggle.
- Safe paste against password fields, changed focus, elevated windows.
- Hindi/name recognition quality; English-vs-multilingual model choice.
- Offline run with the network actually disconnected.
- End-to-end stop-to-paste timing with a microphone.
- Removing unused dependencies from the bundle (hidden/blocked, not removed).
