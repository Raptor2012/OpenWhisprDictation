# Windows local dictation validation — 2026-10-28

Environment: Windows 11, Node 25.8.2, Electron 43.8.3. Source baseline:
`66e03c104e203f29309fec2ae9e7f82472841776`; derivative changes remain uncommitted.

## Supported regression gate

```powershell
npm run test:dictation
```

Latest result after the latency repair: **273 tests passed, zero failures or skips**,
in 63.0 seconds. The original delivery run passed 271 tests in 90.1 seconds.
The explicit 25-file scope is in `scripts/test-dictation.js`, with four workers
and a 60-second timeout per test. This does not replace the upstream suite.

Coverage includes local settings and identity, loopback-only networking,
local decode with and without the PCM WAV, local cleanup, raw transcript
preservation on cleanup failure, refusal of stale cloud selections and old
cloud-fallback preferences, cancellation ownership, interrupted-recording
recovery, PCM/preview lifecycle, safe-paste refusal and clipboard preservation,
hotkey validation/startup/fallbacks, Windows mouse listener arguments and
reconciliation, vocabulary aliases, correction extraction, snippets and GPU
runtime seeding.

The renderer integration test loads the actual settings resolver and reasoning
service, with native decode and inference mocked at the Electron bridge. It does
not capture a physical microphone or execute a real paste. A mutation that
allowed every cleanup route caused its explicit zero-upload assertion to fail;
the unmodified code passes.

## Regressions and test compatibility repaired

- The original full log contained 259 `ReferenceError: module is not defined`
  failures from `localOnlyDictation.js`. It is now an explicit ES module,
  `localOnlyDictation.mjs`, matching its renderer consumer. Both the local WebM
  decode and deterministic cleanup route were reproduced failing before this
  repair and passing afterwards.
- Startup tests extracted JavaScript using LF-only delimiters from a CRLF
  checkout. Normalize line endings before extracting; the startup tests now pass.
- The Windows default-hotkey expectation now reflects Ctrl+Alt+Space. The F8
  fallback when the listener is absent, and rejection of listener-only bindings,
  remain covered.
- The pending-decode cancellation test now exercises the supported local route.
  Stale cloud selection and failed local decode tests assert refusal without
  uploads, instead of expecting removed cloud behavior.

## Build checks

- `npm run typecheck`: exit 0.
- `npm run build:renderer`: exit 0. Vite still reports large chunks and plugin
  timing advisories inherited from the large upstream renderer graph.
- Unsigned Windows directory build: exit 0; `afterPack` verified native binaries.
- All 605 packaged application files with corresponding source files matched
  byte-for-byte in the final ASAR inspection.
- `git -c core.safecrlf=false diff --check`: exit 0.

The executable is `dist/win-unpacked/OpenWhispr Dictation.exe`. It is unsigned.
Physical microphone, mouse-button operation, paste targets and disconnected
network operation remain manual validation items in the delivery README.

## Upstream full suite

The initial run (`fulltest.log`) reported 9,010 tests, 8,116 passes, 358 failures,
535 skips and one todo. It was not a passing release check.

The continuation rerun uses the same four-worker full-suite command and is
recorded in `fulltest-after-triage.log`: **9,034 tests, 8,384 passes, 107 failures,
542 skips, one todo**, exit 1, in 22 minutes 57 seconds. No renderer
`module is not defined` error remains. Counts are not directly comparable with
the initial run because more nested tests executed after the module repair and
three workers were stopped. Three legacy cloud test workers stalled
waiting for operations disabled in this derivative and were terminated to let
the remaining files continue:

- `test/helpers/audioManagerCustomUpload.test.js`
- `test/helpers/audioManagerStreamingFinalization.test.js`
- `test/helpers/audioManagerStreamingRouting.test.js`

For future full diagnostics, bound each test explicitly:

```powershell
node --import tsx --test --test-concurrency=4 --test-timeout=60000 "test/**/*.test.js"
```

The full upstream suite includes removed cloud/assistant/meeting/account
behavior, POSIX-specific filesystem/socket assumptions, native SQLite tests
built for Electron rather than the shell's Node ABI, old default-setting
expectations, and strict locale parity despite the documented English fallback.
These are separate from the supported regression gate. A failure in that full
suite must still be inspected; it is not automatically an expected removal.

Every reported failing case is named in
[`windows-dictation-full-suite-failures.md`](windows-dictation-full-suite-failures.md),
with error excerpts and classification. The full run loaded the raw-WAV tests
before their cloud expectations were updated; those two cases pass in the final
supported gate. Several legacy archive/tar, assistant-panel/note and policy
assertions remain unresolved outside that gate. The full suite is still red;
this delivery makes no claim that all 107 failures are harmless.
