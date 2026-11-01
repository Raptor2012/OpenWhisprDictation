"""Resident Maeve audition companion for one explicitly chosen T3 thread."""
import argparse
from collections import deque
import ctypes
import json
import os
from pathlib import Path
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk

os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
import numpy as np
import ptts
import sounddevice as sd

from live_reader_core import Message, MessageFeed
from t3_voice_core import audio_feedback
from diagnostics import write_status

ROOT = Path(__file__).resolve().parent
THREAD = 'e1702ae5-e5aa-4d2f-822c-26bbf95dfb95'


class ContinuousAudio:
    """One persistent device; callback always supplies PCM or silence."""
    def __init__(self, device=None):
        self.cv = threading.Condition()
        self.chunks = deque()
        self.pending = 0
        self.epoch = 0
        self.played_samples = 0
        self.callbacks = 0
        self.output_underflows = 0
        self.level = 0.0
        self.spectrum = [0.0]*11
        self.stream = sd.RawOutputStream(samplerate=24000, channels=1, dtype='int16', device=device,
                                         blocksize=480, latency='low', callback=self.callback)
        self.stream.start()

    def callback(self, output, frames, timing, status):
        target = memoryview(output).cast('B')
        target[:] = b'\0' * len(target)
        pos = 0
        with self.cv:
            self.callbacks += 1
            if status.output_underflow:
                self.output_underflows += 1
            while self.chunks and pos < len(target):
                chunk = self.chunks[0]
                take = min(len(chunk), len(target) - pos)
                target[pos:pos + take] = chunk[:take]
                pos += take
                self.pending -= take
                if take == len(chunk):
                    self.chunks.popleft()
                else:
                    self.chunks[0] = chunk[take:]
            self.played_samples += pos // 2
            level,bands = audio_feedback(target,24000) if pos else (0.0,[0.0]*11)
            self.level = max(level, self.level * .86)
            self.spectrum = [max(value,previous*.74) for value,previous in zip(bands,self.spectrum)]
            self.cv.notify_all()

    def reset(self):
        with self.cv:
            self.epoch += 1
            self.chunks.clear()
            self.pending = 0
            self.level = 0.0
            self.spectrum = [0.0]*11
            self.cv.notify_all()
            return self.epoch

    def put(self, pcm, epoch, cancel):
        pcm = memoryview(pcm)
        with self.cv:
            while self.pending > 48000 and epoch == self.epoch and not cancel.is_set():
                self.cv.wait(.03)
            if epoch != self.epoch or cancel.is_set():
                return False
            self.chunks.append(pcm)
            self.pending += len(pcm)
            return True

    def drain(self, epoch, cancel):
        with self.cv:
            while self.pending and epoch == self.epoch and not cancel.is_set():
                self.cv.wait(.03)

    def close(self):
        self.reset()
        self.stream.abort()
        self.stream.close()


