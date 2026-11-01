"""Maeve voice orb for T3 Code: frameless transparent web view, hands-free or OpenWhispr-driven."""
import argparse
from collections import deque
import ctypes
from ctypes import wintypes
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
# Transparent page background, and keep timers running while the orb window is hidden so it
# reappears with current state. The env var replaces pywebview's own argument string.
os.environ['WEBVIEW2_DEFAULT_BACKGROUND_COLOR'] = '00000000'
os.environ['WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS'] = (
    '--disable-features=ElasticOverscroll --disable-background-timer-throttling '
    '--disable-renderer-backgrounding --disable-backgrounding-occluded-windows')
import numpy as np
import ptts
import sounddevice as sd
import webrtcvad
import webview

from diagnostics import write_status
from live_reader import ContinuousAudio
from live_reader_core import Message
from t3_voice_core import (DictationWatch, OpenWhisprFeed, Routes, StreamingFeed, UtteranceGate, cleanup_text,
                           list_threads, parse_hotkey, read_env, send_message, transcribe)

ROOT = Path(__file__).resolve().parent
DB = Path.home() / '.t3/userdata/statev2.sqlite'
RATE = 16000
FRAME = 320  # 20 ms at 16 kHz
COMPACT, BUBBLE, CARD = (180, 150), (340, 300), (320, 296)
BAR, BAR_BUBBLE, BAR_CARD = (200, 48), (340, 214), (320, 196)   # toolbar mode
OPENWHISPR_ENV = Path(os.environ.get('APPDATA', '')) / 'OpenWhisprDictation/.env'
LINGER = 1.2        # seconds the orb stays after the last reason to show it
FADE = 0.5          # seconds for the exit animation before the window is hidden

# A private handle: setting argtypes on ctypes.windll.user32 would change pywebview's own calls (drag).
user32 = ctypes.WinDLL('user32')
kernel32 = ctypes.WinDLL('kernel32')
gdi32 = ctypes.WinDLL('gdi32')
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_uint]
user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
user32.MonitorFromPoint.restype = wintypes.HMONITOR
HWND_TOPMOST = wintypes.HWND(-1)
SWP_NOACTIVATE, SWP_NOSIZE, SWP_NOMOVE, SWP_ASYNC = 0x10, 0x1, 0x2, 0x4000
SW_HIDE, SW_SHOWNOACTIVATE = 0, 4
EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)


def find_app_window(exe, title=None):
    """First visible, unowned top-level window of a process whose image ends with `exe`, or None."""
    found = []

    def visit(hwnd, _):
        if not user32.IsWindowVisible(hwnd) or user32.GetWindow(hwnd, 4) or not user32.GetWindowTextLengthW(hwnd):
            return True
        if title is not None:
            text = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, text, 256)
            if text.value != title:
                return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        handle = kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
        if handle:
            size = wintypes.DWORD(520)
            path = ctypes.create_unicode_buffer(520)
            ok = kernel32.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size))
            kernel32.CloseHandle(handle)
            if ok and path.value.lower().endswith(exe):
                found.append(hwnd)
                return False
        return True

    user32.EnumWindows(EnumWindowsProc(visit), 0)
    return found[0] if found else None


def find_t3_window():
    return find_app_window('t3 code (beta).exe')


def find_openwhispr_pill():
    return find_app_window('openwhispr dictation.exe', 'Voice Recorder')


