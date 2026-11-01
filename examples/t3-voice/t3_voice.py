"""Maeve voice orb for T3 Code: one transparent UI for held OpenWhispr dictation and replies."""
import argparse
from collections import deque
import ctypes
from ctypes import wintypes
import json
import math
import os
from pathlib import Path
import queue
import sqlite3
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
from t3_voice_core import (DictationPreview, DictationWatch, VoiceFx, matching_user_submission, read_agent_activity, audio_device_choices, resolve_audio_device, OpenWhisprFeed, Routes, StreamingFeed, UtteranceGate, cleanup_text,
                           audio_feedback, list_threads, parse_hotkey, parse_thread_url, read_env, send_message, transcribe)

ROOT = Path(__file__).resolve().parent
DB = Path.home() / '.t3/userdata/statev2.sqlite'
RATE = 16000
FRAME = 320  # 20 ms at 16 kHz
COMPACT, BUBBLE, CARD = (180, 150), (340, 300), (320, 360)
BAR, BAR_BUBBLE, BAR_CARD = (200, 48), (340, 214), (320, 270)   # toolbar mode
OPENWHISPR_ENV = Path(os.environ.get('APPDATA', '')) / 'OpenWhisprDictation/.env'
LINGER = 1.2        # seconds the orb stays after the last reason to show it
FADE = 0.5          # seconds for the exit animation before the window is hidden
BUBBLE_FADE = 0.35  # keep native bounds while the page finishes its 180 ms bubble exit

# A private handle: setting argtypes on ctypes.windll.user32 would change pywebview's own calls (drag).
user32 = ctypes.WinDLL('user32')
kernel32 = ctypes.WinDLL('kernel32')
gdi32 = ctypes.WinDLL('gdi32')
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
gdi32.CreateRectRgn.restype = wintypes.HANDLE
gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
user32.GetWindowRgn.argtypes = [wintypes.HWND, wintypes.HANDLE]
user32.SetWindowRgn.argtypes = [wintypes.HWND, wintypes.HANDLE, wintypes.BOOL]
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_uint]
user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
user32.MonitorFromPoint.restype = wintypes.HMONITOR
HWND_TOPMOST = wintypes.HWND(-1)
SWP_NOACTIVATE, SWP_NOSIZE, SWP_NOMOVE, SWP_ASYNC = 0x10, 0x1, 0x2, 0x4000
SW_HIDE, SW_SHOWNOACTIVATE = 0, 4
EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)


def find_app_windows(exe, title=None, overlays=False):
    """Match process identity as well as title; recorder overlays may have owners."""
    found = []

    def visit(hwnd, _):
        if (not user32.IsWindowVisible(hwnd) or (not overlays and user32.GetWindow(hwnd, 4))
                or not user32.GetWindowTextLengthW(hwnd)):
            return True
        text = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, text, 256)
        if overlays and not is_dictation_overlay(text.value, user32.GetWindowLongW(hwnd, -16), user32.GetWindowLongW(hwnd, -20)):
            return True
        if title is not None:
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
        return True

    user32.EnumWindows(EnumWindowsProc(visit), 0)
    return found


def find_app_window(exe, title=None):
    windows = find_app_windows(exe, title)
    return windows[0] if windows else None


def find_t3_window():
    return find_app_window('t3 code (beta).exe')


def is_dictation_overlay(title, style, exstyle):
    return title == 'Voice Recorder' or (title in ('OpenWhispr', 'OpenWhispr Dictation')
            and not style & 0x00C00000 and bool(exstyle & 0x08000000))


def find_openwhispr_pills():
    return find_app_windows('openwhispr dictation.exe', overlays=True)


def set_hidden_region(hwnd, hidden):
    """An empty window region hides OpenWhispr's pill without hiding the window, so Chromium keeps
    treating it as visible and never throttles the recorder that lives in it."""
    probe = gdi32.CreateRectRgn(0, 0, 0, 0)
    kind = user32.GetWindowRgn(hwnd, probe)
    gdi32.DeleteObject(probe)
    if hidden and kind != 1:  # 1 = NULLREGION
        region = gdi32.CreateRectRgn(0, 0, 0, 0)
        if not user32.SetWindowRgn(hwnd, region, True):
            gdi32.DeleteObject(region)
    elif not hidden and kind == 1:
        user32.SetWindowRgn(hwnd, None, True)


def clamp_anchor(anchor, size, area):
    cx, bottom = anchor
    width, height = size
    left, top, right, edge_bottom = area
    return max(left + width/2, min(cx, right-width/2)), max(top+height, min(bottom, edge_bottom))


