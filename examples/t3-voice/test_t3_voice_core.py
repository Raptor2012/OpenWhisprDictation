import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import test_live_reader
from t3_voice_core import audio_device_choices, resolve_audio_device, VoiceFx, DictationWatch, McpSender, OpenWhisprFeed, parse_hotkey, Routes, StreamingFeed, UtteranceGate, send_message_cli
from t3_voice_core import parse_thread_url


class DictationPreviewTests(unittest.TestCase):
    def preview(self, **kwargs):
        from t3_voice_core import DictationPreview
        return DictationPreview(sample_rate=10, interval=.5, window_seconds=2, min_seconds=.2, **kwargs)

    def test_only_held_speech_requests_preview_and_only_one_request_runs(self):
        preview = self.preview()
        preview.push(b'1234', voiced=True)
        self.assertIsNone(preview.request(0))
        session = preview.start()
        preview.push(b'0000', voiced=False)
        self.assertIsNone(preview.request(0))
        preview.push(b'1234', voiced=True)
        self.assertEqual((session,b'00001234'), preview.request(0))
        preview.push(b'5678', voiced=True)
        self.assertIsNone(preview.request(2))
        self.assertEqual('hello',preview.complete(session,'hello'))
        self.assertIsNone(preview.request(.4))
        self.assertEqual((session,b'000012345678'),preview.request(.5))

    def test_audio_is_bounded_and_release_drops_late_results(self):
        preview = self.preview()
        old = preview.start()
        preview.push(b'a'*60, voiced=True)
        self.assertEqual((old,b'a'*40),preview.request(0))
        preview.stop()
        preview.push(b'x'*60, voiced=True)
        self.assertIsNone(preview.request(1))
        new = preview.start()
        preview.push(b'b'*8, voiced=True)
        # A new hold previews at once; the previous hold's request no longer blocks it.
        self.assertEqual((new,b'b'*8),preview.request(1))
        self.assertIsNone(preview.complete(old,'late old words'))
        self.assertIsNone(preview.complete(old,'duplicate old result'))
        self.assertEqual('new words',preview.complete(new,'new words'))

    def test_empty_result_releases_worker_and_silence_does_not_repeat_inference(self):
        preview = self.preview()
        session = preview.start()
        preview.push(b'a'*8, voiced=True)
        preview.request(0)
        self.assertIsNone(preview.complete(session,''))
        preview.push(b'0'*8, voiced=False)
        self.assertIsNone(preview.request(2))
        preview.push(b'b'*8, voiced=True)
        self.assertIsNotNone(preview.request(2))