class Reader:
    def __init__(self, thread):
        self.feed = MessageFeed(Path.home() / '.t3/userdata/statev2.sqlite', thread)
        self.thread = thread
        self.window = tk.Tk()
        self.window.title('Maeve — T3 live voice test')
        self.window.geometry('540x260')
        self.window.minsize(480, 240)
        self.status = tk.StringVar(value='Loading Maeve locally…')
        self.enabled = tk.BooleanVar(value=True)
        self.notice = queue.Queue()
        self.jobs = queue.Queue(maxsize=128)
        self.cancel = threading.Event()
        self.quit = threading.Event()
        self.current = None
        self.generation = 0
        self.last_run = None
        self.ready = False
        self.audio = None
        self.error = None
        self.meta = {'threadId': thread, 'mode': 'completed-assistant-messages',
                     'pid': os.getpid(), 'messagesObserved': 0, 'messagesSpoken': 0,
                     'state': 'loading', 'voice': 'Maeve', 'model': 'Phonon 31M'}
        outer = ttk.Frame(self.window, padding=20)
        outer.pack(fill='both', expand=True)
        ttk.Label(outer, text='Maeve · British English', font=('Segoe UI', 16, 'bold')).pack(anchor='w')
        ttk.Label(outer, text='Following this T3 conversation only.', font=('Segoe UI', 10)).pack(anchor='w', pady=(4, 10))
        ttk.Label(outer, textvariable=self.status, wraplength=470).pack(anchor='w')
        ttk.Checkbutton(outer, text='Read new replies automatically', variable=self.enabled,
                        command=self.toggle).pack(anchor='w', pady=10)
        buttons = ttk.Frame(outer)
        buttons.pack(anchor='w')
        ttk.Button(buttons, text='Stop', command=self.stop).pack(side='left', padx=(0, 8))
        ttk.Button(buttons, text='Test Maeve', command=self.test_voice).pack(side='left', padx=(0, 8))
        ttk.Button(buttons, text='Quit', command=self.close).pack(side='left')
        ttk.Label(outer, text='Stop shortcut: Ctrl + Alt + Space\nReads completed messages; skips code blocks and tool output.',
                  foreground='#555555').pack(anchor='w', pady=(12, 0))
        self.window.protocol('WM_DELETE_WINDOW', self.close)
        self.window.bind('<Escape>', lambda _: self.stop())
        self.worker = threading.Thread(target=self.synthesize, daemon=True)
        self.worker.start()
        threading.Thread(target=self.hotkey, daemon=True).start()
        self.window.after(100, self.tick)

    def write_status(self):
        self.meta['updatedAt'] = time.time()
        if self.audio:
            self.meta.update(audioCallbacks=self.audio.callbacks,
                             playedSamples=self.audio.played_samples,
                             outputUnderflows=self.audio.output_underflows,
                             deviceLatencySeconds=self.audio.stream.latency)
        write_status(ROOT / 'live-status.json', self.meta)

    def hotkey(self):
        # Poll a chord's edge; no system keyboard hook, clipboard or text capture.
        held = False
        user32 = ctypes.windll.user32
        while not self.quit.wait(.025):
            down = all(user32.GetAsyncKeyState(key) & 0x8000 for key in (0x11, 0x12, 0x20))
            if down and not held:
                self.notice.put(('stop', None))
            held = down

    def stop(self):
        if self.audio:
            with self.audio.cv:
                self._stop_locked()
        else:
            self._stop_locked()
        self.status.set('Stopped. The next new reply will be read.')
        self.meta['state'] = 'stopped'

    def _stop_locked(self):
        self.generation += 1
        self.cancel.set()
        if self.current:
            self.feed.suppress(self.current.run)
        if self.last_run:
            self.feed.suppress(self.last_run)
        # Suppress queued runs too, so their later messages cannot restart playback.
        while True:
            try:
                self.feed.suppress(self.jobs.get_nowait()[0].run)
            except queue.Empty:
                break
        if self.audio:
            self.audio.reset()

    def toggle(self):
        self.stop()
        self.feed.discard_pending()
        self.status.set('Waiting for a new reply…' if self.enabled.get() else 'Paused')

    def test_voice(self):
        if self.ready:
            self.jobs.put_nowait((Message('voice-test', 'voice-test-' + str(time.monotonic()),
                'Hello. I am Maeve. Ask a question in this conversation, and I will read the next reply aloud.'), self.generation))

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
                    message, generation = self.jobs.get(timeout=.1)
                except queue.Empty:
                    continue
                # UI and worker synchronize ownership through the audio condition.
                with self.audio.cv:
                    if message.run in self.feed.suppressed or generation != self.generation:
                        continue
                    self.current = message
                    self.cancel = threading.Event()
                    cancel = self.cancel
                    epoch = self.audio.epoch
                self.notice.put(('speaking', message.id))
                start = time.perf_counter()
                first = None
                with tts.stream(message.text, voice='Maeve') as stream:
                    for chunk in stream:
                        if cancel.is_set() or self.quit.is_set():
                            break
                        if first is None:
                            first = (time.perf_counter() - start) * 1000
                            self.notice.put(('first-audio', first))
                        pcm = (np.clip(chunk, -1, 1) * 32767).astype('<i2').tobytes()
                        if not self.audio.put(pcm, epoch, cancel):
                            break
                self.audio.drain(epoch, cancel)
                self.current = None
                self.notice.put(('done', not cancel.is_set()))
        except Exception as exc:
            self.notice.put(('error', type(exc).__name__ + ': ' + str(exc)))

    def tick(self):
        if self.quit.is_set():
            return
        try:
            while True:
                kind, value = self.notice.get_nowait()
                if kind == 'ready':
                    self.ready = True
                    self.feed.discard_pending()
                    self.status.set('Ready. Ask something in this T3 thread.')
                    self.meta['state'] = 'ready'
                elif kind == 'stop':
                    self.stop()
                elif kind == 'speaking':
                    self.status.set('Maeve is reading…')
                    self.meta.update(state='speaking', lastMessageId=value)
                elif kind == 'first-audio':
                    self.meta['lastFirstAudioMs'] = value
                elif kind == 'done':
                    if value:
                        self.meta['messagesSpoken'] += 1
                    self.status.set('Waiting for a new reply…' if self.enabled.get() else 'Paused')
                    self.meta['state'] = 'ready' if self.enabled.get() else 'paused'
                elif kind == 'error':
                    self.error = value
                    self.ready = False
                    self.status.set('Reader error: ' + value)
                    self.meta.update(state='error', error=value)
        except queue.Empty:
            pass
        try:
            if self.ready:
                messages = self.feed.poll()
                if self.enabled.get():
                    for message in messages:
                        self.meta['messagesObserved'] += 1
                        self.last_run = message.run
                        self.jobs.put_nowait((message, self.generation))
        except queue.Full:
            self.stop()
            self.enabled.set(False)
            self.status.set('Paused: speech queue filled. Enable to continue with new replies.')
        except Exception as exc:
            self.status.set('T3 connection error: ' + type(exc).__name__)
            self.meta['connectionError'] = type(exc).__name__
        self.write_status()
        self.window.after(100, self.tick)

    def close(self):
        self.quit.set()
        self.stop()
        if self.audio:
            self.audio.close()
        self.meta['state'] = 'closed'
        self.write_status()
        self.window.destroy()

    def run(self):
        self.window.mainloop()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--thread', default=THREAD)
    args = parser.parse_args()
    # Windows named mutex prevents duplicate narrators for this test companion.
    kernel = ctypes.windll.kernel32
    kernel.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel.CreateMutexW(None, True, 'Local\\MaeveT3LiveTest')
    if kernel.GetLastError() != 183:
        try:
            Reader(args.thread).run()
        finally:
            kernel.CloseHandle(ctypes.c_void_p(handle))