class MONITORINFO(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('monitor', wintypes.RECT), ('work', wintypes.RECT), ('flags', wintypes.DWORD)]


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
        self.mic_bands = [0.0]*11
        self.mic_peak = 0.0
        self.out_level = 0.0
        self.pending = None  # unfinished fragment waiting for its continuation
        self.mode = 'openwhispr'  # hold/release defines turns; never listen continuously
        self.prefs.set('mode', self.mode)
        self.cleanup = bool(self.prefs.get('cleanup', False))
        self.high_contrast = bool(self.prefs.get('highContrast', False))
        self.reduced_motion = bool(self.prefs.get('reducedMotion', False))
        self.agent = {}
        self.agent_poll_at = 0.0
        self.visual_events = {'sent': 0, 'interrupt': 0}
        self.synthesis_done_run = ''
        self.settled_feed_run = ''
        self.voice_fx = bool(self.prefs.get('voiceFx', True))   # Techno audio effect: interface EQ, sheen and plate reverb
        self.fx = VoiceFx()
        self.mic_device = self.prefs.get('micDevice', '')          # '' = system default
        self.speaker_device = self.prefs.get('speakerDevice', '')
        self.choosing_delivery = False
        self.expanded_at = 0.0
        self.card_focused = False
        self.outside_since = None
        self.window = None
        self.hwnd = None
        self.size = COMPACT
        self.viewport_target = COMPACT
        self.expanded = False
        self.panel_extra = False
        self.hovered = False
        self.visible = False
        self.show_until = 0.0
        self.hide_at = None
        self.bubble_layout_until = 0.0
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
        self.hide_pill = True
        self.pill_hwnds = set()
        self.pill_scan_at = 0.0
        self.dict_keys = None
        self.dict_mode = 'push'
        self.env_read_at = 0.0
        self.dictating = False
        self.dict_state = ''          # '', 'dictating', 'processing', 'done', 'failed'
        self.dict_until = 0.0
        self.dict_quiet_until = 0.0
        self.dict_watch = DictationWatch()
        self.dict_preview = DictationPreview()
        self.dict_preview_session = 0
        self.dict_preview_text = ''
        self.dict_preview_until = 0.0
        self.listening = False
        self.follow_active = bool(self.prefs.get('followActive', True))
        self.active_thread = None
        self.capture_ticket = None
        self.asr_pending = 0
        self.asr_lock = threading.Lock()
        self.delivery = self.prefs.get('delivery', 'immediate')
        self.review = None
        self.review_seq = 0
        self.review_poll_at = 0.0
        self.dictation_started_wall = 0.0
        self.read_openwhispr_settings()
        self.meta = {'pid': os.getpid(), 'state': 'loading', 'voice': 'Maeve', 'model': 'Phonon 31M',
                     'asr': 'parakeet-0.6b via sherpa ws:6006', 'chunksSpoken': 0, 'utterancesSent': 0,
                     'utterancesDiscarded': 0}
        initial = thread or self.prefs.get('thread') or next(
            (t['id'] for t in self.threads if self.routes.preferences.get(t['id'])), None)
        if initial is None and self.threads:
            initial = self.threads[0]['id']
        if initial:
            self.select(initial, automatic=True)
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
        if self.follow_active and self.active_thread is None:
            return False
        return bool(self.thread and self.routes.preferences.get(self.thread, False))

    def watch_active_thread(self):
        """Read only the T3 document URL. UI Automation stays off the audio and engine threads."""
        try:
            import clr
            wpf = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Microsoft.NET/Framework64/v4.0.30319/WPF'
            clr.AddReference(str(wpf / 'UIAutomationClient.dll'))
            clr.AddReference(str(wpf / 'UIAutomationTypes.dll'))
            from System import IntPtr
            from System.Windows.Automation import AutomationElement, ControlType, PropertyCondition, TreeScope, ValuePattern
            environment = (Path.home() / '.t3/userdata/environment-id').read_text().strip()
            condition = PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.Document)
            while not self.quit.wait(.12):
                target = None
                try:
                    hwnd = find_t3_window()
                    if hwnd:
                        root = AutomationElement.FromHandle(IntPtr(hwnd))
                        docs = root.FindAll(TreeScope.Descendants, condition)
                        for doc in docs:
                            pattern = doc.GetCurrentPattern(ValuePattern.Pattern)
                            thread = parse_thread_url(str(pattern.Current.Value), environment)
                            if thread:
                                with sqlite3.connect(DB.resolve().as_uri() + '?mode=ro', uri=True, timeout=.05) as db:
                                    row = db.execute('SELECT thread_id,title FROM orchestration_v2_projection_threads '
                                                     'WHERE thread_id=? AND deleted_at IS NULL AND archived_at IS NULL',
                                                     (thread,)).fetchone()
                                if row:
                                    target = {'id': row[0], 'title': row[1]}
                                    break
                    self.notice.put(('active-thread', target))
                except Exception as exc:
                    self.notice.put(('active-thread-error', type(exc).__name__))
        except Exception as exc:
            self.notice.put(('active-thread-error', type(exc).__name__))

    def follow_tick(self):
        if not self.follow_active or not self.active_thread or self.active_thread['id'] == self.thread:
            return
        if (self.review or self.dict_state in ('dictating', 'processing') or self.pending
                or self.state in ('hearing', 'transcribing', 'sending')
                or getattr(getattr(self, 'gate', None), 'frames', None) is not None):
            return
        self.select(self.active_thread['id'], automatic=True)

    def toggle_follow_active(self):
        with self.lock:
            self.follow_active = not self.follow_active
            self.prefs.set('followActive', self.follow_active)
            self.follow_tick()
            self.update_mic()

    def set_delivery(self, mode):
        if mode in ('immediate', 'review', 'composer'):
            with self.lock:
                self.delivery = mode
                self.prefs.set('delivery', mode)

    def set_review_focus(self, active):
        if not self.window or not self.hwnd:
            return
        from System.Windows.Forms import MethodInvoker
        def apply():
            self.window.focus = active
            style = user32.GetWindowLongW(self.hwnd, -20)
            user32.SetWindowLongW(self.hwnd, -20, style & ~0x08000000 if active else style | 0x08000000)
            if active:
                self.window.native.Activate()
                self.window.native.browser.webview.Focus()
        self.window.native.BeginInvoke(MethodInvoker(apply))

    def update_review_text(self, review_id, text, revision):
        with self.lock:
            draft = self.review
            if (not draft or draft['id'] != review_id or draft.get('sending')
                    or revision <= draft.get('editVersion',0)):
                return
            draft['text'] = text
            draft['editVersion'] = revision

    def confirm_review(self, review_id, text):
        with self.lock:
            if not self.review or self.review['id'] != review_id or self.review.get('sending') or not text.strip():
                return
            self.review['text'] = text.strip()
            self.reconcile_direct_submission(force=True)
            if self.review is None:
                return
            draft = self.review
            draft.update(text=text.strip(), sending=True, error='')
            self.review_sending_id = review_id
            self.set_state('sending')
            self.update_mic()
            self.dispatch(text.strip(), draft['ticket'], draft['asr'], draft['started'], approved=True)

    def cancel_review(self):
        with self.lock:
            if self.review and self.review.get('sending'):
                return
            self.review = None
            self.set_review_focus(False)
            self.set_state(self.idle_state())
            self.update_mic()

    def reconcile_direct_submission(self, force=False):
        draft = self.review
        now = time.monotonic()
        if (not draft or draft.get('sending') or self.dictating or (not force and now < self.review_poll_at)
                or not draft.get('ticket') or not draft.get('text')):
            return
        self.review_poll_at = now + .35
        if not matching_user_submission(DB,draft['ticket'].thread,draft['text'],draft.get('since',time.time())):
            return
        self.review = None
        self.pending = None
        self.dict_preview_text = ''
        self.dict_preview_until = 0.0
        self.dict_state = ''
        self.dict_until = 0.0
        self.set_review_focus(False)
        self.set_state(self.idle_state())
        self.meta['directSubmissions'] = self.meta.get('directSubmissions',0)+1
        self.visual_events['sent'] += 1
        self.update_mic()

    def finish_review(self, error=None):
        if not self.review or self.review['id'] != getattr(self, 'review_sending_id', None):
            return
        self.review_sending_id = None
        if error:
            self.review.update(sending=False, error=error)
            self.set_review_focus(True)
        else:
            self.review = None
            self.set_review_focus(False)
        self.update_mic()

    def draft_in_composer(self, ticket, text):
        """Semantic accessibility edit, never keystrokes or a clipboard paste into an arbitrary app."""
        from System import IntPtr
        from System.Windows.Automation import AutomationElement, ControlType, PropertyCondition, TreeScope, ValuePattern
        hwnd = find_t3_window()
        if not hwnd:
            raise RuntimeError('Open the destination thread in T3 to insert a draft.')
        root = AutomationElement.FromHandle(IntPtr(hwnd))
        docs = root.FindAll(TreeScope.Descendants, PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.Document))
        environment = (Path.home() / '.t3/userdata/environment-id').read_text().strip()
        for doc in docs:
            url = str(doc.GetCurrentPattern(ValuePattern.Pattern).Current.Value)
            if parse_thread_url(url, environment) != ticket.thread:
                continue
            edits = doc.FindAll(TreeScope.Descendants, PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.Edit))
            editors = [edit for edit in edits if 'composer-tiptap' in str(edit.Current.ClassName).split()]
            if len(editors) != 1:
                break
            editor = editors[0]
            value = editor.GetCurrentPattern(ValuePattern.Pattern)
            previous = str(value.Current.Value)
            if self.mode == 'openwhispr' and previous.rstrip().endswith(text):
                return  # OpenWhispr may already have pasted this dictation into the composer.
            if not previous.strip():
                previous = ''
            draft = (previous + '\n\n' if previous else '') + text
            # Recheck both route and user mute/selection before the mutation.
            if (parse_thread_url(str(doc.GetCurrentPattern(ValuePattern.Pattern).Current.Value), environment) != ticket.thread
                    or not self.routes.current(ticket)):
                break
            value.SetValue(draft)
            if str(value.Current.Value).strip().replace('\r\n', '\n') != draft.strip().replace('\r\n', '\n'):
                raise RuntimeError('T3 did not confirm the draft text. Nothing was sent.')
            if user32.GetForegroundWindow() == hwnd:
                editor.SetFocus()
            return
        raise RuntimeError('Open the captured destination thread in T3 first. Nothing was sent.')

    def cue(self, steps, ms=70):
        if self.audio:
            self.audio.put(tone(steps, ms), self.audio.epoch, threading.Event())

    def snapshot(self):
        title = next((t['title'] for t in self.threads if t['id'] == self.thread), '')
        if self.mode == 'openwhispr' and not self.openwhispr.available():
            hint = 'OpenWhispr history not found. Start OpenWhispr Dictation.'
        elif self.mode == 'openwhispr':
            hint = "OpenWhispr's hotkey dictates into this thread. Keep T3's composer unfocused."
        else:
            hint = self.detail or 'Stop: Ctrl+Alt+M or Esc. Headphones recommended.'
        if self.follow_active:
            routing_hint = 'Following open T3 thread' if self.active_thread else 'Open a local T3 thread to speak to it'
            hint = (self.detail + ' · ' if self.detail else '') + routing_hint
        else:
            hint = 'Pinned thread · ' + hint
        if self.startup_cached is None:
            self.startup_cached = self.startup_enabled()
        now = time.monotonic()
        show_bubble = self.reply_bubble_visible(now)
        state, text = self.state, self.text
        if self.dict_state:
            state, text = self.dict_state, (self.dict_error if self.dict_state == 'failed' else '')
        return {'agent': self.agent, 'visualEvents': dict(self.visual_events),
                'highContrast': self.high_contrast, 'reducedMotion': self.reduced_motion,
                'playback': self.audio.playback_progress() if self.audio else None,
                'state': state, 'text': text, 'mic': self.mic_level, 'out': self.audio.level if self.audio else 0.0,
                'micBands': self.mic_bands, 'outBands': self.audio.spectrum if self.audio else [0.0]*11,
                'speaking': self.current is not None and not self.maeve_muted,
                'voiceOn': self.voice_on(), 'mode': self.mode, 'thread': self.thread or '', 'threadTitle': title,
                'threads': [{'id': t['id'], 'title': (t['title'] or '')[:60]} for t in self.threads[:40]],
                'detail': hint, 'cleanup': self.cleanup, 'startup': self.startup_cached,
                'openwhispr': self.openwhispr.available(), 'visible': self.visible,
                'micMuted': self.mic_muted, 'maeveMuted': self.maeve_muted, 'dock': self.dock,
                'hidePill': self.hide_pill, 'dictKey': self.prefs.get('dictKeyLabel', ''),
                'dictActivation': self.dict_mode,
                'followActive': self.follow_active,
                'expanded': self.expanded, 'hovered': self.hovered,
                'viewportTarget': list(self.viewport_target),
                'voiceFx': self.voice_fx,
                'delivery': self.delivery,
                'review': {key: self.review.get(key) for key in ('id', 'text', 'title', 'sending', 'error', 'editVersion')} if self.review else None,
                'bubble': self.dictation_bubble(now) or (self.bubble if show_bubble else None)}

    # ----- routing -----
    def select(self, thread, automatic=False):
        with self.lock:
            had_thread = self.thread is not None
            enabled = bool(self.thread and self.routes.preferences.get(self.thread, False))
            if not automatic:
                if self.review and self.review.get('sending'):
                    return
                if self.review:
                    self.cancel_review()
                self.follow_active = False
                self.prefs.set('followActive', False)
            self.stop()
            self.thread = thread
            self.agent = {}
            self.agent_poll_at = 0.0
            self.routes.select(thread)
            if automatic and had_thread:
                self.routes.enable(enabled)
            if self.active_thread and not any(t['id'] == thread for t in self.threads):
                self.threads.insert(0, dict(self.active_thread))
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

    # ----- audio devices -----
    def device_index(self, kind):
        name = self.mic_device if kind == 'input' else self.speaker_device
        try:
            return resolve_audio_device(name, sd.query_devices(), sd.query_hostapis(), kind)
        except Exception:
            return None

    def audio_devices(self):
        devices, hostapis = sd.query_devices(), sd.query_hostapis()
        listed = lambda kind: [{'name': n, 'label': l} for n, l in audio_device_choices(devices, hostapis, kind)]
        return {'inputs': listed('input'), 'outputs': listed('output'),
                'mic': self.mic_device, 'speaker': self.speaker_device}

    def set_mic_device(self, name):
        with self.lock:
            self.mic_device = name or ''
            self.prefs.set('micDevice', self.mic_device)
            if self.mic_stream is not None:      # reopen on the new device if the meter is running
                self.mic_stream.abort()
                self.mic_stream.close()
                self.mic_stream = None
                self.update_mic()

    def set_speaker_device(self, name):
        with self.lock:
            previous = self.speaker_device
            self.speaker_device = name or ''
            if self.audio is None:
                self.prefs.set('speakerDevice', self.speaker_device)
                return
            self.stop()
            try:
                fresh = ContinuousAudio(device=self.device_index('output'))
            except Exception as exc:
                self.speaker_device = previous
                self.meta['speakerError'] = type(exc).__name__
                return
            old, self.audio = self.audio, fresh
            old.close()
            self.prefs.set('speakerDevice', self.speaker_device)
            self.cue([523, 659], 60)               # a short chime on the new speaker

    def set_appearance(self, high_contrast, reduced_motion):
        with self.lock:
            self.high_contrast = bool(high_contrast)
            self.reduced_motion = bool(reduced_motion)
            self.prefs.set('highContrast', self.high_contrast)
            self.prefs.set('reducedMotion', self.reduced_motion)

    def toggle_voice_fx(self):
        with self.lock:
            self.voice_fx = not self.voice_fx
            self.prefs.set('voiceFx', self.voice_fx)

    # ----- toolbar and OpenWhispr pill -----
    def toggle_dock(self):
        with self.lock:
            self.dock = not self.dock
            self.prefs.set('dock', self.dock)
            self.expanded = False
            self.panel_extra = False
            self.show_until = time.monotonic() + LINGER
            if self.hwnd is not None:
                self.place(self.target_size())
            self.cue([587, 440] if self.dock else [440, 587], 50)

    def manage_pill(self, force=False):
        now = time.monotonic()
        self.pill_hwnds = {hwnd for hwnd in self.pill_hwnds if user32.IsWindow(hwnd)}
        if force or now >= self.pill_scan_at:
            self.pill_hwnds.update(find_openwhispr_pills())
            self.pill_scan_at = now + .25
        for hwnd in self.pill_hwnds:
            set_hidden_region(hwnd, not self.quit.is_set())
        self.meta['hiddenOverlayCount'] = len(self.pill_hwnds)

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
        self.listening = False
        want = self.ready and self.dictating
        if want and self.mic_stream is None:
            self.mic_stream = sd.RawInputStream(samplerate=RATE, channels=1, dtype='int16', device=self.device_index('input'),
                                                blocksize=FRAME, latency='low', callback=self.mic_callback)
            self.mic_stream.start()
        elif not want and self.mic_stream is not None:
            self.mic_stream.abort()
            self.mic_stream.close()
            self.mic_stream = None
            self.mic_level = 0.0
            self.mic_bands = [0.0]*11

    def mic_callback(self, data, frames, timing, status):
        frame = bytes(data)
        if len(frame) != FRAME * 2:
            return
        level,bands = audio_feedback(frame,RATE)
        self.mic_level = max(level, self.mic_level * .86)  # retain short peaks between 50 ms UI polls
        self.mic_bands = [max(value,previous*.74) for value,previous in zip(bands,self.mic_bands)]
        self.mic_peak = max(self.mic_peak,level)
        # Display-only preview; OpenWhispr still supplies the only deliverable transcript.
        if self.dict_preview:
            self.dict_preview.push(frame, voiced=level > .004)

    def preview_audio(self, session, audio):
        started = time.perf_counter()
        text, error = '', ''
        try:
            text = transcribe(audio, RATE, timeout=1.5)
        except Exception as exc:
            error = type(exc).__name__
        self.notice.put(('dict-preview', (session, text, (time.perf_counter()-started)*1000, error)))

    def accept_dictation_preview(self, session, text, elapsed, error):
        accepted = self.dict_preview.complete(session, text)
        if accepted and not self.review:
            self.dict_preview_text = accepted[-1200:]
            self.meta['lastPreviewMs'] = elapsed
            self.meta['previewUpdates'] = self.meta.get('previewUpdates', 0) + 1
            self.meta.pop('previewError', None)
        if error:
            self.meta['previewError'] = error

    def deliver_audio(self, audio, ticket):
        started = time.perf_counter()
        try:
            with self.asr_lock:
                text = transcribe(audio, RATE)
            asr_ms = (time.perf_counter() - started) * 1000
            if not text or not self.routes.current(ticket):
                self.notice.put(('discarded', 'empty' if not text else 'target changed'))
                return
            self.notice.put(('transcript', (text, ticket, asr_ms, started)))
        except Exception as exc:
            self.notice.put(('send-error', type(exc).__name__ + ': ' + str(exc)[:120]))
        finally:
            self.notice.put(('asr-finished', None))

    HOLD_SECONDS = 1.1
    SENTENCE_GRACE = 0.65

    def accept_transcript(self, text, ticket, asr_ms, started):
        """ASR punctuation is not a turn boundary. Every segment gets a continuation grace."""
        if not self.routes.current(ticket):
            return
        if self.pending and self.pending['ticket'] == ticket:
            text = self.pending['text'] + ' ' + text
            asr_ms += self.pending['asr']
            started = self.pending['started']
        capturing = getattr(getattr(self, 'gate', None), 'frames', None) is not None
        grace = self.SENTENCE_GRACE if text.rstrip().endswith(('.', '?', '!')) else self.HOLD_SECONDS
        self.pending = {'text': text, 'ticket': ticket, 'asr': asr_ms, 'started': started,
                        'deadline': None if capturing else time.monotonic() + grace}
        self.set_state('hearing' if capturing else 'ready', '' if capturing else 'Listening…')

    def flush_pending(self, now):
        capturing = getattr(getattr(self, 'gate', None), 'frames', None) is not None
        if not self.pending or capturing or self.asr_pending:
            return
        if self.pending['deadline'] is None:
            self.pending['deadline'] = now + self.HOLD_SECONDS
        elif now >= self.pending['deadline']:
            fragment, self.pending = self.pending, None
            self.dispatch(fragment['text'], fragment['ticket'], fragment['asr'], fragment['started'])

    def dispatch(self, text, ticket, asr_ms, started, approved=False):
        threading.Thread(target=self.deliver_text, args=(text, ticket, asr_ms, started, approved), daemon=True).start()

    def deliver_text(self, text, ticket, asr_ms, started, approved=False):
        try:
            if self.cleanup and not approved:
                text = cleanup_text(text)
            if not self.routes.current(ticket):
                self.notice.put(('discarded', 'target changed'))
                return
            if self.follow_active and not approved and (not self.active_thread or self.active_thread['id'] != ticket.thread):
                raise RuntimeError('The open T3 thread changed during capture. Please speak again for the new thread.')
            if self.delivery == 'review' and not approved:
                self.notice.put(('review', (text, ticket, asr_ms, started)))
                return
            if self.delivery == 'composer' and not approved:
                self.draft_in_composer(ticket, text)
                self.notice.put(('drafted', None))
                return
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
            if self.review and self.review.get('sending'):
                continue  # the draft is already on its way; this text is not for it
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
        self.synthesis_done_run = ''
        if self.current is not None:
            self.visual_events['interrupt'] += 1
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
            try:
                self.audio = ContinuousAudio(device=self.device_index('output'))
            except Exception:
                self.audio = ContinuousAudio()      # saved speaker unavailable: use the system default
            self.notice.put(('ready', None))
            while not self.quit.is_set():
                try:
                    message, generation = self.jobs.get(timeout=.05)
                except queue.Empty:
                    continue
                with self.audio.cv:
                    if (self.feed and message.run in self.feed.suppressed) or generation != self.generation:
                        continue
                    self.synthesis_done_run = ''
                    self.audio.begin_reply(message.run)
                    self.current = message
                    self.cancel = threading.Event()
                    cancel = self.cancel
                    epoch = self.audio.epoch
                self.notice.put(('speaking', message))
                start = time.perf_counter()
                first = None
                fx = self.fx if self.voice_fx else None
                if fx is None:
                    self.fx.reset()
                with tts.stream(message.text, voice='Maeve') as stream:
                    for chunk in stream:
                        if cancel.is_set() or self.quit.is_set():
                            break
                        if first is None:
                            first = (time.perf_counter() - start) * 1000
                            self.notice.put(('first-audio', first))
                        clipped = np.clip(fx.process(chunk) if fx else chunk, -1, 1)
                        pcm = (clipped * 32767).astype('<i2').tobytes()
                        if not self.audio.put(pcm, epoch, cancel, reply_run=message.run):
                            break
                if cancel.is_set() or self.quit.is_set():
                    self.fx.reset()  # an interruption never leaves a reverb tail behind
                elif fx is not None:
                    # Release the reverb tail in 50 ms slices, only while the output is nearly empty and
                    # nothing new is queued, so the next sentence never waits behind it.
                    while self.jobs.empty() and fx.tail_live and not cancel.is_set():
                        with self.audio.cv:
                            while (self.audio.pending > 2400 and self.jobs.empty() and not cancel.is_set()
                                   and epoch == self.audio.epoch):
                                self.audio.cv.wait(.01)
                        if not self.jobs.empty() or cancel.is_set():
                            break
                        tail = np.clip(fx.drain(0.05), -1, 1)
                        if not self.audio.put((tail * 32767).astype('<i2').tobytes(), epoch, cancel, reply_run=message.run):
                            break
                if not cancel.is_set():
                    self.synthesis_done_run = message.run
                    self.finalize_playback()
                self.audio.drain(epoch, cancel)
                self.out_level = 0.0
                self.current = None
                self.notice.put(('done', not cancel.is_set()))
        except Exception as exc:
            self.notice.put(('error', type(exc).__name__ + ': ' + str(exc)))

    def finalize_playback(self):
        # The total becomes known after the run has settled AND the last PCM has been generated.
        if not self.audio or not self.synthesis_done_run or not self.jobs.empty():
            return
        run = self.synthesis_done_run
        known_final = (run.startswith('voice-test-') or
                       (self.agent.get('activity') == 'idle' and self.agent.get('run') == run
                        and self.settled_feed_run == run))
        abandoned = self.current is None and self.agent.get('run') != run
        if known_final or abandoned:
            self.audio.finish_reply(run)

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
                if kind == 'review':
                    text, ticket, asr, started = value
                    if self.routes.current(ticket):
                        self.review_seq += 1
                        self.review = {'id': self.review_seq, 'text': text, 'ticket': ticket, 'asr': asr,
                                       'since': self.dictation_started_wall or (time.time()-max(0,time.perf_counter()-started)),
                                       'started': started, 'title': next((t['title'] for t in self.threads if t['id'] == ticket.thread), '')}
                        self.review_poll_at = 0.0
                        self.expanded = False
                        self.confirmed = False
                        self.set_state('reviewing')
                        self.update_mic()
                        if self.hwnd:
                            self.place(self.target_size())
                            user32.ShowWindowAsync(self.hwnd, SW_SHOWNOACTIVATE)
                            self.visible = True
                            self.set_review_focus(True)
                elif kind == 'drafted':
                    self.confirmed = False
                    self.set_state(self.idle_state(), 'Draft ready · press Enter in T3')
                    self.pin_until = time.monotonic() + 5
                elif kind == 'active-thread':
                    changed = self.active_thread != value
                    self.active_thread = value
                    self.meta.pop('activeThreadError', None)
                    if changed and self.follow_active:
                        self.update_mic()
                        if self.ready and self.state in ('off', 'ready'):
                            self.set_state(self.idle_state())
                elif kind == 'active-thread-error':
                    self.active_thread = None
                    self.meta['activeThreadError'] = value
                    if self.follow_active:
                        self.update_mic()
                elif kind == 'ready':
                    self.ready = True
                    if self.feed:
                        self.feed.discard_pending()
                    self.set_state(self.idle_state())
                    self.update_mic()
                    self.cue([523, 784], 60)
                    self.pin_until = time.monotonic() + 3.0
                    self.text = 'Ready · Ctrl+Alt+M'
                elif kind == 'stop':
                    self.pending = None
                    if self.review:
                        self.cancel_review()
                    self.stop()
                    self.set_state('stopped')
                elif kind == 'dict-start':
                    self.dictation_started_wall = time.time()
                    if self.current or not self.jobs.empty():
                        self.stop()  # Maeve must not talk into the dictation
                    if self.review and not self.review.get('sending'):
                        self.review = None          # newer dictation replaces an unsent draft
                        self.set_review_focus(False)
                    self.pending = None
                    self.dictating = True
                    self.mic_peak = 0.0
                    self.dict_state = 'dictating'
                    self.dict_preview_text = ''
                    self.dict_preview_until = 0.0
                    self.bubble = None          # older reply text never comes back over the new turn
                    self.bubble_until = 0.0
                    self.bubble_layout_until = 0.0
                    if not self.review:
                        self.dict_preview_session = self.dict_preview.start()
                    self.update_mic()
                elif kind == 'dict-preview':
                    self.accept_dictation_preview(*value)
                elif kind == 'dict-stop':
                    if self.dictating:
                        self.dictating = False
                        self.dict_state = 'processing'
                        self.dict_until = time.monotonic() + 12.0
                        self.dict_quiet_until = time.monotonic() + 0.6
                        self.dict_preview.stop()  # don't await preview ASR or add release latency
                        self.update_mic()
                elif kind == 'hotkey':
                    if self.review:
                        self.cancel_review()
                    elif self.current or not self.jobs.empty() or self.state in ('speaking', 'reading'):
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
                elif kind == 'asr-finished':
                    self.asr_pending = max(0, self.asr_pending - 1)
                elif kind == 'sending':
                    self.set_state('sending')
                elif kind == 'discarded':
                    self.meta['utterancesDiscarded'] += 1
                    self.confirmed = False
                    self.set_state(self.idle_state())
                elif kind == 'sent':
                    self.finish_review()
                    words, asr_ms, total_ms = value
                    self.meta['utterancesSent'] += 1
                    self.visual_events['sent'] += 1
                    self.meta.update(lastAsrMs=asr_ms, lastSendMs=total_ms)
                    self.set_state('waiting')
                    self.confirmed = False
                    self.sent_at = time.monotonic()
                    self.detail = 'Sent %d words · ASR %.0f ms · total %.0f ms' % (words, asr_ms, total_ms)
                    self.cue([784, 1047], 55)
                elif kind == 'you':
                    self.show_bubble('you', value, None, 3.0)
                elif kind == 'send-error':
                    self.finish_review(value)
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
        self.reconcile_direct_submission()
        self.flush_pending(time.monotonic())
        now = time.monotonic()
        if now >= self.agent_poll_at:
            self.agent = read_agent_activity(DB, self.thread)
            self.agent_poll_at = now + .35
        try:
            if self.ready and self.feed and self.voice_on():
                messages = self.feed.poll()
                self.settled_feed_run = ''
                for message in messages:
                    self.last_run = message.run
                    if self.maeve_muted:
                        if self.t3_min:
                            self.silent.append(message)
                        continue
                    self.jobs.put_nowait((message, self.generation))
                if self.agent.get('activity') == 'idle':
                    self.settled_feed_run = self.agent.get('run', '')
                if self.mode == 'openwhispr' and self.openwhispr.available():
                    self.forward_openwhispr()
        except queue.Full:
            self.stop()
            self.set_state('error', 'Speech queue filled')
        except Exception as exc:
            self.meta['connectionError'] = type(exc).__name__
        self.finalize_playback()
        self.meta['updatedAt'] = time.time()
        self.meta['mode'] = self.mode
        self.meta['inputMonitorActive'] = self.mic_stream is not None
        self.meta['lastMicPeak'] = self.mic_peak
        self.follow_tick()
        self.meta.update(followActive=self.follow_active,
                         activeThreadId=self.active_thread['id'] if self.active_thread else None)
        self.meta.update(delivery=self.delivery, reviewPending=bool(self.review))
        self.meta.update(dock=self.dock, dictationState=self.dict_state, hidePill=self.hide_pill)
        if self.audio:
            self.meta.update(playedSamples=self.audio.played_samples, outputUnderflows=self.audio.output_underflows)
            self.meta['playbackLevel'] = self.audio.level
        write_status(ROOT / 't3-voice-status.json', self.meta)
        self.desktop_tick()

    # ----- OpenWhispr dictation -----
    dict_error = ''

    def dictation_tick(self):
        now = time.monotonic()
        if self.dict_preview:
            request = self.dict_preview.request(now)
            if request:
                threading.Thread(target=self.preview_audio, args=request, daemon=True).start()
        if now >= self.env_read_at:
            self.read_openwhispr_settings()
        self.manage_pill()
        try:
            rows = self.dict_watch.poll()
        except Exception as exc:
            self.meta['dictationWatchError'] = type(exc).__name__
            rows = []
        # An earlier cleanup can finish during the next held recording. It is not this turn's end.
        if rows and not self.dictating and self.dict_state == 'processing':
            last = rows[-1]
            if last['status'] == 'completed' and last['text']:
                self.dict_state, self.dict_until = 'done', now + 0.9
                self.dict_preview_text = last['text'][-1200:]
                self.dict_preview_until = now + 3.0
                self.meta['lastDictationWords'] = len(last['text'].split())
            else:
                self.dict_state, self.dict_until = 'failed', now + 3.0
                self.dict_preview_until = 0.0
                self.dict_error = (last['error'] or 'Dictation failed')[:60]
        elif self.dict_state in ('processing', 'done', 'failed') and now >= self.dict_until:
            self.dict_state = ''

    # ----- bubble -----
    def reply_playing(self):
        bubble, current = self.bubble, self.current
        return bool(bubble and bubble.get('who') == 'maeve' and current and current.run == self.bubble_run)

    def reply_bubble_visible(self, now):
        return bool(not self.expanded and not self.review and self.bubble
                    and (now < self.bubble_until or self.reply_playing()))

    def dictation_bubble(self, now):
        if self.expanded or self.review:
            return None
        live = self.dict_state == 'dictating'
        processing = self.dict_state == 'processing'
        if live or processing or (self.dict_preview_text and now < self.dict_preview_until):
            return {'id': 'dict-%s' % self.dict_preview_session, 'who': 'you', 'live': live,
                    'processing': processing, 'text': self.dict_preview_text or ('Listening…' if live else 'Transcribing…')}
        return None

    def show_bubble(self, who, text, run, seconds):
        now = time.monotonic()
        current = self.current
        if who == 'maeve':
            self.dict_preview_until = 0.0  # let the reply take over from the final user transcript
        same = (who == 'maeve' and self.bubble and self.bubble['who'] == 'maeve' and run == self.bubble_run
                and (now < self.bubble_until + LINGER or (current and current.run == run)))
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
        if self.review:
            return BAR_BUBBLE if self.dock else BUBBLE
        if self.expanded:
            base = BAR_CARD if self.dock else CARD
            return (base[0], base[1] + (120 if self.panel_extra else 0))
        now = time.monotonic()
        bubble = (self.dictation_bubble(now) or self.reply_bubble_visible(now)
                  or now < self.bubble_layout_until
                  or (self.dict_preview_text and now < self.dict_preview_until + BUBBLE_FADE)
                  or (self.bubble is not None and now < self.bubble_until + BUBBLE_FADE))
        if self.dock:
            return BAR_CARD if self.expanded else BAR_BUBBLE if bubble else BAR
        return CARD if self.expanded else BUBBLE if bubble else COMPACT

    def wants_visible(self, now):
        if self.agent.get('activity') in ('approval', 'input', 'thinking'):
            return True
        if self.review or self.dock or self.dict_state or self.expanded or self.hovered or now < self.pin_until or self.pending or self.dictation_bubble(now):
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
        return self.reply_bubble_visible(now)

    def card_watch(self, now):
        """Close the settings card when the user clicks another window, or leaves it for 2.5 s."""
        if not (self.expanded and self.hwnd) or self.review or now - self.expanded_at < 0.8:
            return
        if self.choosing_delivery:
            self.outside_since = None
            return
        foreground = user32.GetForegroundWindow()
        ours = foreground == self.hwnd or user32.GetAncestor(foreground, 3) == self.hwnd  # GA_ROOTOWNER
        if ours:
            self.card_focused = True
        point, rect = wintypes.POINT(), wintypes.RECT()
        user32.GetCursorPos(ctypes.byref(point))
        user32.GetWindowRect(self.hwnd, ctypes.byref(rect))
        inside = rect.left <= point.x < rect.right and rect.top <= point.y < rect.bottom
        self.outside_since = None if inside else (self.outside_since or now)
        if (self.card_focused and not ours and not inside) or (self.outside_since and now - self.outside_since > 2.5):
            self.set_expanded(False)

    def refresh_hover(self):
        """Recover from missed WebView leave events; transparent window space is not a hover target."""
        if not self.hovered or not self.hwnd or self.expanded:
            return
        point, rect = wintypes.POINT(), wintypes.RECT()
        user32.GetCursorPos(ctypes.byref(point))
        user32.GetWindowRect(self.hwnd, ctypes.byref(rect))
        scale = self.scale()
        x = (point.x - (rect.left + rect.right) / 2) / scale
        y = (rect.bottom - point.y) / scale
        if self.dock:
            self.hovered = abs(x) <= 98 and 4 <= y <= 44
        else:
            self.hovered = (x*x + (y-66)**2 <= 48**2 or
                            (abs(x)-60)**2 + (y-66)**2 <= 18**2 or
                            (x-39)**2 + (y-103)**2 <= 14**2)

    def desktop_tick(self):
        now = time.monotonic()
        self.refresh_hover()
        self.card_watch(now)
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
        if self.reply_playing():
            self.bubble_until = max(self.bubble_until, now + 1.0)
        if self.dictation_bubble(now) or self.reply_bubble_visible(now):
            self.bubble_layout_until = now + BUBBLE_FADE
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
        monitor = user32.MonitorFromPoint(wintypes.POINT(int(cx), int(bottom)-20), 2)
        info = MONITORINFO()
        info.size = ctypes.sizeof(info)
        if user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            width, height = min(width, info.work.right-info.work.left), min(height, info.work.bottom-info.work.top)
            cx, bottom = clamp_anchor((cx,bottom), (width,height),
                                      (info.work.left,info.work.top,info.work.right,info.work.bottom))
        user32.SetWindowPos(self.hwnd, HWND_TOPMOST, int(cx - width / 2), int(bottom - height), width, height,
                            SWP_NOACTIVATE)
        self.viewport_target = (width / scale, height / scale)
        self.size = size

    def attach(self, hwnd):
        """Called once the native window exists: position it on the saved anchor or the work-area corner."""
        self.hwnd = hwnd
        # pywebview must initialize pythonnet first; concurrent clr imports can break its startup.
        threading.Thread(target=self.watch_active_thread, daemon=True).start()
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
        with self.lock:
            if self.hwnd is not None and expanded != self.expanded:
                if expanded and self.review and self.review.get('sending'):
                    return {'expanded': self.expanded, 'size': list(self.viewport_target)}
                if expanded and self.review:
                    self.review = None
                    self.set_state(self.idle_state())
                self.expanded = expanded
                self.expanded_at = time.monotonic()
                self.card_focused = False
                self.outside_since = None
                if not expanded:
                    self.panel_extra = False
                self.show_until = time.monotonic() + LINGER
                self.place(self.target_size())
                self.set_review_focus(expanded)
            return {'expanded': self.expanded, 'size': list(self.viewport_target)}

    def set_panel_extra(self, extra):
        with self.lock:
            self.panel_extra = bool(extra)
            if self.hwnd:
                self.place(self.target_size())

    def close(self):
        self.quit.set()
        self.dict_preview.stop()
        for hwnd in self.pill_hwnds:
            if user32.IsWindow(hwnd):
                set_hidden_region(hwnd, False)
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

    def toggle_voice_fx(self):
        self._engine.toggle_voice_fx()

    def set_appearance(self, high_contrast, reduced_motion):
        self._engine.set_appearance(high_contrast, reduced_motion)

    def audio_devices(self):
        return self._engine.audio_devices()

    def set_mic_device(self, name):
        self._engine.set_mic_device(name)

    def set_speaker_device(self, name):
        self._engine.set_speaker_device(name)

    def poll(self, choosing_delivery=False):
        self._engine.choosing_delivery = bool(choosing_delivery)
        return self._engine.snapshot()

    def select(self, thread):
        self._engine.select(thread)

    def toggle_voice(self):
        self._engine.toggle_voice()

    def toggle_follow_active(self):
        self._engine.toggle_follow_active()

    def set_delivery(self, mode):
        self._engine.set_delivery(mode)

    def set_panel_extra(self, extra):
        self._engine.set_panel_extra(extra)

    def update_review_text(self, review_id, text, revision):
        self._engine.update_review_text(review_id, text, revision)

    def confirm_review(self, review_id, text):
        self._engine.confirm_review(review_id, text)

    def cancel_review(self):
        self._engine.cancel_review()

    def toggle_cleanup(self):
        self._engine.toggle_cleanup()

    def toggle_startup(self):
        self._engine.toggle_startup()

    def stop(self):
        self._engine.notice.put(('stop', None))

    def test_voice(self):
        self._engine.test_voice()

    def set_expanded(self, expanded):
        return self._engine.set_expanded(bool(expanded))

    def set_hover(self, hovered):
        self._engine.set_hover(bool(hovered))

    def toggle_mic_mute(self):
        self._engine.toggle_mic_mute()

    def toggle_maeve_mute(self):
        self._engine.toggle_maeve_mute()

    def toggle_dock(self):
        self._engine.toggle_dock()

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
