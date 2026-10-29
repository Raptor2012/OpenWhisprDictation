# Dictation latency pass - 2026-10-28

Latest profile update: the user explicitly authorized a **60-second microphone
warm hold** after the remaining driver-opening delay was measured. It is enabled
and the app UI shows **1 minute**. This supersedes the earlier warm-hold-off
observations below. The first acquisition after a longer pause is still cold;
idle speech is not recorded/transcribed while the device is held. Warm-start
latency awaits the user's next two-dictation test; no rebuild was required.

User feedback: delay both before capture starts and after speaking stops.
The active profile uses Nemotron Speech Streaming EN 0.6B, English (US),
and local Gemma 4 E4B QAT cleanup on the RTX 4070 Laptop GPU.

## Confirmed avoidable delay

`useAudioRecording.js` awaited two compositor frames before preparing the
microphone, starting a recording, and stopping capture. Each frame had a 250 ms
fallback because hidden/occluded windows may stop painting. Each affected action
could therefore wait up to 500 ms before doing its work.

Capture preparation and stop now run immediately; React renders status updates
concurrently. Sounds remain asynchronous. A preparation cancelled while the
target lookup is pending cannot later start a recording. Microphone warm-hold
remains off: no microphone is kept open between dictations.

The existing **Keep model loaded** preference was enabled in the running app.
This prevents the cleanup server unloading after five idle minutes and avoids
its next model-load delay. It retains RAM/VRAM while the app is open; it does not
keep the microphone open. Model selection, cleanup quality, English-only
configuration and paste verification were retained.

## Measurements of the already-warm local services

- Existing English online server, 7.06-second synthetic English WAV replayed at
  real speed in 200 ms chunks: first partial 848 ms, ten updates, final flush
  **251 ms**, 102 output characters, `truncated=false`.
- Existing Vulkan cleanup server, application's default cleanup prompt with
  thinking disabled: **530 ms** for nine input words and **313 ms** for 21 input
  words. The second request reused the cached system prompt. These requests used
  synthetic text and did not change the cleanup configuration.

These are inference-transport measurements, not physical press-to-record or
stop-to-paste measurements. The frame waits are verified independently by the
regression test; no claim is made that every actual dictation saves 500 ms.

## Automated verification

- `npm run test:dictation`: **273 passed**, zero failures or skips.
- Affected hook/lifecycle, paste-recovery and visual-frame suites: **27 passed**.
- `npm run typecheck`: exit 0.
- `npm run build:renderer`: exit 0.
- Focused code review: no actionable findings.

The regression test holds compositor frames indefinitely and verifies that
start, stop and mouse preparation still progress, and that cancellation during
target lookup cannot start capture. It failed against the old start path and
passes after the repair. Native microphone behavior remains a user test.

The broad upstream suite was not rerun for this targeted hook repair. Its prior
107 failures and interrupted cloud workers remain documented in
`windows-dictation-full-suite-failures.md`; the scoped passes above are not a
claim that the entire upstream suite is green.

## Delivery

Follow-up from actual user trials: the first microphone acquisition took 1,946 ms;
seven later trials took 765-1,075 ms to get the microphone ready. Remaining setup
after microphone readiness was 28-46 ms (83 ms on the first trial). These timings
come from `Recording start timing` in `latency-app.log`, so the remaining startup
cost is acquiring a usable input stream rather than the removed frame wait.
The existing warm-hold feature could reuse an open device between nearby
dictations, but it remains off pending the user's choice because the earlier
preference was to close the microphone between sessions. Its capture/hold/health
and cancellation tests passed: 48 tests, zero failures.

The Windows build completed successfully and all 605 packaged application files
matched source. The installed archive's recording hook matches the repaired
source and contains no `waitForVisualFrames` dependency. The executable remains
at `dist/win-unpacked/OpenWhispr Dictation.exe`; the previous directory is retained
at `dist/win-unpacked-before-latency-20261028` for rollback. The app was restarted
using the existing profile. Session-local info-level timing output is captured
in `latency-app.log` for the next user trial; full transcript debug logging is off.
