# T3 voice panel (Maeve)

Hands-free voice loop for one [T3 Code](https://t3.chat) thread, fully local:

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

Pick a thread, tick **Voice on for this thread**, and talk. Stop with the button, Escape, or Ctrl+Alt+Space.

## Files

| File | Role |
|---|---|
| `t3_voice.py` | The Tk panel: thread picker, microphone, playback, status file |
| `t3_voice_core.py` | Per-thread routing, streaming sentence feed, utterance gate, MCP sender, ASR client |
| `live_reader_core.py` | Read-only SQLite feed of T3 messages and Markdown-to-prose cleaning |
| `live_reader.py` | Earlier reader; the panel reuses its persistent audio device |
| `pair_t3.py` | Mints the MCP token through T3's pairing-code OAuth flow |
| `test_*.py` | `python -m unittest -q` runs 15 tests against SQLite fixtures, no audio needed |

`t3-voice-token.txt`, settings, status and logs are git-ignored. The status file holds timings and counters only, never conversation text.

## Tuning

- Silence window: `UtteranceGate(start_frames=3, silence_frames=25)` in `t3_voice.py`. 20 ms per frame.
- Shorter than 300 ms starts splitting slow sentences into separate turns, which costs extra model usage.
