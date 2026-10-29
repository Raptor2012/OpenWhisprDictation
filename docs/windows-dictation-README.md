# OpenWhispr Dictation (Windows, local-only) — delivery notes

Derived from OpenWhispr upstream commit `66e03c104e203f29309fec2ae9e7f82472841776`.
Design: `docs/superpowers/specs/2026-10-28-windows-dictation-design.md`.
Plan: `docs/superpowers/plans/2026-10-28-windows-dictation.md`.

## Artifact

- Unsigned, unpackaged build: `dist\win-unpacked\OpenWhispr Dictation.exe`
  (built with `electron-builder.unsigned-win.json`; no installer, no code signing,
  no auto-update).
- App identity: `com.openwhispr.dictation`, product name "OpenWhispr Dictation".
- User data: `%APPDATA%\OpenWhisprDictation` (settings `.env`, SQLite history,
  the copied Vulkan llama runtime under `bin\llama-vulkan`).
- Model files are **shared read-only** with the installed OpenWhispr at
  `%USERPROFILE%\.cache\openwhispr` (`parakeet-models`, `models`). Nothing is
  moved or deleted there. One addition was made: the
  `nemotron-3.5-asr-streaming-0.6b` streaming model was placed beside the
  existing `parakeet-tdt-0.6b-v3`; the original app sees it as a downloaded
  model and may use it too.

### Launch

Current user preference (updated after testing): the saved profile selects
**Nemotron Speech Streaming EN 0.6B** and **English (US)** transcription instead
of automatic language detection. The English model was added to the shared
cache from the existing benchmark files; all four file hashes match. The
multilingual models remain installed. No rebuild or restart was required.

The user subsequently enabled **Keep Microphone Warm -> 1 minute** to avoid
reopening the device between nearby dictations. The mic-in-use indicator stays
on during that hold; no idle speech is recorded or transcribed. Starts after a
longer pause still incur the cold device-opening time.

Double-click `dist\win-unpacked\OpenWhispr Dictation.exe`, or from PowerShell:

```powershell
& "D:\Teacher\OpenWhisprDictation\dist\win-unpacked\OpenWhispr Dictation.exe"
```

It runs beside the installed OpenWhispr (separate single-instance lock, tray icon
and data). The default dictation hotkey is **Ctrl+Alt+Space** (the installed app
keeps Ctrl+Win; both apps' low-level hooks would fire on a shared modifier-only
chord). Change it, or bind **Mouse Button 4 / 5**, under Settings → Hotkeys.

To rebuild after a source change:

```powershell
npm run build:renderer
npx electron-builder --win --dir --config electron-builder.unsigned-win.json --publish never
```

(Node 25.8 is installed here; upstream pins Node 24. Never regenerate
`package-lock.json` with this Node.)

### Rollback / removal

The installed OpenWhispr was not modified. To remove the derivative:

1. Quit it from the tray.
2. Delete `dist\win-unpacked` (or the whole checkout).
3. Delete `%APPDATA%\OpenWhisprDictation`.
4. Optional: delete `%USERPROFILE%\.cache\openwhispr\parakeet-models\nemotron-3.5-asr-streaming-0.6b`
   (≈680 MB) if the original app should not keep it. Nothing else in the cache
   was touched.

## What changed versus upstream

- **Identity and startup** (`main.js`, `electron-builder.json`): separate app ID,
  name and userData; no OAuth protocol, auth bridge, CLI bridge, update check,
  calendar sync, meeting detection, diarization download or semantic search.
  Settings IPC can no longer start the meeting process/mic monitors
  (`ipcHandlers.js` forces both detectors off). `get-stt-config` returns null,
  so no cloud config fetch runs.
- **Network boundary** (`src/helpers/localNetworkBoundary.js`): Node sockets and
  Chromium requests to non-loopback hosts are refused. This is defense in depth
  inside the app process, not an OS firewall; native sidecars (sherpa-onnx,
  llama-server) only listen on 127.0.0.1. Consequence: **the app cannot
  download models or GPU runtimes**; it relies on files already in the shared
  cache and on the bundled Vulkan runtime.
