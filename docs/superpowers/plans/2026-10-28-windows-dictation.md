# Windows Local Dictation Implementation Plan

> **For agentic workers:** Use focused independent implementation tasks and review their integration. Steps use checkbox syntax for tracking.

**Goal:** Deliver a separate, local-only Windows dictation app based on OpenWhispr.

**Architecture:** Retain upstream Electron capture, local inference and paste components where appropriate. Isolate identity and data, remove non-dictation runtime paths, add Windows mouse activation, and replace the control surface with focused settings and status.

**Tech Stack:** Electron, React, Node.js, Windows native input, sherpa-onnx and local llama inference.

**Spec:** docs/superpowers/specs/2026-10-28-windows-dictation-design.md

## Global Constraints

- Preserve existing installation, data and shared models; no cloud transcription or cleanup.
- No always-on microphone, arbitrary surrounding text collection, or blocking feedback.
- Keyboard fallback; configurable mouse button, hold and toggle; editable vocabulary and confirmation before learning.
- Report actual measurements and unverified functionality, without claiming accuracy not tested.

## Review Focus

- Rebinding or missed button-up must not leave capture stuck; exercise hold/toggle and unregister.
- Old results must not paste into a newer session; exercise delayed completion and repeated stop.
- Failed or unsafe paste must retain copyable text; exercise focus loss and password fields.
- Offline operation must not call cloud providers; inspect and test routing.
- Capture startup must not clip initial speech; test recorded samples and physical activation.

### Task 1: Separate identity and runtime
**Files:** main.js, electron-builder.json, packaging scripts.
- [ ] Isolate user data, protocol, app identity and update behavior from installed OpenWhispr.
- [ ] Remove or disable unrelated background startup and build downloads while retaining required local inference and paste resources.
- [ ] Verify concurrent operation and packaging against original app.

### Task 2: Windows activation
**Files:** resources/windows-key-listener.c, src/helpers/hotkeyManager.js, focused tests and settings integration.
- [ ] Test then implement native side-button down/up handling, rebinding, unregister and hold/toggle.
- [ ] Verify keyboard fallback and noninterference with normal mouse buttons.

### Task 3: Local pipeline and vocabulary
**Files:** transcription, cleanup and dictionary helpers and focused tests.
- [ ] Enforce local-only routing and preserve transcription on failures and stale sessions.
- [ ] Provide user-confirmed editable corrections and aliases; exercise correction and undo behavior.
- [ ] Compare local streaming and existing Parakeet plus cleanup on consistent samples, and retain active models unless replacements are validated.

### Task 4: Focused UI
**Files:** control panel, settings and dictation status components.
- [ ] Present compact dictation states and relevant settings, with copyable result and immediate asynchronous cues.
- [ ] Remove unrelated navigation and background work, and verify accessibility and build.

### Task 5: Integration and delivery
- [ ] Run focused and full relevant tests, build a separate Windows artifact, and review integration.
- [ ] Exercise physical input, capture, paste, offline behavior, and startup/resume when possible; measure cold and warm latency and report sample limitations.
- [ ] Document launch, rollback, exact validation and remaining limitations.
