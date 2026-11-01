# Maeve Orb Visuals Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans. Execute inline as authorized by the user; keep the checkpoint on main.

**Goal:** Implement all ten visual improvements in the approved try-and-revert workflow.
**Architecture:** Extend the existing renderer and snapshot bridge. Read real v2 run/request state; count reply PCM without including cues. Add no dependencies.
**Tech Stack:** Python, SQLite read-only, WebView2, WebGL, Canvas, CSS.
**Spec:** ../specs/2026-11-01-maeve-orb-visuals-design.md

## Global Constraints
- Work in D:/Teacher/tts-audition/phonon; scratch stays there.
- Copy source/UI/tests into examples/t3-voice. Use venv Python and pythonw.
- No simulated input, device-default changes, token output, or direct saved-pref edits.
- Checkpoint first; changes remain a separate revertible commit. Push main as authorized.

## Review Focus
- Old approval rows cannot light another run or thread: fixture test in Task 1.
- Startup cues must not count as reply progress: PCM callback test in Task 1.
- Reduced motion must stop shader and particle time as well as CSS: rendered test in Task 2.
- Long bubbles must allow reading earlier text without losing the first line: rendered scroll tests in Task 2.
- New menu entries must fit both card sizes: layout tests in Task 3.

### Task 1: Truthful engine snapshot and progress
Files: t3_voice_core.py, live_reader.py, t3_voice.py, test_t3_voice_core.py, test_orb_logic.py.
Interfaces: read_agent_activity(path, thread) returns {run, activity, approval, needsInput, producing}; ContinuousAudio.begin_reply(run), finish_reply(run), playback_progress() track explicitly tagged PCM; snapshot exposes agent, playback, visualEvents, highContrast, reducedMotion.
- [x] Add failing SQLite fixture tests for active/settled runs, requests, stale requests, unrelated threads, unsupported schema.
- [x] Add failing audio tests for cues excluded, same-run continuity, bounded progress, and interruption reset.
- [x] Implement activity helper with bounded read-only queries, throttled engine polling, event counters, normal appearance-pref setters and tagged reply output.
- [x] Run venv/Scripts/python.exe -m unittest test_orb_logic test_t3_voice_core test_live_reader -q; require zero failures.

### Task 2: Ten visual effects and appearance controls
Files: ui/orb.html, verify_orb_ui.py.
Interfaces: consume Task 1 snapshot fields; visualState() maps actual activity without overriding dictation; visualMotion(now) returns frozen decorative time under reduced motion; stable thread accent from thread ID.
- [x] Add rendered failing checks for agent state shapes, event deduplication, scroll-only mask, compact/capped bubble, appearance controls and motion freeze.
- [x] Extend shader for spiral, ripple, thread rim, approval edge and interior stars. Draw orbiting comet instead of spinner, gradient spectrum and sample-based playback line.
- [x] Add final-word settle glow, readable glass highlights, scroll-follow behavior, appearance overlay and persistent accessible switches.
- [x] Run window checker; require all 46 existing cases plus new feature checks without failures.

### Task 3: Review, delivery and restart
Files: README.md plus verified source copies.
- [x] Review diff and spec coverage; inspect captured orb and toolbar screenshots.
- [x] Update README and test count; copy verified files and check identical bytes.
- [x] Run unit suite, UI checker and git diff --check after final edits.
- [x] Restart only confirmed pythonw t3_voice.py processes; verify ready and clean logs after about 20 seconds.
- [x] Commit with required author/trailer, push main, and report checkpoint and feature commit with limitations.
