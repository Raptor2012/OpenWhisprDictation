"""T3 voice panel: hands-free speech in, streaming Maeve speech out, one chosen thread."""
import argparse
import ctypes
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
import webrtcvad

from diagnostics import write_status
from live_reader import ContinuousAudio
from live_reader_core import Message
from t3_voice_core import Routes, StreamingFeed, UtteranceGate, list_threads, send_message, transcribe

ROOT = Path(__file__).resolve().parent
DB = Path.home() / '.t3/userdata/statev2.sqlite'
RATE = 16000
FRAME = 320  # 20 ms at 16 kHz
MIN_UTTERANCE_BYTES = int(RATE * 0.45) * 2


class Panel:
    def __init__(self, thread=None):
        self.routes = Routes(ROOT / 't3-voice-settings.json')
        self.threads = list_threads(DB)
        self.window = tk.Tk()
        self.window.title('Maeve — T3 voice')
        self.window.geometry('560x330')
        self.window.minsize(500, 300)
        self.status = tk.StringVar(value='Loading Maeve locally…')
        self.listen_state = tk.StringVar(value='Microphone idle')
        self.voice_on = tk.BooleanVar(value=False)
        self.mic_on = tk.BooleanVar(value=True)
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
        self.meta = {'pid': os.getpid(), 'state': 'loading', 'voice': 'Maeve', 'model': 'Phonon 31M',
                     'asr': 'parakeet-0.6b via sherpa ws:6006', 'mode': 'streaming-sentences',
                     'chunksSpoken': 0, 'utterancesSent': 0, 'utterancesDiscarded': 0}

        outer = ttk.Frame(self.window, padding=16)
        outer.pack(fill='both', expand=True)
        ttk.Label(outer, text='Maeve · T3 voice', font=('Segoe UI', 16, 'bold')).pack(anchor='w')
        row = ttk.Frame(outer)
        row.pack(fill='x', pady=(8, 4))
        ttk.Label(row, text='Thread:').pack(side='left')
        self.picker = ttk.Combobox(row, state='readonly', width=52,
                                   values=[self.label(t) for t in self.threads])
        self.picker.pack(side='left', padx=(6, 0), fill='x', expand=True)
        self.picker.bind('<<ComboboxSelected>>', lambda _: self.select(self.threads[self.picker.current()]['id']))
        ttk.Checkbutton(outer, text='Voice on for this thread (speak replies, send what I say)',
                        variable=self.voice_on, command=self.toggle_voice).pack(anchor='w', pady=(6, 0))
        ttk.Checkbutton(outer, text='Hands-free microphone (speaking interrupts Maeve)',
                        variable=self.mic_on, command=self.toggle_mic).pack(anchor='w')
        ttk.Label(outer, textvariable=self.status, wraplength=510).pack(anchor='w', pady=(10, 0))
        ttk.Label(outer, textvariable=self.listen_state, wraplength=510, foreground='#1a5fb4').pack(anchor='w', pady=(2, 8))
        buttons = ttk.Frame(outer)
        buttons.pack(anchor='w')
        ttk.Button(buttons, text='Stop', command=self.stop).pack(side='left', padx=(0, 8))
        ttk.Button(buttons, text='Test Maeve', command=self.test_voice).pack(side='left', padx=(0, 8))
        ttk.Button(buttons, text='Quit', command=self.close).pack(side='left')
        ttk.Label(outer, text='Stop: Ctrl+Alt+Space or Escape. Code blocks and tool output are skipped.\n'
                              'Use headphones: the microphone stays open while Maeve speaks.',
                  foreground='#555555').pack(anchor='w', pady=(12, 0))
        self.window.protocol('WM_DELETE_WINDOW', self.close)
        self.window.bind('<Escape>', lambda _: self.stop())

        initial = thread or next((t['id'] for t in self.threads if self.routes.preferences.get(t['id'])), None)
        if initial is None and self.threads:
            initial = self.threads[0]['id']
        if initial:
            self.select(initial)
        threading.Thread(target=self.synthesize, daemon=True).start()
        threading.Thread(target=self.hotkey, daemon=True).start()
        self.window.after(60, self.tick)

    @staticmethod
    def label(t):
        return (t['title'] or '(untitled)')[:60] + '  ·  ' + t['id'][:8]

    # ----- routing -----
    def select(self, thread):
        self.stop()
        self.thread = thread
        self.routes.select(thread)
        self.feed = StreamingFeed(DB, thread)
        self.voice_on.set(self.routes.preferences.get(thread, False))
        for index, t in enumerate(self.threads):
            if t['id'] == thread:
                self.picker.current(index)
        self.meta['threadId'] = thread
        self.status.set(('Listening to this thread.' if self.voice_on.get() else 'Voice is off for this thread.'))
        self.update_mic()

    def toggle_voice(self):
        self.stop()
        self.routes.enable(self.voice_on.get())
        if self.feed:
            self.feed.discard_pending()
        self.status.set('Listening to this thread.' if self.voice_on.get() else 'Voice is off for this thread.')
        self.update_mic()

    def toggle_mic(self):
        self.update_mic()

    def update_mic(self):
        want = self.mic_on.get() and self.voice_on.get() and self.ready
        if want and self.mic_stream is None:
            self.start_mic()
        elif not want and self.mic_stream is not None:
            self.mic_stream.abort()
            self.mic_stream.close()
            self.mic_stream = None
            self.listen_state.set('Microphone idle')

    # ----- speech in -----
    def start_mic(self):
        self.vad = webrtcvad.Vad(2)
        self.gate = UtteranceGate(start_frames=3, silence_frames=25)  # 60 ms start, 500 ms end
        self.mic_stream = sd.RawInputStream(samplerate=RATE, channels=1, dtype='int16',
                                            blocksize=FRAME, latency='low', callback=self.mic_callback)
        self.mic_stream.start()
        self.listen_state.set('Microphone open. Speak when ready.')

    def mic_callback(self, data, frames, timing, status):
        frame = bytes(data)
        if len(frame) != FRAME * 2:
            return
        try:
            voiced = self.vad.is_speech(frame, RATE)
        except Exception:
            voiced = False
        for kind, audio in self.gate.push(frame, voiced):
            if kind == 'start':
                self.notice.put(('speech-start', None))
            else:
                ticket = self.routes.ticket()
                if ticket is None or len(audio) < MIN_UTTERANCE_BYTES:
                    self.notice.put(('discarded', 'too short' if ticket else 'voice off'))
                    continue
                self.notice.put(('speech-end', None))
                threading.Thread(target=self.deliver, args=(audio, ticket), daemon=True).start()

    def deliver(self, audio, ticket):
        started = time.perf_counter()
        try:
            text = transcribe(audio, RATE)
            asr_ms = (time.perf_counter() - started) * 1000
            if len(text.split()) < 1 or not self.routes.current(ticket):
                self.notice.put(('discarded', 'empty' if not text else 'target changed'))
                return
            send_message(ticket.thread, text)
            self.notice.put(('sent', (len(text.split()), asr_ms, (time.perf_counter() - started) * 1000)))
        except Exception as exc:
            self.notice.put(('send-error', type(exc).__name__ + ': ' + str(exc)[:120]))

    # ----- speech out -----
    def hotkey(self):
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
        self.meta['state'] = 'stopped'

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
                        pcm = (np.clip(chunk, -1, 1) * 32767).astype('<i2').tobytes()
                        if not self.audio.put(pcm, epoch, cancel):
                            break
                self.audio.drain(epoch, cancel)
                self.current = None
                self.notice.put(('done', not cancel.is_set()))
        except Exception as exc:
            self.notice.put(('error', type(exc).__name__ + ': ' + str(exc)))

    # ----- UI loop -----
    def tick(self):
        if self.quit.is_set():
            return
        try:
            while True:
                kind, value = self.notice.get_nowait()
                if kind == 'ready':
                    self.ready = True
                    if self.feed:
                        self.feed.discard_pending()
                    self.status.set('Ready.' + ('' if self.voice_on.get() else ' Turn voice on for this thread.'))
                    self.meta['state'] = 'ready'
                    self.update_mic()
                elif kind == 'stop':
                    self.stop()
                    self.status.set('Stopped.')
                elif kind == 'speech-start':
                    if self.current or not self.jobs.empty():
                        self.stop()  # barge-in
                    self.listen_state.set('Hearing you…')
                elif kind == 'speech-end':
                    self.listen_state.set('Transcribing…')
                elif kind == 'discarded':
                    self.meta['utterancesDiscarded'] += 1
                    self.listen_state.set('Ignored (' + value + '). Microphone open.')
                elif kind == 'sent':
                    words, asr_ms, total_ms = value
                    self.meta['utterancesSent'] += 1
                    self.meta.update(lastAsrMs=asr_ms, lastSendMs=total_ms)
                    self.listen_state.set('Sent %d words to T3 (ASR %.0f ms, total %.0f ms). Microphone open.' % (words, asr_ms, total_ms))
                    self.status.set('Waiting for the reply…')
                    self.meta['state'] = 'waiting'
                elif kind == 'send-error':
                    self.listen_state.set('Send failed: ' + value)
                    self.meta['lastSendError'] = value
                elif kind == 'speaking':
                    self.status.set('Maeve is speaking…')
                    self.meta['state'] = 'speaking'
                elif kind == 'first-audio':
                    self.meta['lastFirstAudioMs'] = value
                elif kind == 'done':
                    if value:
                        self.meta['chunksSpoken'] += 1
                    if self.jobs.empty():
                        self.status.set('Listening to this thread.' if self.voice_on.get() else 'Voice is off for this thread.')
                        self.meta['state'] = 'ready'
                elif kind == 'error':
                    self.ready = False
                    self.status.set('Reader error: ' + value)
                    self.meta.update(state='error', error=value)
        except queue.Empty:
            pass
        try:
            if self.ready and self.feed and self.voice_on.get():
                for message in self.feed.poll():
                    self.last_run = message.run
                    self.jobs.put_nowait((message, self.generation))
        except queue.Full:
            self.stop()
            self.status.set('Paused: speech queue filled.')
        except Exception as exc:
            self.status.set('T3 connection error: ' + type(exc).__name__)
            self.meta['connectionError'] = type(exc).__name__
        self.meta['updatedAt'] = time.time()
        if self.audio:
            self.meta.update(playedSamples=self.audio.played_samples, outputUnderflows=self.audio.output_underflows)
        write_status(ROOT / 't3-voice-status.json', self.meta)
        self.window.after(60, self.tick)

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
        self.window.destroy()

    def run(self):
        self.window.mainloop()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--thread', default=None)
    args = parser.parse_args()
    kernel = ctypes.windll.kernel32
    kernel.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel.CreateMutexW(None, True, 'Local\\MaeveT3Voice')
    if kernel.GetLastError() != 183:
        try:
            Panel(args.thread).run()
        finally:
            kernel.CloseHandle(ctypes.c_void_p(handle))
