# Maeve voice orb for T3 Code

A small orb that gives one [T3 Code](https://t3.chat) thread a voice, fully local. It is a frameless WebView2 window with true per-pixel transparency (the DWM frame is extended over the whole window and the system backdrop turned off), so only the orb and its glow are drawn on the desktop.

The orb stays out of the way:

- It appears only while you are speaking (after 140 ms of confirmed speech), while your words are transcribed and sent, and while Maeve speaks. It springs in, lingers about a second, then fades and the window is hidden. It only takes keyboard focus when you choose to review a transcript above the orb.
- When T3 Code is minimized, a speech bubble rises above the orb and types out Maeve's reply at speaking pace, and briefly shows what you said, like a desktop pet.
- Hover the orb for two buttons: mute your microphone, and mute Maeve. With Maeve muted and T3 minimized, replies still appear silently in the bubble.
- Ctrl+Alt+M stops Maeve while she speaks; otherwise it summons the orb for a few seconds so you can click it for settings.
- The same UI mirrors OpenWhispr dictation: a blue orb and live mic waveform while recording, a working animation after release, then a green done pulse or a failure indication from the local history. It reads `DICTATION_KEY` and `ACTIVATION_MODE` from OpenWhispr's `.env`, including mouse buttons and push/tap modes. It never changes those settings or triggers the key itself.
- Hover and use the minimize chip, or choose **Options → Minimize to toolbar**, for a persistent 200×48 capsule. The mini orb opens settings; the other controls mute the T3 microphone, mute Maeve, and expand back to the orb. The waveform follows microphone input and Maeve playback. Bubble and settings windows grow upward around the same bottom-centre anchor. The toolbar preference survives restarts.
- **Hide OpenWhispr's own pill** is enabled by default, giving dictation and Maeve one shared surface. The original pill receives an empty window region while its recorder keeps running; disabling the option or quitting normally restores it. The mute controls affect the T3 integration, not OpenWhispr's recorder.

Two microphone modes:

- **Hands-free** (default): the orb owns the microphone. WebRTC VAD endpoints after 400 ms of silence; speaking again interrupts Maeve.
- In either mode, starting OpenWhispr dictation stops Maeve and suppresses hands-free capture during recording and for 600 ms after release. Dictation is therefore not also captured as a hands-free T3 utterance.
- **OpenWhispr hotkey**: dictate with OpenWhispr Dictation's own hotkey. Each completed dictation in OpenWhispr's local history is forwarded to the thread. OpenWhispr also pastes into the focused field, so keep T3's composer unfocused in this mode.

The loop:

1. You speak. WebRTC VAD endpoints the utterance after 400 ms of silence.
2. OpenWhispr's running Parakeet 0.6B service (sherpa-onnx WebSocket on `127.0.0.1:6006`) transcribes it in about 300 ms.
3. The text is posted to the chosen T3 thread over T3's local MCP endpoint (about 20 ms per call).
4. Maeve (Phonon 31M, British English, CPU) reads the reply sentence by sentence while it is still streaming. First audio in about 40 ms. Speaking again interrupts her.

Nothing leaves the machine and no provider tokens are involved. Each spoken message is one ordinary turn for whichever model runs the thread.

## Requirements

- Windows, Python 3.13, the T3 Code desktop app running.
- OpenWhispr Dictation running with the Parakeet model (it owns the sherpa service on port 6006).
- Phonon model and the Maeve voice in the Hugging Face cache (`gradium/phonon-31m-en`, `gradium/phonon-voices`). Run any `ptts` sample once online to populate it; the panel runs offline afterwards.
- Headphones. The microphone stays open while Maeve speaks so you can interrupt.

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
- **Review above the orb**: show an editable preview with its destination title. **Enter** sends once, **Shift+Enter** adds a line, and **Esc** or **Cancel** discards it. Hands-free capture pauses while the preview is open. The orb takes focus for this review only; the destination stays fixed until you send or cancel.
- **Draft in T3**: append the transcript to the existing composer draft in the exact captured thread without submitting it. Press **Enter in T3** when ready. This uses the composer's accessibility value API, never simulated keys or an arbitrary clipboard paste. The destination must still be open in T3; a mismatch or inaccessible editor reports an error and sends nothing. Hands-free mode is recommended. In OpenWhispr hotkey mode, an already-pasted matching transcript is not appended twice.

The follow, pin and delivery preferences survive restarts. Settings grow upward when the thread list or options menu opens. Stop with the Stop pill or Ctrl+Alt+M. Options also holds **Clean up with OpenWhispr's model** (adds its local cleanup latency) and **Start with Windows**.

## Files

| File | Role |
|---|---|
| `t3_voice.py` | Engine (microphone, playback, routing, status file) and the pywebview host |
| `ui/orb.html` | The orb and card: canvas animation, state palette, controls. Open with `?demo=1` for a design preview |
| `t3_voice_core.py` | Per-thread routing, streaming sentence feed, utterance gate, MCP sender, ASR client |
| `live_reader_core.py` | Read-only SQLite feed of T3 messages and Markdown-to-prose cleaning |
| `live_reader.py` | Earlier reader; the panel reuses its persistent audio device |
| `pair_t3.py` | Mints the MCP token through T3's pairing-code OAuth flow |
| `test_*.py` | `python -m unittest test_orb_logic test_t3_voice_core test_live_reader -q` runs 47 tests (SQLite fixtures, exact desktop routes, following/pinning, review confirmation, composer draft guards, delivery modes, dictation, capture suppression, toolbar sizing, visibility and bubble rules), no audio needed |

`t3-voice-token.txt`, settings, status and logs are git-ignored. The status file holds timings and counters only, never conversation text.

## Tuning

- Silence window: `UtteranceGate(start_frames=2, silence_frames=20)` in `t3_voice.py`. 20 ms per frame.
- Shorter than 300 ms starts splitting slow sentences into separate turns, which costs extra model usage.

## Cleanup model benchmark (OpenWhispr Dictation, 2026-11-01)

`bench_cleanup.py` runs OpenWhispr's cleanup prompt over five dictation samples against the app's llama-server (port 8221) and any GGUF paths you pass (each spawned on port 8231 with the bundled Vulkan build). RTX 4070 Laptop, 8 GB VRAM, with a game and the Unity editor also on the GPU:

| Model | Median per cleanup | Notes |
|---|---|---|
| gemma-4-E4B q4_0 (previous default) | ~3.2 s | 5 GB weights plus a 16k context left ~0.5 GB VRAM free; everything else spilled to system memory |
| Qwen3.5-2B Q4_K_M | ~0.45 s | Picked. Same corrections as gemma on 4 of 5 samples; took "new paragraph" literally once |
| Qwen3.5-0.8B Q4_K_M | ~0.33 s | Rejected: echoed the raw transcript on 3 of 5 samples and invented a sentence once |

Set `LOCAL_CLEANUP_MODEL=qwen3.5-2b-q4_k_m` in `%APPDATA%\OpenWhisprDictation\.env` with the GGUF in `~/.cache/openwhispr/models/`. On an 8 GB card, VRAM headroom matters more than model speed: a model that fits beside your other GPU work beats a bigger one that spills.