def set_hidden_region(hwnd, hidden):
    """An empty window region hides OpenWhispr's pill without hiding the window, so Chromium keeps
    treating it as visible and never throttles the recorder that lives in it."""
    probe = gdi32.CreateRectRgn(0, 0, 0, 0)
    kind = user32.GetWindowRgn(hwnd, probe)
    gdi32.DeleteObject(probe)
    if hidden and kind != 1:  # 1 = NULLREGION
        user32.SetWindowRgn(hwnd, gdi32.CreateRectRgn(0, 0, 0, 0), True)
    elif not hidden and kind == 1:
        user32.SetWindowRgn(hwnd, None, True)


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
        self.hwnd = None
        self.size = COMPACT
        self.expanded = False
        self.hovered = False
        self.visible = False
        self.show_until = 0.0
        self.hide_at = None
        self.pin_until = 0.0
        self.sent_at = self.error_at = 0.0
        self.confirmed = False
        self.mic_muted = bool(self.prefs.get('micMuted', False))
        self.maeve_muted = bool(self.prefs.get('maeveMuted', False))
        self.t3_min = False
        self.t3_hwnd = None
        self.t3_scan_at = 0.0
        self.bubble = None
        self.bubble_seq = 0
        self.bubble_run = None
        self.bubble_until = 0.0
        self.silent = deque()
        self.silent_next = 0.0
        self.startup_cached = None
        # OpenWhispr dictation mirrored in the orb
        self.dock = bool(self.prefs.get('dock', False))
        self.hide_pill = bool(self.prefs.get('hidePill', True))
        self.pill_hwnd = None
        self.pill_scan_at = 0.0
        self.dict_keys = None
        self.dict_mode = 'push'
        self.env_read_at = 0.0
        self.dictating = False
        self.dict_state = ''          # '', 'dictating', 'processing', 'done', 'failed'
        self.dict_until = 0.0
        self.dict_quiet_until = 0.0
        self.dict_watch = DictationWatch()
        self.listening = False
        self.read_openwhispr_settings()
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
        if self.startup_cached is None:
            self.startup_cached = self.startup_enabled()
        show_bubble = self.bubble is not None and time.monotonic() < self.bubble_until and self.t3_min and not self.expanded
        state, text = self.state, self.text
        if self.dict_state:
            state, text = self.dict_state, (self.dict_error if self.dict_state == 'failed' else '')
        return {'state': state, 'text': text, 'mic': self.mic_level, 'out': self.out_level,
                'voiceOn': self.voice_on(), 'mode': self.mode, 'thread': self.thread or '', 'threadTitle': title,
                'threads': [{'id': t['id'], 'title': (t['title'] or '')[:60]} for t in self.threads[:40]],
                'detail': hint, 'cleanup': self.cleanup, 'startup': self.startup_cached,
                'openwhispr': self.openwhispr.available(), 'visible': self.visible,
                'micMuted': self.mic_muted, 'maeveMuted': self.maeve_muted, 'dock': self.dock,
                'hidePill': self.hide_pill, 'dictKey': self.prefs.get('dictKeyLabel', ''),
                'bubble': self.bubble if show_bubble else None}

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
        self.openwhispr.cursor = None  # never replay history after switching the target or mode
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
        self.startup_cached = None

    # ----- toolbar and OpenWhispr pill -----
    def toggle_dock(self):
        with self.lock:
            self.dock = not self.dock
            self.prefs.set('dock', self.dock)
            self.expanded = False
            self.show_until = time.monotonic() + LINGER
            if self.hwnd is not None:
                self.place(self.target_size())
            self.cue([587, 440] if self.dock else [440, 587], 50)

    def toggle_hide_pill(self):
        with self.lock:
            self.hide_pill = not self.hide_pill
            self.prefs.set('hidePill', self.hide_pill)
            self.manage_pill(force=True)

    def manage_pill(self, force=False):
        now = time.monotonic()
        if force or now >= self.pill_scan_at or (self.pill_hwnd and not user32.IsWindow(self.pill_hwnd)):
            if not (self.pill_hwnd and user32.IsWindow(self.pill_hwnd)):
                self.pill_hwnd = find_openwhispr_pill()
            self.pill_scan_at = now + 2.0
        if self.pill_hwnd:
            set_hidden_region(self.pill_hwnd, self.hide_pill and not self.quit.is_set())

    def read_openwhispr_settings(self):
        env = read_env(OPENWHISPR_ENV)
        label = env.get('DICTATION_KEY', '')
        self.dict_keys = parse_hotkey(label)
        self.dict_mode = 'tap' if env.get('ACTIVATION_MODE', 'push') == 'tap' else 'push'
        if label != self.prefs.get('dictKeyLabel'):
            self.prefs.set('dictKeyLabel', label)
        self.env_read_at = time.monotonic() + 5.0

    # ----- mutes -----
    def toggle_mic_mute(self):
        with self.lock:
            self.mic_muted = not self.mic_muted
            self.prefs.set('micMuted', self.mic_muted)
            self.pending = None
            self.confirmed = False
            self.update_mic()
            if self.state in ('hearing', 'transcribing'):
                self.set_state(self.idle_state())
            self.cue([392] if self.mic_muted else [523, 659], 55)

    def toggle_maeve_mute(self):
        with self.lock:
            self.maeve_muted = not self.maeve_muted
            self.prefs.set('maeveMuted', self.maeve_muted)
            if self.maeve_muted:
                self.stop()
                if self.state == 'speaking':
                    self.set_state(self.idle_state())
            else:
                self.silent.clear()
                if self.state == 'reading':
                    self.set_state(self.idle_state())
            self.cue([440, 330] if self.maeve_muted else [659, 784], 55)

    # ----- speech in -----
    def update_mic(self):
        self.listening = self.ready and self.voice_on() and self.mode == 'handsfree' and not self.mic_muted
        want = self.listening or (self.ready and self.dictating)
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

    def mic_callback(self, data, frames, timing, status):
        frame = bytes(data)
        if len(frame) != FRAME * 2:
            return
        samples = np.frombuffer(frame, dtype='<i2').astype('f4') / 32768
        self.mic_level = float(np.sqrt(np.mean(samples * samples)))
        if not self.listening or self.dictating or time.monotonic() < self.dict_quiet_until:
            if self.gate.frames is not None:
                self.gate.reset()  # OpenWhispr owns this speech; never also send it to T3
            return
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
            self.notice.put(('you', text))
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
            if ticket is None or self.mic_muted:
                continue
            self.stop()  # a new dictation always interrupts the current reply
            threading.Thread(target=self._forward, args=(text, ticket), daemon=True).start()

    def _forward(self, text, ticket):
        self.deliver_text(text, ticket, 0.0, time.perf_counter())

    # ----- speech out -----
    def hotkey(self):
        held = dict_held = False
        active = False
        user32 = ctypes.windll.user32
        while not self.quit.wait(.015):
            down = all(user32.GetAsyncKeyState(key) & 0x8000 for key in (0x11, 0x12, 0x4D))  # Ctrl+Alt+M
            if down and not held:
                self.notice.put(('hotkey', None))
            held = down
            keys = self.dict_keys
            dict_down = bool(keys) and all(user32.GetAsyncKeyState(key) & 0x8000 for key in keys)
            if self.dict_mode == 'push':
                if dict_down and not dict_held:
                    self.notice.put(('dict-start', None))
                elif dict_held and not dict_down:
                    self.notice.put(('dict-stop', None))
            elif dict_down and not dict_held:  # tap mode toggles
                active = not active
                self.notice.put(('dict-start' if active else 'dict-stop', None))
            dict_held = dict_down

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
                self.notice.put(('speaking', message))
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
                    self.pin_until = time.monotonic() + 3.0
                    self.text = 'Ready · Ctrl+Alt+M'
                elif kind == 'stop':
                    self.stop()
                    self.set_state('stopped')
                elif kind == 'dict-start':
                    if self.current or not self.jobs.empty():
                        self.stop()  # Maeve must not talk into the dictation
                    self.pending = None
                    self.dictating = True
                    self.dict_state = 'dictating'
                    self.update_mic()
                elif kind == 'dict-stop':
                    if self.dictating:
                        self.dictating = False
                        self.dict_state = 'processing'
                        self.dict_until = time.monotonic() + 12.0
                        self.dict_quiet_until = time.monotonic() + 0.6
                        self.update_mic()
                elif kind == 'hotkey':
                    if self.current or not self.jobs.empty() or self.state in ('speaking', 'reading'):
                        self.stop()
                        self.silent.clear()
                        self.set_state('stopped')
                    else:  # summon the orb, or dismiss it if it was summoned
                        now = time.monotonic()
                        self.pin_until = 0.0 if now < self.pin_until else now + 6.0
                elif kind == 'speech-start':
                    if self.pending:
                        self.pending['deadline'] = None  # continuation may be coming; keep holding
                    if not self.current and self.jobs.empty():
                        self.set_state('hearing')
                elif kind == 'speech-confirmed':
                    if self.current or not self.jobs.empty():
                        self.stop()  # barge-in only on real speech, never on a click or a breath
                    self.silent.clear()
                    self.confirmed = True
                    self.set_state('hearing')
                elif kind == 'speech-end':
                    self.set_state('transcribing')
                elif kind == 'transcript':
                    self.accept_transcript(*value)
                elif kind == 'sending':
                    self.set_state('sending')
                elif kind == 'discarded':
                    self.meta['utterancesDiscarded'] += 1
                    self.confirmed = False
                    self.set_state(self.idle_state())
                elif kind == 'sent':
                    words, asr_ms, total_ms = value
                    self.meta['utterancesSent'] += 1
                    self.meta.update(lastAsrMs=asr_ms, lastSendMs=total_ms)
                    self.set_state('waiting')
                    self.confirmed = False
                    self.sent_at = time.monotonic()
                    self.detail = 'Sent %d words · ASR %.0f ms · total %.0f ms' % (words, asr_ms, total_ms)
                    self.cue([784, 1047], 55)
                elif kind == 'you':
                    self.show_bubble('you', value, None, 3.0)
                elif kind == 'send-error':
                    self.error_at = time.monotonic()
                    self.confirmed = False
                    self.set_state('error', 'Send failed')
                    self.detail = value[:90]
                    self.meta['lastSendError'] = value
                    self.cue([220, 180], 90)
                elif kind == 'speaking':
                    self.set_state('speaking')
                    if value is not None and value.id != 'voice-test':
                        self.show_reply(value)
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
                    self.error_at = time.monotonic()
                    self.set_state('error', 'Reader error')
                    self.detail = value[:90]
                    self.meta['error'] = value
        except queue.Empty:
            pass
        self.dictation_tick()
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
                    if self.maeve_muted:
                        if self.t3_min:
                            self.silent.append(message)
                        continue
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
        self.meta.update(dock=self.dock, dictationState=self.dict_state, hidePill=self.hide_pill)
        if self.audio:
            self.meta.update(playedSamples=self.audio.played_samples, outputUnderflows=self.audio.output_underflows)
        write_status(ROOT / 't3-voice-status.json', self.meta)
        self.desktop_tick()

    # ----- OpenWhispr dictation -----
    dict_error = ''

    def dictation_tick(self):
        now = time.monotonic()
        if now >= self.env_read_at:
            self.read_openwhispr_settings()
        self.manage_pill()
        try:
            rows = self.dict_watch.poll()
        except Exception as exc:
            self.meta['dictationWatchError'] = type(exc).__name__
            rows = []
        if rows and self.dict_state in ('dictating', 'processing'):
            last = rows[-1]
            if last['status'] == 'completed' and last['text']:
                self.dict_state, self.dict_until = 'done', now + 0.9
                self.meta['lastDictationWords'] = len(last['text'].split())
            else:
                self.dict_state, self.dict_until = 'failed', now + 3.0
                self.dict_error = (last['error'] or 'Dictation failed')[:60]
        elif self.dict_state in ('processing', 'done', 'failed') and now >= self.dict_until:
            self.dict_state = ''

    # ----- bubble -----
    def show_bubble(self, who, text, run, seconds):
        now = time.monotonic()
        same = (who == 'maeve' and self.bubble and self.bubble['who'] == 'maeve' and run == self.bubble_run
                and now < self.bubble_until + LINGER)
        if same:
            joined = self.bubble['text'] + ' ' + text
            cut = max(0, len(joined) - 1200)
            self.bubble = dict(self.bubble, text=joined[cut:], new=max(0, len(self.bubble['text']) + 1 - cut))
            self.bubble_until = max(self.bubble_until, now + seconds)
        else:
            self.bubble_seq += 1
            self.bubble = {'id': self.bubble_seq, 'who': who, 'text': text[-1200:], 'new': 0}
            self.bubble_until = now + seconds
        self.bubble_run = run

    def show_reply(self, message):
        self.show_bubble('maeve', message.text, message.run, max(2.5, len(message.text.split()) / 2.8))

    # ----- desktop: T3 state, visibility, placement -----
    def target_size(self):
        bubble = self.t3_min and self.bubble is not None and time.monotonic() < self.bubble_until
        if self.dock:
            return BAR_CARD if self.expanded else BAR_BUBBLE if bubble else BAR
        return CARD if self.expanded else BUBBLE if bubble else COMPACT

    def wants_visible(self, now):
        if self.dock or self.dict_state or self.expanded or self.hovered or now < self.pin_until or self.pending:
            return True
        state = self.state
        if state in ('speaking', 'reading', 'transcribing', 'sending'):
            return True
        if state == 'hearing' and self.confirmed:
            return True
        if state == 'waiting' and now < self.sent_at + 2.5:
            return True
        if state == 'error' and now < self.error_at + 4.0:
            return True
        return self.t3_min and self.bubble is not None and now < self.bubble_until

    def desktop_tick(self):
        now = time.monotonic()
        if now >= self.t3_scan_at:
            if not (self.t3_hwnd and user32.IsWindow(self.t3_hwnd)):
                self.t3_hwnd = find_t3_window()
            self.t3_min = self.t3_hwnd is None or bool(user32.IsIconic(self.t3_hwnd))
            self.t3_scan_at = now + 0.25
        # Silent reading while Maeve is muted and T3 is minimized.
        if self.silent and now >= self.silent_next and not self.confirmed:
            message = self.silent.popleft()
            self.show_reply(message)
            self.set_state('reading')
            self.silent_next = now + max(2.0, len(message.text.split()) / 2.8)
        elif not self.silent and self.state == 'reading' and now >= self.silent_next:
            self.set_state(self.idle_state())
        if self.hwnd is None:
            return
        if self.wants_visible(now):
            self.show_until = now + LINGER
        visible = now < self.show_until
        if visible:
            self.hide_at = None
            self.place(self.target_size())
            if not self.visible:
                user32.SetWindowPos(self.hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                                    SWP_NOACTIVATE | SWP_NOMOVE | SWP_NOSIZE | SWP_ASYNC)
                user32.ShowWindowAsync(self.hwnd, SW_SHOWNOACTIVATE)
        elif self.visible:
            self.hide_at = now + FADE
        if not visible and self.hide_at and now >= self.hide_at:
            self.hide_at = None
            self.remember_anchor()
            user32.ShowWindowAsync(self.hwnd, SW_HIDE)
            if self.bubble and now > self.bubble_until:
                self.bubble = None
        self.visible = visible

    def scale(self):
        return (user32.GetDpiForWindow(self.hwnd) or 96) / 96

    def anchor(self):
        rect = wintypes.RECT()
        user32.GetWindowRect(self.hwnd, ctypes.byref(rect))
        return (rect.left + rect.right) // 2, rect.bottom

    def remember_anchor(self):
        cx, bottom = self.anchor()
        if [cx, bottom] != self.prefs.get('anchor'):
            self.prefs.set('anchor', [cx, bottom])

    def place(self, size, anchor=None):
        """Resize around a fixed bottom-centre anchor so the orb itself never jumps."""
        if size == self.size and anchor is None:
            return
        cx, bottom = anchor or self.anchor()
        scale = self.scale()
        width, height = int(size[0] * scale), int(size[1] * scale)
        user32.SetWindowPos(self.hwnd, HWND_TOPMOST, int(cx - width / 2), int(bottom - height), width, height,
                            SWP_NOACTIVATE | SWP_ASYNC)
        self.size = size

    def attach(self, hwnd):
        """Called once the native window exists: position it on the saved anchor or the work-area corner."""
        self.hwnd = hwnd
        saved = self.prefs.get('anchor')
        if not (saved and user32.MonitorFromPoint(wintypes.POINT(saved[0], saved[1] - 20), 0)):
            area = wintypes.RECT()
            user32.SystemParametersInfoW(0x30, 0, ctypes.byref(area), 0)
            scale = self.scale()
            saved = [area.right - int(120 * scale), area.bottom - int(8 * scale)]
        self.size = None
        self.place(self.target_size(), anchor=saved)
        self.visible = True  # navigation shows the window once; the normal fade hides it after the intro

    def set_hover(self, hovered):
        self.hovered = hovered

    def set_expanded(self, expanded):
        if self.hwnd is None or expanded == self.expanded:
            return
        self.expanded = expanded
        self.show_until = time.monotonic() + LINGER
        self.place(self.target_size())

    def close(self):
        self.quit.set()
        if self.pill_hwnd and user32.IsWindow(self.pill_hwnd):
            set_hidden_region(self.pill_hwnd, False)
        self.stop()
        if self.mic_stream:
            self.mic_stream.abort()
            self.mic_stream.close()
        if self.audio:
            self.audio.close()
        self.meta['state'] = 'closed'
        write_status(ROOT / 't3-voice-status.json', self.meta)
        if self.hwnd is not None:
            self.remember_anchor()
        if self.window is not None:
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

    def set_hover(self, hovered):
        self._engine.set_hover(bool(hovered))

    def toggle_mic_mute(self):
        self._engine.toggle_mic_mute()

    def toggle_maeve_mute(self):
        self._engine.toggle_maeve_mute()

    def toggle_dock(self):
        self._engine.toggle_dock()

    def toggle_hide_pill(self):
        self._engine.toggle_hide_pill()

    def quit(self):
        self._engine.close()


