# Maeve voice orb for T3 Code

A small always-on-top orb (frameless, transparent WebView2) that gives one [T3 Code](https://t3.chat) thread a voice, fully local. The orb breathes while listening, glows amber and swells with your voice, spins while transcribing and sending, and pulses violet to Maeve's speech. Click it for the card: thread picker, voice toggle, microphone mode, stop, options.

Two microphone modes:

- **Hands-free** (default): the orb owns the microphone. WebRTC VAD endpoints after 400 ms of silence; speaking again interrupts Maeve.
- **OpenWhispr hotkey**: dictate with OpenWhispr Dictation's own hotkey. Each completed dictation in OpenWhispr's local history is forwarded to the thread. OpenWhispr also pastes into the focused field, so keep T3's composer unfocused in this mode.

The loop:

1. You speak. WebRTC VAD endpoints the utterance after 500 ms of silence.
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

Click the orb, pick a thread, press **Voice on**, and talk. Stop with the Stop pill, Escape, or Ctrl+Alt+M. Options holds **Clean up with OpenWhispr's model** (sends the transcript through OpenWhispr's local llama-server first; costs its cleanup latency) and **Start with Windows**.

## Files

| File | Role |
|---|---|
| `t3_voice.py` | Engine (microphone, playback, routing, status file) and the pywebview host |
| `ui/orb.html` | The orb and card: canvas animation, state palette, controls. Open with `?demo=1` for a design preview |
| `t3_voice_core.py` | Per-thread routing, streaming sentence feed, utterance gate, MCP sender, ASR client |
| `live_reader_core.py` | Read-only SQLite feed of T3 messages and Markdown-to-prose cleaning |
| `live_reader.py` | Earlier reader; the panel reuses its persistent audio device |
| `pair_t3.py` | Mints the MCP token through T3's pairing-code OAuth flow |
| `test_*.py` | `python -m unittest -q` runs 15 tests against SQLite fixtures, no audio needed |

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
