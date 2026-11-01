"""Maeve voice orb for T3 Code: frameless transparent web view, hands-free or OpenWhispr-driven."""
import argparse
import ctypes
import json
import math
import os
from pathlib import Path
import queue
import sys
import threading
import time

os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
import numpy as np
import ptts
import sounddevice as sd
import webrtcvad
import webview

from diagnostics import write_status
from live_reader import ContinuousAudio
from live_reader_core import Message
from t3_voice_core import (OpenWhisprFeed, Routes, StreamingFeed, UtteranceGate, cleanup_text, list_threads,
                           send_message, transcribe)

ROOT = Path(__file__).resolve().parent
DB = Path.home() / '.t3/userdata/statev2.sqlite'
RATE = 16000
FRAME = 320  # 20 ms at 16 kHz
SMALL, LARGE = (180, 150), (320, 296)


class Prefs:
    def __init__(self, path):
        self.path = Path(path)
        try:
            self.data = json.loads(self.path.read_text('utf-8'))
        except (OSError, ValueError):
            self.data = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.data, indent=2), 'utf-8')
        temporary.replace(self.path)


def tone(steps, ms=70, volume=0.12):
    """Short UI cue: a few sine notes, 24 kHz mono int16."""
    out = []
    for freq in steps:
        n = int(24000 * ms / 1000)
        t = np.arange(n) / 24000
        env = np.minimum(1, np.minimum(t, (n / 24000) - t) * 120)
        out.append(np.sin(2 * math.pi * freq * t) * env * volume)
    return (np.concatenate(out) * 32767).astype('<i2').tobytes()


