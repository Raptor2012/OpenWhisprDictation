# Maeve voice orb for T3 Code

A small orb that gives one [T3 Code](https://t3.chat) thread a voice, fully local. It is a frameless WebView2 window with true per-pixel transparency (the DWM frame is extended over the whole window and the system backdrop turned off), so only the orb and its glow are drawn on the desktop.

The orb stays out of the way:

- It appears while the dictation key is held, while your words are transcribed and delivered, and while Maeve speaks. It springs in, lingers about a second, then fades and the window is hidden. It only takes keyboard focus when you deliberately open settings or review a transcript above the orb.
- When T3 Code is minimized, a speech bubble rises above the orb and types out Maeve's reply at speaking pace, and briefly shows what you said, like a desktop pet.
- While you hold the dictation key, **You · live** shows your recognized words above the orb or toolbar, even with T3 open. It starts with a listening indication, updates a rolling preview as you speak, keeps the last words visible while transcription finishes, then briefly shows OpenWhispr's final text. Word corrections can update in place; the preview is never sent to T3. An open review editor takes priority over the bubble.
- A small waveform beneath the orb reacts to microphone input; toolbar mode uses its built-in waveform. Short voice peaks are retained between UI updates and quiet speech is mapped to a perceptible, gently springing orb response. New and corrected words blur and rise into view on both sides of the conversation; unchanged words keep their existing elements instead of flashing again. Reduced-motion settings disable the word animation.
- Hover the orb for two buttons: mute your microphone, and mute Maeve. With Maeve muted and T3 minimized, replies still appear silently in the bubble.
- Ctrl+Alt+M stops Maeve while she speaks; otherwise it summons the orb for a few seconds so you can click it for settings.
- The same UI mirrors OpenWhispr dictation: a blue orb and live mic waveform while recording, a working animation after release, then a green done pulse or a failure indication from the local history. It reads `DICTATION_KEY` and `ACTIVATION_MODE` from OpenWhispr's `.env`, including mouse buttons and push/tap modes. It never changes those settings or triggers the key itself.
- Hover and use the minimize chip, or choose **Options → Minimize to toolbar**, for a persistent 200×48 capsule. The mini orb opens settings; the other controls mute the T3 microphone, mute Maeve, and expand back to the orb. The waveform follows microphone input and Maeve playback. Bubble and settings windows grow upward around the same bottom-centre anchor. The toolbar preference survives restarts.
- **The orb is the only recording surface.** Both OpenWhispr overlay variants (`Voice Recorder` and its frameless, non-activating `OpenWhispr` overlay) receive empty window regions while the recorder keeps running. Every matching overlay is tracked, including replacement windows; normal exit restores them. OpenWhispr's settings window remains accessible. There is no toggle that accidentally brings back a duplicate pill. The input button pauses T3 voice input; it does not disable OpenWhispr's recorder.

**Hold to dictate, release to finish.** Use OpenWhispr Dictation's configured push-to-talk key (currently Mouse Forward / `MouseButton5`). Pauses of any length do not end the held dictation. Release starts OpenWhispr's transcription and cleanup; its completed history row goes directly to the selected delivery mode. The orb adds no silence deadline, continuation grace or end-of-turn model to this path. The former hands-free choice is removed, including saved preferences that would otherwise restart continuous capture. The orb's microphone stream supplies the live level meter and display-only preview while the key is held.

Starting a held dictation stops Maeve immediately. OpenWhispr also pastes into the focused field, so keep T3's composer unfocused for immediate-send or orb-review delivery. If the review editor is focused, OpenWhispr can insert additional dictated text there for editing before you send.

The loop:

1. Hold the configured dictation key and speak naturally; release when finished.
2. OpenWhispr's running Parakeet 0.6B service (sherpa-onnx WebSocket on `127.0.0.1:6006`) transcribes it in about 300 ms.
3. The completed OpenWhispr history row enters the selected delivery mode immediately: send, preview, or draft. Only transcription/cleanup/delivery work contributes to the release-to-text time; there is no additional silence wait in the orb.
4. Maeve (Phonon 31M, British English, CPU) reads the reply sentence by sentence while it is still streaming. First audio in about 40 ms. Speaking again interrupts her.

Speech processing stays local, with no additional cloud speech service or turn detector. The transcript is sent to whichever provider powers your chosen T3 thread as one ordinary message.

## Requirements

- Windows, Python 3.13, the T3 Code desktop app running.
- OpenWhispr Dictation running with the Parakeet model (it owns the sherpa service on port 6006).
- Phonon model and the Maeve voice in the Hugging Face cache (`gradium/phonon-31m-en`, `gradium/phonon-voices`). Run any `ptts` sample once online to populate it; the panel runs offline afterwards.
- Headphones recommended. Pressing the dictation key interrupts Maeve before recording your next turn.

## Setup

```powershell
python -m venv venv
venv\Scripts\python -m pip install -r requirements.txt
venv\Scripts\python pair_t3.py        # one-time: mints a 30-day local MCP token
"Start Maeve T3 Voice.cmd"            # launches the panel without a console window
```

Press Ctrl+Alt+M to summon the orb, click it, press **Voice on**, and talk. By default it follows the thread currently open in the local T3 desktop app. It reads the exact document URL through Windows accessibility on a background worker, validates the thread in T3's read-only database, and never guesses from recent message activity. The card and mini-orb tooltip show the destination. If the open route cannot be resolved, automatic capture is disabled; the manual picker remains available.

Choosing a thread in the existing picker pins that destination. **Options → Follow active T3 thread** resumes automatic following. The voice enable state carries across followed threads. Routing changes wait for the current recording/transcription/delivery or pending orb review; a detected change during capture rejects the transcript rather than sending to an unintended thread.

Use the **Transcript delivery** dropdown in settings to choose:

- **Send immediately** (default): send the transcript to the captured destination over local MCP.
- **Review above the orb**: show an editable preview with its destination title. **Enter** sends once, **Shift+Enter** adds a line, and **Esc** or **Cancel** discards it. While sending, editing and repeat confirmation are disabled. A failed send keeps the edited text and offers **Retry**; a successful send dismisses the preview. The destination stays fixed until you send or cancel.
- **Draft in T3**: append the transcript to the existing composer draft in the exact captured thread without submitting it. Press **Enter in T3** when ready. This uses the composer's accessibility value API, never simulated keys or an arbitrary clipboard paste. The destination must still be open in T3; a mismatch or inaccessible editor reports an error and sends nothing. An already-pasted matching transcript is not appended twice.

The follow, pin and delivery preferences survive restarts. Settings grow upward when the thread list opens; the options menu stays compact. Expanded windows are clamped to the current monitor's work area. Controls and editable text do not initiate window dragging; the orb and toolbar waveform remain draggable. Controls expose keyboard focus and accessible labels. Stop with the Stop pill or Ctrl+Alt+M; the shortcut cancels an unsent review. Options also holds **Clean up with OpenWhispr's model** (adds its local cleanup latency) and **Start with Windows**.

## Files

| File | Role |
|---|---|
| `t3_voice.py` | Engine (microphone, playback, routing, status file) and the pywebview host |
| `ui/orb.html` | The orb and card: canvas animation, state palette, controls. Open with `?demo=1` for a design preview |
| `t3_voice_core.py` | Per-thread routing, streaming sentence feed, utterance gate, MCP sender, ASR client |
| `live_reader_core.py` | Read-only SQLite feed of T3 messages and Markdown-to-prose cleaning |
| `live_reader.py` | Earlier reader; the panel reuses its persistent audio device |
| `pair_t3.py` | Mints the MCP token through T3's pairing-code OAuth flow |
| `test_*.py` | `python -m unittest test_orb_logic test_t3_voice_core test_live_reader -q` runs 65 tests, including bounded hold-only previews, stale-result rejection, held-recording completion races, meter peak retention, both overlay variants, work-area clamping, review failure/retry and routing; no audio needed |
| `verify_orb_ui.py` | Optional WebView2 verification: `python verify_orb_ui.py` checks 44 state/layout combinations, live word revisions, dismissal races and control callbacks in an isolated demo. It never opens the mic, simulates input or sends to T3. Evidence is written beneath `runtime/orb-ui-qa/`. |

`t3-voice-token.txt`, settings, status and logs are git-ignored. The status file holds timings and counters only, never conversation text.

## Tuning

- The active hold/release path has no VAD endpoint or silence wait. The earlier utterance-gate helpers remain in the core for the older prototypes/tests, and are not used by the orb's microphone callback.
- OpenWhispr owns recording/transcription/cleanup; its configuration is read, never rewritten by the orb.
- The display-only preview reuses the local recognizer on at most six seconds of recent audio, about once a second, with one request in flight. It starts after at least 650 ms of audio and avoids repeated inference during silence. Words may be revised; this is an approximate rolling preview, not the final cleaned transcript. Release clears its audio buffer and discards late results without waiting for preview recognition. Only OpenWhispr's completed history row enters the delivery flow.
- A previous dictation's cleanup completing during a new held recording cannot mark the live recording done or replace its preview. The status file counts accepted preview updates without storing transcript text.
- The orb uses premultiplied alpha for WebView2 transparency, a restrained audio-responsive halo, and continuous noise phase. Speech does not draw expanding ripple rings.

## Cleanup model benchmark (OpenWhispr Dictation, 2026-11-01)

`bench_cleanup.py` runs OpenWhispr's cleanup prompt over five dictation samples against the app's llama-server (port 8221) and any GGUF paths you pass (each spawned on port 8231 with the bundled Vulkan build). RTX 4070 Laptop, 8 GB VRAM, with a game and the Unity editor also on the GPU:

| Model | Median per cleanup | Notes |
|---|---|---|
| gemma-4-E4B q4_0 (previous default) | ~3.2 s | 5 GB weights plus a 16k context left ~0.5 GB VRAM free; everything else spilled to system memory |
| Qwen3.5-2B Q4_K_M | ~0.45 s | Picked. Same corrections as gemma on 4 of 5 samples; took "new paragraph" literally once |
| Qwen3.5-0.8B Q4_K_M | ~0.33 s | Rejected: echoed the raw transcript on 3 of 5 samples and invented a sentence once |

Set `LOCAL_CLEANUP_MODEL=qwen3.5-2b-q4_k_m` in `%APPDATA%\OpenWhisprDictation\.env` with the GGUF in `~/.cache/openwhispr/models/`. On an 8 GB card, VRAM headroom matters more than model speed: a model that fits beside your other GPU work beats a bigger one that spills.