- **Local-only routing** (`audioManager.js`, `localOnlyDictation.mjs`):
  transcription refuses anything but a local model; cleanup runs only when the
  resolved cleanup route is local, otherwise the raw transcript is kept. No
  OpenAI fallback paths remain.
- **Defaults** (`settingsStore.ts`, `main.js`): fresh profiles start with local
  transcription (Parakeet/Nemotron via sherpa-onnx, model
  `nemotron-3.5-asr-streaming-0.6b`, streaming runtime) and local cleanup with
  `gemma-4-e4b-it-qat-q4_0`. The bundled Vulkan llama runtime
  (`resources/bin/llama-vulkan`, copied from the installed app, llama.cpp build
  9763 — the same build as the bundled CPU binary) is copied into userData on
  first launch (`bundledGpuPacks.js`) and `LLAMA_VULKAN_ENABLED` is set once;
  turning it off in Settings is respected afterwards.
- **Windows mouse activation** (`resources/windows-key-listener.c`,
  `windowsKeyManager.js`, `hotkeyManager.js`, `hotkeyValidator.ts`): side
  buttons (XBUTTON1/2) are hooked with `WH_MOUSE_LL`; left/right/middle are never
  touched. Tap (toggle) and Hold (push-to-talk) both work through the existing
  key-down/key-up routing. By default the bound button is **swallowed** so the
  browser Back/Forward action does not fire; Settings → Hotkeys shows "Keep the
  mouse button's normal action" when a mouse button is bound (`--swallow`
  listener flag, `MOUSE_BUTTON_PASSTHROUGH` in `.env`). Injected (synthetic)
  events are never swallowed.
- **Safe paste** (`resources/windows-fast-paste.c`, `clipboard.js`): `--safe-paste`
  verifies, through UI Automation metadata only (no text is read), that the
  foreground window is the captured one and the focused control is enabled,
  keyboard-focusable, not a password field and not read-only. Anything else
  returns exit 4 and the app does **not** inject: the transcript stays on the
  clipboard and the pill shows "Transcript ready to paste" with a copyable
  transcript. There is no nircmd/SendKeys fallback any more. Limitation: within
  the same window the helper cannot prove the focused field is the *same* field
  that had focus at capture time.
- **No external field monitoring**: the text-edit monitor and auto-learn are
  removed from `ipcHandlers.js` (`noExternalFieldMonitoring.test.js` pins it).
- **Vocabulary**: Dictionary words (preferred spellings) feed the recognizer
  prompt and the cleanup prompt as before. **Spoken aliases** ("heard as…") are
  stored as snippets (alias → preferred spelling) and replaced whole-word,
  case-insensitively, right after transcription and before cleanup
  (`vocabularyAliases.ts`; renaming or removing a word retargets or removes its
  aliases). **Confirmed corrections**: on the home screen, "Fix spelling" lets
  you edit the latest transcript; "Suggest dictionary words" diffs your edit
  against the transcript (`extractCorrectionPairs`) and proposes words with an
  optional "also replace ‹heard› with it" alias. Nothing is saved until "Add
  selected"; an Undo toast removes what was just added. Only the app's own
  transcript is read.
- **UI** (`AppRouter.jsx`, `ControlPanel.tsx`, `SettingsModal.tsx`,
  `SettingsPage.tsx`, `PillCommandMenu.tsx`): a single home screen (hotkey, quick
  links, latest dictation with Copy / Fix spelling), Settings limited to
  General, Hotkeys, Speech-to-Text (dictation tab only) and Cleanup model
  (dictation cleanup tab only). Account, notes, meetings, assistant, calendar,
  integrations and cloud sections are not shown. All new strings are in
  `src/locales/en/translation.json` under `dictationApp.*`,
  `dictionary.aliases.*` and `settingsPage.general.hotkey.mousePassThrough.*`
  (other locales fall back to English).