class Engine:
    def __init__(self, thread=None):
        self.routes = Routes(ROOT / 't3-voice-settings.json')
        self.prefs = Prefs(ROOT / 't3-voice-prefs.json')
        self.threads = list_threads(DB)
        self.openwhispr = OpenWhisprFeed()
        self.lock = threading.RLock()
        self.notice = queue.Queue()
        self.jobs = queue.Queue(maxsize=256)
        self.cancel = threading.Event()
        self.quit = threading.Event()
        self.generation = 0
        self.current = None
        self.last_run = None
        self.ready = False
        self.audio = None
        self.feed = None
        self.thread = None
        self.mic_stream = None
        self.state = 'loading'
        self.text = ''
        self.detail = ''
        self.mic_level = 0.0
        self.out_level = 0.0
        self.pending = None  # unfinished fragment waiting for its continuation
        self.mode = self.prefs.get('mode', 'handsfree')
        self.cleanup = bool(self.prefs.get('cleanup', False))
        self.window = None
        self.expanded = False
        self.meta = {'pid': os.getpid(), 'state': 'loading', 'voice': 'Maeve', 'model': 'Phonon 31M',
                     'asr': 'parakeet-0.6b via sherpa ws:6006', 'chunksSpoken': 0, 'utterancesSent': 0,
                     'utterancesDiscarded': 0}
        initial = thread or self.prefs.get('thread') or next(
            (t['id'] for t in self.threads if self.routes.preferences.get(t['id'])), None)
        if initial is None and self.threads:
            initial = self.threads[0]['id']
        if initial:
            self.select(initial)
        threading.Thread(target=self.synthesize, daemon=True).start()
        threading.Thread(target=self.hotkey, daemon=True).start()
        threading.Thread(target=self.loop, daemon=True).start()

    # ----- state -----
    def set_state(self, state, text=''):
        self.state = state
        self.text = text
        self.meta['state'] = state

    def idle_state(self):
        return 'ready' if self.voice_on() else 'off'

    def voice_on(self):
        return bool(self.thread and self.routes.preferences.get(self.thread, False))

    def cue(self, steps, ms=70):
        if self.audio:
            self.audio.put(tone(steps, ms), self.audio.epoch, threading.Event())

    def snapshot(self):
        title = next((t['title'] for t in self.threads if t['id'] == self.thread), '')
        if self.mode == 'openwhispr' and not self.openwhispr.available():
            hint = 'OpenWhispr history not found. Use hands-free.'
        elif self.mode == 'openwhispr':
            hint = "OpenWhispr's hotkey dictates into this thread. Keep T3's composer unfocused."
        else:
            hint = self.detail or 'Stop: Ctrl+Alt+M or Esc. Headphones recommended.'
        return {'state': self.state, 'text': self.text, 'mic': self.mic_level, 'out': self.out_level,
                'voiceOn': self.voice_on(), 'mode': self.mode, 'thread': self.thread or '', 'threadTitle': title,
                'threads': [{'id': t['id'], 'title': (t['title'] or '')[:60]} for t in self.threads[:40]],
                'detail': hint, 'cleanup': self.cleanup, 'startup': self.startup_enabled(),
                'openwhispr': self.openwhispr.available()}

    # ----- routing -----
    def select(self, thread):
        with self.lock:
            self.stop()
            self.thread = thread
            self.routes.select(thread)
            self.feed = StreamingFeed(DB, thread)
            self.prefs.set('thread', thread)
            self.meta['threadId'] = thread
            self.after_route_change()

    def toggle_voice(self):
        with self.lock:
            if not self.thread:
                return
            self.stop()
            self.routes.enable(not self.voice_on())
            self.feed.discard_pending()
            self.after_route_change()
            self.cue([660, 880] if self.voice_on() else [440], 60)

    def toggle_mode(self):
        with self.lock:
            self.mode = 'openwhispr' if self.mode == 'handsfree' else 'handsfree'
            self.prefs.set('mode', self.mode)
            self.openwhispr.cursor = None
            self.after_route_change()

    def toggle_cleanup(self):
        self.cleanup = not self.cleanup
        self.prefs.set('cleanup', self.cleanup)

    def after_route_change(self):
        self.pending = None
        self.detail = ''
        if self.ready:
            self.set_state(self.idle_state())
        self.update_mic()

    # ----- startup -----
    RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'

    def startup_command(self):
        return '"%s" "%s"' % (Path(sys.executable).with_name('pythonw.exe'), ROOT / 't3_voice.py')

    def startup_enabled(self):
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.RUN_KEY) as key:
                return winreg.QueryValueEx(key, 'MaeveT3Voice')[0] == self.startup_command()
        except OSError:
            return False

    def toggle_startup(self):
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if self.startup_enabled():
                try:
                    winreg.DeleteValue(key, 'MaeveT3Voice')
                except OSError:
                    pass
            else:
                winreg.SetValueEx(key, 'MaeveT3Voice', 0, winreg.REG_SZ, self.startup_command())

    # ----- speech in -----
    def update_mic(self):
        want = self.ready and self.voice_on() and self.mode == 'handsfree'
        if want and self.mic_stream is None:
            self.vad = webrtcvad.Vad(3)
            self.gate = UtteranceGate(start_frames=2, silence_frames=20)  # 40 ms start, 400 ms end
            self.mic_stream = sd.RawInputStream(samplerate=RATE, channels=1, dtype='int16',
                                                blocksize=FRAME, latency='low', callback=self.mic_callback)
            self.mic_stream.start()
        elif not want and self.mic_stream is not None:
            self.mic_stream.abort()
            self.mic_stream.close()
            self.mic_stream = None
            self.mic_level = 0.0
        if self.mode == 'openwhispr':
            self.openwhispr.cursor = None  # position on the next poll; never replay history

    def mic_callback(self, data, frames, timing, status):
        frame = bytes(data)
        if len(frame) != FRAME * 2:
            return
        samples = np.frombuffer(frame, dtype='<i2').astype('f4') / 32768
        self.mic_level = float(np.sqrt(np.mean(samples * samples)))
        try:
            voiced = self.vad.is_speech(frame, RATE)
        except Exception:
            voiced = False
        for kind, audio in self.gate.push(frame, voiced):
            if kind == 'start':
                self.notice.put(('speech-start', None))
                continue
            if kind == 'confirm':
                self.notice.put(('speech-confirmed', None))
                continue
            ticket = self.routes.ticket()
            if ticket is None or self.gate.last_voiced < self.gate.confirm_frames:
                self.notice.put(('discarded', 'noise' if ticket else 'voice off'))
                continue
            self.notice.put(('speech-end', None))
            threading.Thread(target=self.deliver_audio, args=(audio, ticket), daemon=True).start()

    def deliver_audio(self, audio, ticket):
        started = time.perf_counter()
        try:
            text = transcribe(audio, RATE)
            asr_ms = (time.perf_counter() - started) * 1000
            if not text or not self.routes.current(ticket):
                self.notice.put(('discarded', 'empty' if not text else 'target changed'))
                return
            self.notice.put(('transcript', (text, ticket, asr_ms, started)))
        except Exception as exc:
            self.notice.put(('send-error', type(exc).__name__ + ': ' + str(exc)[:120]))

    HOLD_SECONDS = 0.9

    def accept_transcript(self, text, ticket, asr_ms, started):
        """A sentence goes at once; a fragment waits briefly for its continuation and is merged."""
        if self.pending and self.pending['ticket'] == ticket:
            text = self.pending['text'] + ' ' + text
            asr_ms += self.pending['asr']
            started = self.pending['started']
        self.pending = None
        complete = text.rstrip().endswith(('.', '?', '!')) or len(text.split()) >= 14
        if complete:
            self.dispatch(text, ticket, asr_ms, started)
        else:
            self.pending = {'text': text, 'ticket': ticket, 'asr': asr_ms, 'started': started,
                            'deadline': time.monotonic() + self.HOLD_SECONDS}
            self.set_state('ready', '…')

    def dispatch(self, text, ticket, asr_ms, started):
        threading.Thread(target=self.deliver_text, args=(text, ticket, asr_ms, started), daemon=True).start()

    def deliver_text(self, text, ticket, asr_ms, started):
        try:
            if self.cleanup:
                text = cleanup_text(text)
            self.notice.put(('sending', None))
            send_message(ticket.thread, text)
            self.notice.put(('sent', (len(text.split()), asr_ms, (time.perf_counter() - started) * 1000)))
        except Exception as exc:
            self.notice.put(('send-error', type(exc).__name__ + ': ' + str(exc)[:120]))

    def forward_openwhispr(self):
        try:
            texts = self.openwhispr.poll()
        except Exception as exc:
            self.meta['openwhisprError'] = type(exc).__name__
            return
        for text in texts:
            ticket = self.routes.ticket()
            if ticket is None:
                continue
            self.stop()  # a new dictation always interrupts the current reply
            threading.Thread(target=self._forward, args=(text, ticket), daemon=True).start()

    def _forward(self, text, ticket):
        self.deliver_text(text, ticket, 0.0, time.perf_counter())

    # ----- speech out -----
    def hotkey(self):
        held = False
        user32 = ctypes.windll.user32
        while not self.quit.wait(.025):
            down = all(user32.GetAsyncKeyState(key) & 0x8000 for key in (0x11, 0x12, 0x4D))  # Ctrl+Alt+M
            if down and not held:
                self.notice.put(('stop', None))
            held = down

    def stop(self):
        if self.audio:
            with self.audio.cv:
                self._stop_locked()
        else:
            self._stop_locked()

    def _stop_locked(self):
        self.generation += 1
        self.cancel.set()
        if self.feed:
            if self.current:
                self.feed.suppress(self.current.run)
            if self.last_run:
                self.feed.suppress(self.last_run)
            self.feed.suppress_current()
        while True:
            try:
                self.jobs.get_nowait()
            except queue.Empty:
                break
        if self.audio:
            self.audio.reset()
        self.out_level = 0.0

    def test_voice(self):
        if self.ready:
            self.jobs.put_nowait((Message('voice-test', 'voice-test-' + str(time.monotonic()),
                'Hello. I am Maeve. Speak, and I will send it to this thread and read the reply.'), self.generation))

    def synthesize(self):
        try:
            ptts.set_num_threads(4)
            cache = Path.home() / '.cache/huggingface/hub'
            model = cache / 'models--gradium--phonon-31m-en/snapshots/8c64b55ec301728e2d1695bfea87a08a267d0c2d'
            voice = list((cache / 'models--gradium--phonon-voices/snapshots').glob('*/voices/6PWnV0Nq4wu7RVBT.safetensors'))
            if not voice:
                raise FileNotFoundError('The cached Maeve voice is missing.')
            tts = ptts.TTS(model=str(model), lang='en', device='cpu')
            tts.add_voice('Maeve', str(voice[0]))
            with tts.stream('Ready.', voice='Maeve') as warmup:
                for _ in warmup:
                    pass
            self.audio = ContinuousAudio()
            self.notice.put(('ready', None))
            while not self.quit.is_set():
                try:
                    message, generation = self.jobs.get(timeout=.05)
                except queue.Empty:
                    continue
                with self.audio.cv:
                    if (self.feed and message.run in self.feed.suppressed) or generation != self.generation:
                        continue
                    self.current = message
                    self.cancel = threading.Event()
                    cancel = self.cancel
                    epoch = self.audio.epoch
                self.notice.put(('speaking', None))
                start = time.perf_counter()
                first = None
                with tts.stream(message.text, voice='Maeve') as stream:
                    for chunk in stream:
                        if cancel.is_set() or self.quit.is_set():
                            break
                        if first is None:
                            first = (time.perf_counter() - start) * 1000
                            self.notice.put(('first-audio', first))
                        clipped = np.clip(chunk, -1, 1)
                        self.out_level = float(np.sqrt(np.mean(clipped * clipped)))
                        pcm = (clipped * 32767).astype('<i2').tobytes()
                        if not self.audio.put(pcm, epoch, cancel):
                            break
                self.audio.drain(epoch, cancel)
                self.out_level = 0.0
                self.current = None
                self.notice.put(('done', not cancel.is_set()))
        except Exception as exc:
            self.notice.put(('error', type(exc).__name__ + ': ' + str(exc)))

    # ----- loop -----
    def loop(self):
        while not self.quit.is_set():
            try:
                with self.lock:
                    self.tick()
            except Exception as exc:
                self.meta['loopError'] = type(exc).__name__
            time.sleep(.04)

    def tick(self):
        try:
            while True:
                kind, value = self.notice.get_nowait()
                if kind == 'ready':
                    self.ready = True
                    if self.feed:
                        self.feed.discard_pending()
                    self.set_state(self.idle_state())
                    self.update_mic()
                    self.cue([523, 784], 60)
                elif kind == 'stop':
                    self.stop()
                    self.set_state('stopped')
                elif kind == 'speech-start':
                    if self.pending:
                        self.pending['deadline'] = None  # continuation may be coming; keep holding
                    if not self.current and self.jobs.empty():
                        self.set_state('hearing')
                elif kind == 'speech-confirmed':
                    if self.current or not self.jobs.empty():
                        self.stop()  # barge-in only on real speech, never on a click or a breath
                    self.set_state('hearing')
                elif kind == 'speech-end':
                    self.set_state('transcribing')
                elif kind == 'transcript':
                    self.accept_transcript(*value)
                elif kind == 'sending':
                    self.set_state('sending')
                elif kind == 'discarded':
                    self.meta['utterancesDiscarded'] += 1
                    self.set_state(self.idle_state())
                elif kind == 'sent':
                    words, asr_ms, total_ms = value
                    self.meta['utterancesSent'] += 1
                    self.meta.update(lastAsrMs=asr_ms, lastSendMs=total_ms)
                    self.set_state('waiting')
                    self.detail = 'Sent %d words · ASR %.0f ms · total %.0f ms' % (words, asr_ms, total_ms)
                    self.cue([784, 1047], 55)
                elif kind == 'send-error':
                    self.set_state('error', 'Send failed')
                    self.detail = value[:90]
                    self.meta['lastSendError'] = value
                    self.cue([220, 180], 90)
                elif kind == 'speaking':
                    self.set_state('speaking')
                elif kind == 'first-audio':
                    self.meta['lastFirstAudioMs'] = value
                    self.detail = self.detail.split(' · voice')[0] + ' · voice %.0f ms' % value
                elif kind == 'done':
                    if value:
                        self.meta['chunksSpoken'] += 1
                    if self.jobs.empty():
                        self.set_state(self.idle_state())
                elif kind == 'error':
                    self.ready = False
                    self.set_state('error', 'Reader error')
                    self.detail = value[:90]
                    self.meta['error'] = value
        except queue.Empty:
            pass
        if self.pending and self.pending['deadline'] and time.monotonic() >= self.pending['deadline']                 and self.state not in ('hearing', 'transcribing'):
            fragment = self.pending
            self.pending = None
            self.dispatch(fragment['text'], fragment['ticket'], fragment['asr'], fragment['started'])
        if self.pending and self.pending['deadline'] is None and self.state == 'ready':
            self.pending['deadline'] = time.monotonic() + self.HOLD_SECONDS  # the continuation was dropped
        try:
            if self.ready and self.feed and self.voice_on():
                for message in self.feed.poll():
                    self.last_run = message.run
                    self.jobs.put_nowait((message, self.generation))
                if self.mode == 'openwhispr' and self.openwhispr.available():
                    self.forward_openwhispr()
        except queue.Full:
            self.stop()
            self.set_state('error', 'Speech queue filled')
        except Exception as exc:
            self.meta['connectionError'] = type(exc).__name__
        self.meta['updatedAt'] = time.time()
        self.meta['mode'] = self.mode
        if self.audio:
            self.meta.update(playedSamples=self.audio.played_samples, outputUnderflows=self.audio.output_underflows)
        write_status(ROOT / 't3-voice-status.json', self.meta)

    # ----- window -----
    def set_expanded(self, expanded):
        if self.window is None or expanded == self.expanded:
            return
        self.expanded = expanded
        x, y = self.window.x, self.window.y
        if expanded:
            self.window.move(x - (LARGE[0] - SMALL[0]) // 2, y - (LARGE[1] - SMALL[1]))
            self.window.resize(*LARGE)
        else:
            self.window.resize(*SMALL)
            self.window.move(x + (LARGE[0] - SMALL[0]) // 2, y + (LARGE[1] - SMALL[1]))
            self.prefs.set('pos', [self.window.x, self.window.y])

    def close(self):
        self.quit.set()
        self.stop()
        if self.mic_stream:
            self.mic_stream.abort()
            self.mic_stream.close()
        if self.audio:
            self.audio.close()
        self.meta['state'] = 'closed'
        write_status(ROOT / 't3-voice-status.json', self.meta)
        if self.window is not None:
            if not self.expanded:
                self.prefs.set('pos', [self.window.x, self.window.y])
            self.window.destroy()


class Api:
    """Exposed to the page as pywebview.api."""
    def __init__(self, engine):
        self._engine = engine

    def poll(self):
        return self._engine.snapshot()

    def select(self, thread):
        self._engine.select(thread)

    def toggle_voice(self):
        self._engine.toggle_voice()

    def toggle_mode(self):
        self._engine.toggle_mode()

    def toggle_cleanup(self):
        self._engine.toggle_cleanup()

    def toggle_startup(self):
        self._engine.toggle_startup()

    def stop(self):
        self._engine.notice.put(('stop', None))

    def test_voice(self):
        self._engine.test_voice()

    def set_expanded(self, expanded):
        self._engine.set_expanded(bool(expanded))

    def quit(self):
        self._engine.close()


def make_transparent(window):
    """WebView2 paints transparent; the WinForms host still needs a colour key to let the desktop through."""
    try:
        from System.Drawing import Color
        from System.Windows.Forms import MethodInvoker
        form = window.native

        def apply():
            form.BackColor = Color.FromArgb(1, 2, 3)
            form.TransparencyKey = Color.FromArgb(1, 2, 3)
        form.BeginInvoke(MethodInvoker(apply))
        time.sleep(.3)
        window.resize(*SMALL)
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--thread', default=None)
    args = parser.parse_args()
    engine = Engine(args.thread)
    user32 = ctypes.windll.user32
    sw, sh = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    x, y = engine.prefs.get('pos') or [sw - SMALL[0] - 24, sh - SMALL[1] - 70]
    window = webview.create_window('Maeve', url=str(ROOT / 'ui/orb.html'), js_api=Api(engine),
                                   width=SMALL[0], height=SMALL[1], x=int(x), y=int(y), frameless=True,
                                   transparent=True, on_top=True, easy_drag=True, resizable=False,
                                   min_size=(100, 100), background_color='#010203')
    engine.window = window
    window.events.closed += engine.close
    window.events.shown += lambda: threading.Thread(target=make_transparent, args=(window,), daemon=True).start()
    webview.start(gui='edgechromium', private_mode=True)


if __name__ == '__main__':
    kernel = ctypes.windll.kernel32
    kernel.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel.CreateMutexW(None, True, 'Local\\MaeveT3Voice')
    if kernel.GetLastError() != 183:
        try:
            main()
        finally:
            kernel.CloseHandle(ctypes.c_void_p(handle))