class AudioFeedbackTests(unittest.TestCase):
    def tone(self, frequency, amplitude=.002, rate=16000):
        import numpy as np
        samples=np.sin(2*np.pi*frequency*np.arange(rate//50)/rate)*amplitude
        return (samples*32767).astype('<i2').tobytes()

    def test_frequency_bands_follow_frequency_rather_than_one_loudness_value(self):
        from t3_voice_core import audio_feedback
        import numpy as np
        low_rms,low=audio_feedback(self.tone(400),16000)
        high_rms,high=audio_feedback(self.tone(1600),16000)
        self.assertAlmostEqual(low_rms,high_rms,places=5)
        self.assertNotEqual(int(np.argmax(low)),int(np.argmax(high)))
        self.assertGreater(max(low)-min(low),.2)
        self.assertGreater(max(high)-min(high),.2)

    def test_silence_is_zero_and_quiet_speech_has_visible_finite_bands(self):
        from t3_voice_core import audio_feedback
        level,bands=audio_feedback(bytes(640),16000)
        self.assertEqual(0,level)
        self.assertEqual([0.0]*11,bands)
        level,bands=audio_feedback(self.tone(800,amplitude=.0007),16000)
        self.assertGreater(max(bands),.1)
        self.assertTrue(all(0<=value<=1 for value in bands))


class ActiveThreadTests(unittest.TestCase):
    def test_exact_local_route_and_once_encoded_thread_id(self):
        self.assertEqual('abc', parse_thread_url('t3code://app/#/local/abc', 'local'))
        self.assertEqual('thread:task%3Aid', parse_thread_url('t3code://app/#/local/thread%3Atask%253Aid', 'local'))

    def test_non_thread_and_foreign_routes_are_rejected(self):
        for url in ('t3code://app/#/local', 't3code://app/#/settings/general',
                    't3code://app/#/remote/abc', 'https://evil/#/local/abc',
                    't3code://app/#/local/abc/extra', ''):
            self.assertIsNone(parse_thread_url(url, 'local'), url)


class RouteTests(unittest.TestCase):
    def test_settings_are_per_thread_and_stale_recording_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'settings.json'
            routes = Routes(path)
            routes.select('one')
            self.assertIsNone(routes.ticket())
            routes.enable(True)
            first = routes.ticket()
            routes.select('two')
            self.assertFalse(routes.current(first))
            self.assertIsNone(routes.ticket())
            routes.select('one')
            self.assertIsNotNone(routes.ticket())
            self.assertFalse(routes.current(first))
            self.assertTrue(Routes(path).preferences['one'])
            self.assertNotIn('transcript', path.read_text())

    def test_turning_off_invalidates_pending_transcription(self):
        with tempfile.TemporaryDirectory() as directory:
            routes = Routes(Path(directory) / 'settings.json')
            routes.select('one'); routes.enable(True)
            ticket = routes.ticket()
            routes.enable(False)
            self.assertFalse(routes.current(ticket))

    def test_send_uses_stdin_without_shell_and_does_not_retry(self):
        result = type('Result', (), {'returncode': 0, 'stdout': '{"delivery":"queued"}'})()
        with patch('t3_voice_core.subprocess.run', return_value=result) as run:
            self.assertEqual({'delivery': 'queued'}, send_message_cli('thread-1', 'Text with `code` and $(literal)'))
        args, kwargs = run.call_args
        self.assertIn('thread-1', args[0])
        self.assertEqual('-', args[0][-1])
        self.assertEqual('Text with `code` and $(literal)', kwargs['input'])
        self.assertFalse(kwargs.get('shell', False))
        self.assertEqual(1, run.call_count)


    def test_mcp_sender_reuses_session_and_rejects_tool_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            token = Path(directory) / 'token.txt'; token.write_text('secret')
            runtime = Path(directory) / 'runtime.json'; runtime.write_text('{"origin":"http://127.0.0.1:1"}')
            sender = McpSender(token, runtime)
            calls = []
            def fake_post(body, session=None):
                calls.append((body['method'], session))
                if body['method'] == 'initialize':
                    return 'sid-1', {'result': {}}
                if body['method'] == 'tools/call':
                    return None, {'result': {'structuredContent': {'delivery': 'queued'}}}
                return None, None
            sender._post = fake_post
            self.assertEqual({'delivery': 'queued'}, sender.send('thread-1', 'hello'))
            self.assertEqual({'delivery': 'queued'}, sender.send('thread-1', 'again'))
            self.assertEqual(1, sum(1 for method, _ in calls if method == 'initialize'))
            self.assertEqual('sid-1', calls[-1][1])
            sender._post = lambda body, session=None: (None, {'result': {'isError': True}})
            with self.assertRaises(RuntimeError):
                sender.send('thread-1', 'bad')


class StreamTests(unittest.TestCase):
    setUp = test_live_reader.ReaderTests.setUp
    add = test_live_reader.ReaderTests.add
    def test_streams_safe_sentences_once_and_flushes_tail(self):
        feed = StreamingFeed(self.path, 'chosen')
        self.add('one', 'Hello there. A partial', streaming=1)
        self.assertEqual(['Hello there.'], [m.text for m in feed.poll()])
        self.assertEqual([], feed.poll())
        self.db.execute('UPDATE orchestration_v2_projection_messages SET payload_json=?,streaming=0 WHERE message_id=?',
                        (json.dumps({'text': 'Hello there. A partial sentence.', 'creationSource': 'provider', 'createdBy': 'agent'}), 'one'))
        self.db.commit()
        self.assertEqual(['A partial sentence.'], [m.text for m in feed.poll()])
        self.assertEqual([], feed.poll())

    def test_streamed_code_and_tool_output_are_silent(self):
        feed = StreamingFeed(self.path, 'chosen')
        self.add('one', 'Explanation.\n```py\nsecret.call().\n```\nAfterwards.', streaming=1)
        self.assertEqual(['Explanation.'], [m.text for m in feed.poll()])
        feed.suppress('run-1')
        self.add('two', 'Do not restart.', run='run-1')
        self.add('three', 'Next turn.', run='run-2')
        self.assertEqual(['Next turn.'], [m.text for m in feed.poll()])


class OpenWhisprTests(unittest.TestCase):
    def test_only_new_completed_dictations_are_forwarded(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'transcriptions.db'
            db = sqlite3.connect(path)
            db.execute("CREATE TABLE transcriptions (id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT NOT NULL, "
                       "status TEXT NOT NULL DEFAULT 'completed', deleted_at TEXT)")
            db.execute("INSERT INTO transcriptions (text) VALUES ('old history')"); db.commit()
            feed = OpenWhisprFeed(path)
            self.assertEqual([], feed.poll())  # first poll only positions the cursor
            db.execute("INSERT INTO transcriptions (text) VALUES ('  Hello Maeve.  ')")
            db.execute("INSERT INTO transcriptions (text, status) VALUES ('failed one', 'failed')")
            db.execute("INSERT INTO transcriptions (text, deleted_at) VALUES ('gone', 'x')"); db.commit()
            self.assertEqual(['Hello Maeve.'], feed.poll())
            self.assertEqual([], feed.poll())
            db.close()


class DictationTests(unittest.TestCase):
    def test_hotkeys_map_to_virtual_keys(self):
        self.assertEqual((0x06,), parse_hotkey('MouseButton5'))
        self.assertEqual((0x11, 0x12, 0x20), parse_hotkey('Control+Alt+Space'))
        self.assertEqual((0x11, 0x5B), parse_hotkey('CommandOrControl+Super'))
        self.assertEqual((0x77,), parse_hotkey('F8'))
        self.assertEqual((0x10, 0x4B), parse_hotkey('Shift+k'))
        self.assertIsNone(parse_hotkey('GLOBE'))
        self.assertIsNone(parse_hotkey(''))

    def test_watch_reports_every_new_row_once_with_status(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'transcriptions.db'
            db = sqlite3.connect(path)
            db.execute("CREATE TABLE transcriptions (id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT NOT NULL, "
                       "status TEXT NOT NULL DEFAULT 'completed', error_message TEXT, deleted_at TEXT)")
            db.execute("INSERT INTO transcriptions (text) VALUES ('history')"); db.commit()
            watch = DictationWatch(path)
            self.assertEqual([], watch.poll())
            db.execute("INSERT INTO transcriptions (text) VALUES (' Pasted text. ')")
            db.execute("INSERT INTO transcriptions (text, status, error_message) VALUES ('', 'failed', 'No audio')")
            db.commit()
            rows = watch.poll()
            self.assertEqual([('completed', 'Pasted text.', ''), ('failed', '', 'No audio')],
                             [(r['status'], r['text'], r['error']) for r in rows])
            self.assertEqual([], watch.poll())
            db.close()


class UtteranceTests(unittest.TestCase):
    def test_default_keeps_half_second_pause_inside_one_utterance(self):
        gate = UtteranceGate()
        events = []
        for voiced, count, frame in [(True, 10, b'a'), (False, 25, b'z'), (True, 10, b'b'), (False, 59, b'z')]:
            for _ in range(count):
                events.extend(gate.push(frame, voiced))
        self.assertNotIn('end', [kind for kind, _ in events])
        ending = gate.push(b'z', False)
        self.assertEqual('end', ending[0][0])
        self.assertIn(b'a' * 10 + b'z' * 25 + b'b' * 10, ending[0][1])

    def test_speech_interrupts_before_silence_submits_once(self):
        gate = UtteranceGate(start_frames=3, silence_frames=4, confirm_frames=5)
        self.assertEqual([], gate.push(b'a', True))
        self.assertEqual([], gate.push(b'b', True))
        self.assertEqual('start', gate.push(b'c', True)[0][0])
        self.assertEqual([], gate.push(b'd', True))
        self.assertEqual([('confirm', None)], gate.push(b'e', True))
        for _ in range(3):
            self.assertEqual([], gate.push(b'z', False))
        events = gate.push(b'z', False)
        self.assertEqual('end', events[0][0])
        self.assertIn(b'abcde', events[0][1])
        self.assertEqual(5, gate.last_voiced)
        self.assertEqual([], gate.push(b'z', False))

    def test_short_burst_ends_without_confirmation(self):
        gate = UtteranceGate(start_frames=2, silence_frames=3, confirm_frames=7)
        gate.push(b'a', True)
        self.assertEqual('start', gate.push(b'b', True)[0][0])
        events = gate.push(b'z', False) + gate.push(b'z', False) + gate.push(b'z', False)
        self.assertEqual(['end'], [k for k, _ in events])
        self.assertEqual(2, gate.last_voiced)

    def test_reset_drops_the_utterance_in_progress(self):
        gate = UtteranceGate(start_frames=2, silence_frames=3, confirm_frames=3)
        gate.push(b'a', True); gate.push(b'b', True); gate.push(b'c', True)
        gate.reset()
        self.assertEqual([], gate.push(b'z', False) + gate.push(b'z', False) + gate.push(b'z', False))

    def test_short_noise_is_not_an_utterance(self):
        gate = UtteranceGate(start_frames=3, silence_frames=4)
        for voiced in (True, False, True, False, False):
            self.assertEqual([], gate.push(b'x', voiced))


class VoiceFxTests(unittest.TestCase):
    def signal(self):
        import numpy as np
        t = np.arange(24000) / 24000
        return (0.3 * np.sin(2 * np.pi * 220 * t) * (t < 0.6)).astype(np.float32)

    def test_chunked_output_matches_one_shot(self):
        import numpy as np
        x = self.signal()
        whole = VoiceFx().process(x)
        fx = VoiceFx()
        parts = np.concatenate([fx.process(x[i:i + 1777]) for i in range(0, len(x), 1777)])
        self.assertEqual(len(x), len(parts))
        self.assertLess(float(np.max(np.abs(whole - parts))), 1e-4)

    def test_output_is_finite_and_not_clipping(self):
        import numpy as np
        y = VoiceFx().process(self.signal())
        self.assertTrue(np.all(np.isfinite(y)))
        self.assertLess(float(np.max(np.abs(y))), 0.95)
        self.assertGreater(float(np.max(np.abs(y))), 0.1)

    def test_tail_rings_after_speech_and_reset_silences_it(self):
        import numpy as np
        fx = VoiceFx()
        fx.process(self.signal()[:9000])
        tail = fx.flush()
        self.assertGreater(float(np.max(np.abs(tail))), 1e-3)
        self.assertLess(abs(float(tail[-1])), 1e-4)
        self.assertEqual(0.0, float(np.max(np.abs(fx.flush()))))
        fx.process(self.signal()[:9000]); fx.reset()
        silence = fx.process(np.zeros(4000, np.float32))
        self.assertEqual(0.0, float(np.max(np.abs(silence))))


class VoiceFxDrainTests(unittest.TestCase):
    def test_drain_releases_small_slices_then_ends(self):
        import numpy as np
        fx = VoiceFx()
        t = np.arange(12000) / 24000
        fx.process((0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32))
        slices = []
        while fx.tail_live and len(slices) < 50:
            slices.append(fx.drain(0.05))
        self.assertEqual(7, len(slices))
        self.assertTrue(all(len(s) == 1200 for s in slices))
        self.assertGreater(float(np.max(np.abs(slices[0]))), 1e-3)
        self.assertEqual(0.0, float(np.max(np.abs(fx.process(np.zeros(2400, np.float32))))))


class AudioDeviceTests(unittest.TestCase):
    hostapis = [{'name': 'MME'}, {'name': 'Windows DirectSound'}]
    devices = [
        {'name': 'Microsoft Sound Mapper - Input', 'hostapi': 0, 'max_input_channels': 2, 'max_output_channels': 0},
        {'name': 'Microphone (USB Condenser Micro', 'hostapi': 0, 'max_input_channels': 1, 'max_output_channels': 0},
        {'name': 'Headphones (ULT WEAR)', 'hostapi': 0, 'max_input_channels': 0, 'max_output_channels': 2},
        {'name': 'Microphone (USB Condenser Microphone)', 'hostapi': 1, 'max_input_channels': 1, 'max_output_channels': 0},
    ]

    def test_choices_skip_mappers_and_use_full_names(self):
        self.assertEqual([('Microphone (USB Condenser Micro', 'Microphone (USB Condenser Microphone)')],
                         audio_device_choices(self.devices, self.hostapis, 'input'))
        self.assertEqual([('Headphones (ULT WEAR)', 'Headphones (ULT WEAR)')],
                         audio_device_choices(self.devices, self.hostapis, 'output'))

    def test_saved_device_resolves_and_missing_falls_back_to_default(self):
        self.assertEqual(1, resolve_audio_device('Microphone (USB Condenser Micro', self.devices, self.hostapis, 'input'))
        self.assertEqual(2, resolve_audio_device('Headphones (ULT WEAR)', self.devices, self.hostapis, 'output'))
        self.assertIsNone(resolve_audio_device('', self.devices, self.hostapis, 'input'))
        self.assertIsNone(resolve_audio_device('Unplugged headset', self.devices, self.hostapis, 'output'))
        self.assertIsNone(resolve_audio_device('Headphones (ULT WEAR)', self.devices, self.hostapis, 'input'))