- **Cues**: the existing start/stop tones (`dictationCues.js`) are fired with
  `void playStartCue()` after the recorder has started and are never awaited;
  the pill state changes are driven by recorder state, not by animations.

## Validation performed (this machine: i9-14900HX, RTX 4070 Laptop, Windows 11)

Automated:

- `npm run typecheck`: pass.
- `npm run build:renderer`: pass.
- `npm run test:dictation` (273 tests, all pass): clipboard restore and Windows safe-paste
  decline paths, no-external-monitoring pin, local Gemma default, network
  boundary, local-only routing, native listener keys, hotkey validation,
  identity, Windows mouse listener spawn/restart (`windowsKeyManagerMouse.test.js`),
  vocabulary aliases and correction pairs (`vocabularyAliases.test.js`),
  correction learner, snippets, hotkey manager, control panel window, bundled
  GPU pack seeding (`bundledGpuPacks.test.js`), capture/cancellation/recovery
  lifecycle, startup and missing-listener fallback, raw PCM/WebM routing and
  cleanup route configuration. The renderer integration test also verifies
  local decode and cleanup, raw text preservation after cleanup failure,
  stale cloud-selection refusal and absence of cloud fallback. Detailed scope
  and full-suite triage: `docs/validation/windows-dictation-tests.md`.
- Latest latency repair removes animation-frame waits before microphone
  preparation/start/stop; cancellation during target lookup remains guarded.
  The affected hook suites add 27 passing checks. "Keep model loaded" is enabled
  to avoid idle reloads, while microphone warm-hold remains off. Measurements and
  limits: `docs/validation/windows-dictation-latency.md`.
- Full `npm test`: see "Full suite" below.

Startup smoke (dev Electron binary, `NODE_ENV=production`, hotkey F24, 45–50 s,
then the process tree was killed; the installed OpenWhispr kept running):

- No `[ERROR]`/`[WARN]` lines; no meeting/process/mic detectors; no calendar,
  Qdrant, diarization, CLI/auth bridge or stt-config activity.
