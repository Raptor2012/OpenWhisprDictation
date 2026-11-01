# Maeve orb: ten visual improvements

Status: proposed design, pending user approval. No product code has changed.

## Intent

Add all ten requested effects to the existing Maeve orb and toolbar. Make thinking, sending, interruption, and approval waits recognizable without reading labels. Preserve voice routing, recording, device preferences, and transcript delivery.

## Approach

Recommended builder choice: extend the existing WebGL shader, 2D particle/spectrum canvases, CSS, and Python snapshot bridge. Keep one animation loop. No new rendering dependency.

A second animation framework would duplicate timing, accessibility, and transparency handling. A replacement renderer would discard the existing audio-responsive nebula and broaden this task unnecessarily. Neither is recommended. The user has requested all ten outcomes; this implementation approach remains a proposal.

## Existing behavior and relevant changes

The page already renders a fluid nebula, spectral waveforms, drifting particles, glass cards, word entry animations, and a capped bubble. Current bubbles reserve layout as words reveal and have deliberately no top fade; the new request supersedes that presentation rule for scrolled long text only. The engine currently supplies speech/dictation states but does not expose agent approval or work states. ContinuousAudio already counts played samples.

## Visual behavior

1. **State shapes.** Thinking draws a restrained inward spiral inside the rim. A confirmed delivery produces one outward ripple, triggered by a delivery event counter rather than repeated polling. Interrupting active Maeve playback produces a short contraction, triggered by an interruption event; ordinary playback completion does not contract. Preserve the recognizable fluid sphere.
2. **Thread accent.** Derive a stable, subtle rim hue from the selected thread ID. It persists across launches without writing a separate preference. Thread accents never replace the functional state palette. Neutral accent when there is no resolved thread.
3. **Thinking trail.** Replace the busy spinner with a thin orbiting particle comet while the selected agent is running. Increase its speed during actual streamed assistant output. Tool waits retain the slow trail; idle and settled runs stop it. Approval waits use the amber edge instead.
4. **Word entry and settlement.** Live words drift upward from the orb direction with soft opacity. Preserve unchanged word elements during transcript revisions. The transition from live/transcribing to final text adds one brief settling glow, without restarting animation on every poll. Maeve's text continues at its current speaking pace.
5. **Bubble sizing and scroll.** Short messages use a compact bubble. Long messages cap at the existing 113px text viewport. Reserve the available message's layout before revealing its words; never resize because of an individual revealed word. Streaming updates may grow the viewport to the cap but never shrink it mid-utterance. Scroll to follow new words unless the user is reading earlier text; resume following at the bottom. Apply a top fade only when text has actually scrolled above the viewport. First lines, short messages, and unscrolled placeholders stay fully readable.
6. **Approval edge.** Pulse amber when the selected thread has an unresolved approval request, and show a concise accessible status. Keep the orb visible during that wait. Do not infer approval from prose. The effect clears after resolution, thread changes, or cancellation. It does not approve anything or take focus. User-input requests may share an explicit needs-input label, but must not be mislabeled as permission approval.
7. **Glass panels.** Refine the existing blurred bubble/settings/review/device surfaces with a restrained hairline top highlight. Preserve readable dark backing, premultiplied transparency, and current hit targets. The highlights cannot intercept input.
8. **Toolbar.** Give the existing spectrum a coordinated cool-to-violet gradient while retaining frequency and microphone/playback fidelity. Add a thin playback line for Maeve. Use actual audio samples, exclude startup chimes, and reset on a new reply or interruption. While a streamed reply has an unknown total, show an explicitly indeterminate line; once synthesis has supplied the final total, show bounded played/total progress. Never claim a reply is complete before output drains. Sentence boundaries within a reply do not reset progress.
9. **Idle presence.** Add faint stars inside the dark core while the orb is visible, summoned, or pinned. The shimmer stays subtle and does not keep a hidden orb visible. Clip stars to the sphere; no bright particle spray at idle.
10. **Accessibility.** Add a compact Appearance panel under Options with High contrast and Reduced motion switches. Both persist through the normal preference API. Respect the Windows/browser reduced-motion preference even when the manual reduction switch is off; label that behavior. Reduced motion keeps state colors, static shape cues, readable spectra, and progress, while suppressing orbiting, spiraling, pulsing, ripples, contractions, shimmer, blur/word travel, and spring overshoot. High contrast strengthens text and borders and makes panels more opaque. Controls expose names, checked states, keyboard focus, and status text. Device choices remain unchanged.

## Engine and data contract

Read selected-thread run/request metadata through a bounded, read-only SQLite helper in t3_voice_core.py, throttled independently of 20Hz page polls. The installed database has orchestration_v2_projection_runs and orchestration_v2_projection_runtime_requests. Use explicit unresolved request status and response capability to distinguish approvals from questions; resolve the schema using fixtures and actual metadata, without printing conversation content or credentials. Do not rely on legacy projection tables when v2 data is present. Missing/unsupported metadata yields an unknown/neutral agent activity, never a fabricated approval.

Add snapshot fields for agent activity, approval presence, output activity, visual event counters, appearance preferences, and playback progress. Clear thread-specific state on route changes. Use event counters to prevent poll-driven retriggering. Keep audio counters under the existing output synchronization; do not add database or page work to audio callbacks.

## Layout and performance

Appearance uses an overlay like Audio devices, with a compact scrollable Options menu if necessary. All controls must fit both native card sizes and expanded thread-list sizes. Closing the card closes both overlays and clears native-dropdown protection. Keep existing window anchors and monitor clamping. Use bounded particle counts, elapsed-time animation, and no additional perpetual timers beyond existing loops. Reduced motion freezes decorative time rather than merely hiding CSS animations.

## Verification and delivery

Add focused unit fixtures for running/idle/approval/input states, stale/resolved requests, route changes, event deduplication, progress boundaries and interruption reset, and preference round trips. Extend WebView2 verification to cover every effect, appearance controls, reduced-motion behavior in shader/canvas/CSS, contrast styling, long/short/scrolled bubble behavior, and both layouts. Update obsolete no-mask expectations to require a fade only for genuinely scrolled content; keep full first-line readability checks.

Run the full three-module unit suite and all existing 46 layout cases plus new feature checks. Render and inspect evidence screenshots without simulated mouse/keyboard input. Restart only pythonw processes running t3_voice.py, launch with the specified venv pythonw, and verify ready status and traceback-free logs. Copy verified source/test/UI files to examples/t3-voice, update README/test count, commit as Sanket Das with the requested co-author trailer, and push main as established in this session. Do not change default audio devices, select a device, print the token, or directly edit saved preferences. Store scratch evidence only inside phonon.

## Builder discretion and remaining limitations

Exact colors, particle counts, shader constants, animation durations, and accessible control wording are builder choices, guided by the existing deep-space aesthetic. Live approval behavior requires a naturally occurring approval to verify end to end; deterministic fixtures must cover it before release. A real device switch remains outside this visual task. This design does not add sound effects or approval actions.