class MARGINS(ctypes.Structure):
    _fields_ = [('left', ctypes.c_int), ('right', ctypes.c_int), ('top', ctypes.c_int), ('bottom', ctypes.c_int)]


def make_transparent(window, engine):
    """Per-pixel alpha: extend the DWM frame over the whole window and turn off the system backdrop.

    WebView2 then composites its transparent page straight onto the desktop: no colour key, no fringe.
    """
    from System.Drawing import Color
    from System.Windows.Forms import MethodInvoker
    form = window.native

    def apply():
        form.BackColor = Color.Black
        hwnd = form.Handle.ToInt32()
        none = ctypes.c_int(1)  # DWMSBT_NONE
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 38, ctypes.byref(none), 4)
        margins = MARGINS(-1, -1, -1, -1)
        ctypes.windll.dwmapi.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(margins))
        engine.attach(hwnd)
    form.BeginInvoke(MethodInvoker(apply))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--thread', default=None)
    args = parser.parse_args()
    engine = Engine(args.thread)
    window = webview.create_window('Maeve', url=str(ROOT / 'ui/orb.html'), js_api=Api(engine),
                                   width=COMPACT[0], height=COMPACT[1], x=0, y=0, frameless=True,
                                   transparent=True, on_top=True, easy_drag=True, resizable=False, focus=False,
                                   min_size=(100, BAR[1]), background_color='#000000')
    engine.window = window
    window.events.closed += engine.close
    window.events.shown += lambda: make_transparent(window, engine)
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