- Hotkey registered; `sherpa-onnx-online-ws` started on the Nemotron model;
  llama-server started on the bundled Vulkan runtime after it was seeded into
  userData (`Bundled Vulkan llama pack { state: 'seeded' }`, "Vulkan0: NVIDIA
  GeForce RTX 4070").
- No microphone capture was triggered.

Packaged build smoke (`dist\win-unpacked\OpenWhispr Dictation.exe --console-logs
--log-level=debug`, hotkey F24, 55 s, then killed): `resourcesPath` and
`userDataPath` point at the artifact and `%APPDATA%\OpenWhisprDictation`; no
`[ERROR]`/`[WARN]`; detectors off; F24 registered; `sherpa-onnx-online-ws` from
the artifact's `resources\bin`; llama-server on the seeded Vulkan runtime
(`Bundled Vulkan llama pack { state: 'present' }` on the second launch). The
packaged `windows-fast-paste.exe --capabilities` reports `safe-paste-v1` and the
packaged `windows-key-listener.exe MouseButton5 --swallow` reports `Mouse=2,
Swallow=1`. The test-only `DICTATION_KEY=F24` and debug log level were removed
from the derivative's `.env` afterwards, so the first real launch uses the
default hotkey.

Measurements (inference transport only — not physical capture, not stop-to-paste):

| Stage | Result |
| --- | --- |
| Nemotron 3.5 streaming, real-paced 200 ms PCM chunks, 7.44 s synthetic English clip (previous agent) | first partial 0.885 s, 11 updates, final flush 477 ms, text complete, `truncated=false` |
| Batch decode of the same clip, 4 CPU threads (previous agent) | Parakeet TDT v3 1.15–1.17 s; Nemotron multilingual 3.68–3.97 s; Nemotron English 4.5–5.0 s (with competing load) |
| Cold sherpa server start incl. silent warm-up (previous agent) | 7.5 s (Parakeet), 7.7 s (Nemotron multi), 10.4 s (Nemotron EN) |
| Gemma 4 E4B Q4_0 cleanup, Vulkan, warm, app's cleanup prompt, thinking disabled (`benchmark-scripts/cleanup-bench.py`) | 12 words: 0.22 s; 41 words: 0.44–0.52 s; 92 words: 1.27–1.42 s (3 runs each) |
| Gemma model load to healthy (Vulkan) | 9.8 s / 19.4 s (two cold starts, while packaging ran) |

Expected warm stop-to-paste for a typical sentence is therefore roughly the
streaming flush (≈0.5 s) plus cleanup (0.2–0.5 s) plus paste (<0.1 s), but this
was **not measured end to end** with a microphone.

## Not validated (needs a person at the machine)

- Real microphone capture, first-word clipping, microphone selection and device
  changes, and sleep/resume. The user's microphone was in use during this work,
  so no capture test was run.
- Physical Mouse Button 4/5 hold and toggle, rebinding while recording, and the
  pass-through toggle in a real browser.
- Safe-paste in real targets: ordinary field, password field (must decline),
  focus moved to another window (must decline), elevated/admin window (expected
  to decline because UIA access is refused), terminals (declines by design).
- Hindi words and personal names: no Hindi audio was available. Nemotron 3.5 is
  multilingual (auto language detection); recognition quality for Hindi and for
  names is unknown. If English accuracy matters more than Hindi,
  `parakeet-tdt-0.6b-v3` (batch, English-stronger) is still installed and
  selectable in Settings → Speech-to-Text.
- Offline operation was validated only by inspection of the boundary code and
  the smoke logs, not by disconnecting the network.

## Known limitations

- No model or GPU-runtime downloads inside the app (network boundary). Install
  models with the original OpenWhispr; the derivative reads the shared cache.
- Safe paste cannot distinguish two editable fields in the same window.
- Account/cloud code and dependencies still exist in the bundle (hidden and
  blocked), so the package is far larger than a purpose-built app would be.
- `SettingsPage.tsx` hides sections with `Boolean(0) &&` guards rather than
  removing them; a future cleanup could delete them outright.
- Locales other than English show the new strings in English.

## Full suite

`npm test` runs ~1,000 test files with one worker per core by default and
exhausted this machine earlier. Run it with limited concurrency:

```powershell
node --import tsx --test --test-concurrency=4 "test/**/*.test.js"
```

The initial run reported 9,010 tests, 8,116 passes, 358 failures, 535 skips and
one todo (`fulltest.log`). Of those failures, 259 shared a renderer module-format
error in the new local-only helper; it is now an explicit ES module and the
supported regression gate passes.

The continuation full run and its remaining failures are documented in
`docs/validation/windows-dictation-tests.md` and `fulltest-after-triage.log`.
It reported 9,034 tests, 8,384 passes, 107 failures, 542 skips and one todo.
The report names every failed case and separates known incompatibilities from
unresolved legacy assertions; not all failures are certified harmless.
It includes tests for removed cloud features, POSIX-only assumptions and Node
native-binding mismatches, so it is not a green release gate for this derivative.
Three cloud test workers required termination after waiting indefinitely for
disabled operations. Use `--test-timeout=60000` on future full diagnostic runs.

The final Windows package was rebuilt and smoke-launched after the module fix.
All 605 packaged application files compared with source matched byte-for-byte.
Nemotron initialized and Gemma pre-warmed on the bundled Vulkan runtime with no
app-level errors or warnings. Native model-loader diagnostics and Node's existing
module-type performance warning remain in the raw logs. No microphone capture
or physical paste was triggered. The smoke process tree was stopped; the installed
OpenWhispr remained running.
