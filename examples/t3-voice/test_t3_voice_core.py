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
        self.assertEqual(10, len(slices))   # 0.5 s tail in 50 ms slices
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


class AgentActivityTests(unittest.TestCase):
    def setUp(self):
        import sqlite3
        self.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).parent/'runtime')
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'state.sqlite'
        self.db=sqlite3.connect(self.path)
        self.addCleanup(self.db.close)
        self.db.executescript("""
          CREATE TABLE orchestration_v2_projection_runs(run_id TEXT,thread_id TEXT,ordinal INTEGER,status TEXT);
          CREATE TABLE orchestration_v2_projection_nodes(node_id TEXT,run_id TEXT,kind TEXT);
          CREATE TABLE orchestration_v2_projection_runtime_requests(runtime_request_id TEXT,thread_id TEXT,node_id TEXT,kind TEXT,status TEXT,resolved_at TEXT,payload_json TEXT);
          CREATE TABLE orchestration_v2_projection_messages(thread_id TEXT,run_id TEXT,role TEXT,streaming INTEGER);
        """)
        self.db.execute("INSERT INTO orchestration_v2_projection_runs VALUES('run','chosen',1,'running')")
        self.db.commit()

    def activity(self, thread='chosen'):
        from t3_voice_core import read_agent_activity
        return read_agent_activity(self.path,thread)

    def request(self, node_kind='approval_request', status='pending', run='run'):
        self.db.execute('INSERT INTO orchestration_v2_projection_nodes VALUES(?,?,?)',('node',run,node_kind))
        self.db.execute('INSERT INTO orchestration_v2_projection_runtime_requests VALUES(?,?,?,?,?,?,?)',
                        ('req','chosen','node','command',status,None,'{}'))
        self.db.commit()

    def test_approval_only_for_pending_request_in_current_run(self):
        self.request()
        self.assertTrue(self.activity()['approval'])
        self.assertEqual('approval',self.activity()['activity'])
        self.db.execute("UPDATE orchestration_v2_projection_runs SET status='completed'");self.db.commit()
        self.assertFalse(self.activity()['approval'])
        self.assertEqual('idle',self.activity()['activity'])

    def test_stale_run_other_thread_and_resolved_requests_never_light_approval(self):
        self.request(run='old')
        self.assertFalse(self.activity()['approval'])
        self.assertFalse(self.activity('other')['approval'])
        self.db.execute("UPDATE orchestration_v2_projection_nodes SET run_id='run'")
        self.db.execute("UPDATE orchestration_v2_projection_runtime_requests SET status='resolved'");self.db.commit()
        self.assertFalse(self.activity()['approval'])

    def test_questions_are_distinct_and_streaming_output_has_work_state(self):
        self.assertEqual('thinking',self.activity()['activity'])
        self.db.execute("INSERT INTO orchestration_v2_projection_messages VALUES('chosen','run','assistant',1)");self.db.commit()
        self.assertTrue(self.activity()['producing'])
        self.request(node_kind='user_input_request')
        self.assertTrue(self.activity()['needsInput'])
        self.assertFalse(self.activity()['approval'])

    def test_missing_schema_is_neutral(self):
        self.db.execute('DROP TABLE orchestration_v2_projection_runs');self.db.commit()
        self.assertEqual('unknown',self.activity()['activity'])


class VoiceSheenTests(unittest.TestCase):
    def test_parallel_micro_reflections_add_sheen_without_latency_or_chunk_seams(self):
        import inspect
        import numpy as np
        self.assertIn('sheen',inspect.signature(VoiceFx).parameters)
        t=np.arange(6000)/24000
        x=(.15*np.sin(2*np.pi*410*t)+.08*np.sin(2*np.pi*2300*t)).astype(np.float32)
        plain=VoiceFx(sheen=0).process(x)
        whole=VoiceFx(sheen=.10).process(x)
        fx=VoiceFx(sheen=.10)
        chunked=np.concatenate([fx.process(x[i:i+317]) for i in range(0,len(x),317)])
        self.assertGreater(float(np.max(np.abs(whole-plain))),.005)
        self.assertLess(float(np.max(np.abs(whole-chunked))),1e-4)
        impulse=np.zeros(1000,np.float32);impulse[0]=.1
        self.assertGreater(abs(float(VoiceFx().process(impulse)[0])),.01)
        self.assertTrue(np.isfinite(whole).all())


class DirectSubmissionTests(unittest.TestCase):
    def setUp(self):
        import sqlite3
        self.tmp=tempfile.TemporaryDirectory(dir=Path(__file__).parent/'runtime');self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'messages.sqlite';self.db=sqlite3.connect(self.path);self.addCleanup(self.db.close)
        self.db.execute('CREATE TABLE orchestration_v2_projection_messages(thread_id TEXT,role TEXT,created_at TEXT,payload_json TEXT)')

    def add(self,text,thread='chosen',created='2026-11-01T12:01:00.000Z',by='user',role='user'):
        self.db.execute('INSERT INTO orchestration_v2_projection_messages VALUES(?,?,?,?)',(thread,role,created,json.dumps({'text':text,'createdBy':by})));self.db.commit()

    def matched(self,text='Please inspect the Windows build'):
        from t3_voice_core import matching_user_submission
        from datetime import datetime,timezone
        return matching_user_submission(self.path,'chosen',text,datetime(2026,11,1,12,tzinfo=timezone.utc).timestamp())

    def test_normalized_direct_chat_submission_matches_pending_dictation(self):
        self.add('Please inspect the Windows build.');self.assertTrue(self.matched())

    def test_dictation_inside_a_longer_manual_message_matches(self):
        self.add('Extra context first. Please inspect the Windows build. Thanks.');self.assertTrue(self.matched())

    def test_old_other_thread_assistant_and_agent_messages_cannot_clear_review(self):
        for kwargs in ({'created':'2026-11-01T11:59:59.000Z'},{'thread':'other'},{'role':'assistant'},{'by':'agent'}):
            self.add('Please inspect the Windows build',**kwargs)
        self.assertFalse(self.matched())

    def test_unrelated_message_and_short_word_overlap_keep_review(self):
        self.add('Yes, please continue with another task.')
        self.assertFalse(self.matched())
        self.assertFalse(self.matched('yes'))

    def test_missing_database_fails_closed(self):
        from t3_voice_core import matching_user_submission
        self.assertFalse(matching_user_submission(self.path.parent/'missing.sqlite','chosen','Text',0))


class SentDraftRemovalTests(unittest.TestCase):
    def remove(self,draft,text):
        from t3_voice_core import remove_sent_draft_text
        return remove_sent_draft_text(draft,text)

    def test_whole_duplicate_is_cleared(self):
        self.assertEqual('',self.remove('  Dictated words.  ','Dictated words.'))

    def test_surrounding_typed_text_is_preserved_exactly(self):
        self.assertEqual('Earlier draft\n\n\nAfterwards',self.remove('Earlier draft\n\nDictated words.\nAfterwards','Dictated words.'))

    def test_whitespace_variations_match_without_changing_surroundings(self):
        self.assertEqual('Prefix:  suffix',self.remove('Prefix: Dictated\r\nwords. suffix','Dictated words.'))

    def test_ambiguous_or_overlapping_repetitions_are_kept(self):
        self.assertIsNone(self.remove('yes yes yes','yes yes'))
        self.assertIsNone(self.remove('Dictated words. Dictated words.','Dictated words.'))

    def test_unrelated_text_and_substrings_inside_words_are_kept(self):
        self.assertIsNone(self.remove('Different draft','Dictated words.'))
        self.assertIsNone(self.remove('Yesterday','Yes'))
        self.assertIsNone(self.remove('Text','  '))

class CinematicVoiceFxTests(unittest.TestCase):
    def test_body_is_preserved_while_subsonic_rumble_is_removed(self):
        import numpy as np
        from t3_voice_core import _minimum_phase_eq
        h = _minimum_phase_eq(24000)
        gain = lambda hz: abs(np.sum(h * np.exp(-2j*np.pi*hz*np.arange(len(h))/24000)))
        # A cinematic voice needs fundamental/body; the previous steep 135 Hz cut thinned it.
        self.assertGreater(gain(120) / gain(1000), .82)
        self.assertLess(gain(30) / gain(1000), .25)

    def test_dense_full_scale_audio_keeps_true_output_headroom(self):
        import numpy as np
        for rate in (16000, 24000, 48000):
            with self.subTest(rate=rate):
                t = np.arange(rate//2)/rate
                x = np.clip(.8*np.sin(2*np.pi*185*t)+.65*np.sin(2*np.pi*2800*t), -1, 1).astype(np.float32)
                fx = VoiceFx(rate=rate)
                y = np.concatenate([fx.process(x), fx.flush()])
                self.assertTrue(np.isfinite(y).all())
                self.assertLessEqual(float(np.abs(y).max()), .920001)

    def test_tail_release_continues_the_entire_voice_chain(self):
        import numpy as np
        t = np.arange(2400)/24000
        x = (.18*np.sin(2*np.pi*183*t)+.08*np.cos(2*np.pi*2200*t)).astype(np.float32)
        speech, reference = VoiceFx(), VoiceFx()
        speech.process(x); reference.process(x)
        tail = speech.drain(.05)
        continued = reference.process(np.zeros(1200, np.float32))
        # Release starts at unity; missing dry/EQ/doubler history produces a click here.
        np.testing.assert_allclose(tail[:24], continued[:24], atol=.00002)

    def test_tail_is_identical_across_release_chunk_sizes(self):
        import numpy as np
        x = VoiceFxTests().signal()[:9000]
        a, b = VoiceFx(), VoiceFx()
        a.process(x); b.process(x)
        whole = a.flush(.5)
        slices = np.concatenate([b.drain(.05) for _ in range(10)])
        np.testing.assert_allclose(whole, slices, atol=1e-5)
        self.assertEqual(0., float(slices[-1]))
        self.assertFalse(b.tail_live)

    def test_tiny_irregular_chunks_and_reset_preserve_density_state(self):
        import numpy as np
        rng = np.random.default_rng(19)
        x = (rng.normal(size=6000)*np.linspace(.01, .45, 6000)).astype(np.float32)
        whole = VoiceFx().process(x)
        fx = VoiceFx()
        parts, at = [], 0
        for size in (1, 7, 31, 1001, 4, 333, 19, 2400, 2204):
            parts.append(fx.process(x[at:at+size])); at += size
        np.testing.assert_allclose(whole, np.concatenate(parts), atol=1e-5)
        fx.reset()
        np.testing.assert_allclose(whole, fx.process(x), atol=1e-6)


class LatencyPlumbingTests(unittest.TestCase):
    """Cheap change detection, preview stitching and the OpenWhispr cleanup flag (latency workstream)."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).parent / 'runtime')
        self.addCleanup(self.tmp.cleanup)

    def wal_db(self, schema):
        import sqlite3
        path = Path(self.tmp.name) / 'gate.db'
        db = sqlite3.connect(path)
        db.execute('PRAGMA journal_mode=WAL')
        db.execute(schema); db.commit()
        self.addCleanup(db.close)
        return path, db

    def test_change_gate_sees_every_commit_and_forces_a_periodic_poll(self):
        from t3_voice_core import ChangeGate
        path, db = self.wal_db('CREATE TABLE t (x)')
        now = [0.0]
        gate = ChangeGate(path, refresh=.5, clock=lambda: now[0])
        self.assertTrue(gate.changed())          # first look always polls
        self.assertFalse(gate.changed())
        for value in range(5):
            db.execute('INSERT INTO t VALUES (?)', (value,)); db.commit()
            self.assertTrue(gate.changed())
            self.assertFalse(gate.changed())
        db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        db.execute('INSERT INTO t VALUES (9)'); db.commit()
        self.assertTrue(gate.changed())
        now[0] = .6                                # safety net: a full poll at least every `refresh`
        self.assertTrue(gate.changed())
        self.assertFalse(gate.changed())

    def test_change_gate_tolerates_a_missing_database(self):
        from t3_voice_core import ChangeGate
        gate = ChangeGate(Path(self.tmp.name) / 'absent.db', clock=lambda: 0.0)
        self.assertTrue(gate.changed())
        self.assertFalse(gate.changed())

    def test_idle_feed_poll_does_not_open_the_database(self):
        path, db = self.wal_db("CREATE TABLE transcriptions (id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT NOT NULL, "
                               "raw_text TEXT, status TEXT NOT NULL DEFAULT 'completed', deleted_at TEXT)")
        feed = OpenWhisprFeed(path)
        feed.poll(); feed.poll()
        with patch.object(feed, 'connect', side_effect=AssertionError('opened while idle')):
            self.assertEqual([], feed.poll())
        db.execute("INSERT INTO transcriptions (text, raw_text) VALUES ('Hello, Maeve.', 'hello maeve')"); db.commit()
        self.assertEqual(['Hello, Maeve.'], feed.poll())

    def test_openwhispr_rows_report_whether_openwhispr_already_cleaned_them(self):
        path, db = self.wal_db("CREATE TABLE transcriptions (id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT NOT NULL, "
                               "raw_text TEXT, status TEXT NOT NULL DEFAULT 'completed', deleted_at TEXT)")
        feed = OpenWhisprFeed(path)
        self.assertEqual([], feed.poll())
        db.execute("INSERT INTO transcriptions (text, raw_text) VALUES ('Fix the build.', 'uh fix the the build')")
        db.execute("INSERT INTO transcriptions (text, raw_text) VALUES (' Same words. ', 'Same words.')")
        db.execute("INSERT INTO transcriptions (text) VALUES ('No raw copy.')"); db.commit()
        rows = feed.poll()
        self.assertEqual(['Fix the build.', 'Same words.', 'No raw copy.'], rows)
        self.assertEqual([True, False, False], [row.cleaned for row in rows])
        self.assertTrue(all(row.row_id for row in rows))

    def test_idle_streaming_feed_does_not_open_the_database(self):
        import sqlite3
        path = Path(self.tmp.name) / 'state.sqlite'
        db = sqlite3.connect(path); self.addCleanup(db.close)
        db.execute('CREATE TABLE orchestration_v2_projection_messages (message_id TEXT PRIMARY KEY,thread_id TEXT,'
                   'run_id TEXT,role TEXT,streaming INTEGER,created_at TEXT,updated_at TEXT,payload_json TEXT)'); db.commit()
        feed = StreamingFeed(path, 'chosen')
        feed.poll()
        with patch.object(feed, 'connect', side_effect=AssertionError('opened while idle')):
            self.assertEqual([], feed.poll())

    def preview(self):
        from t3_voice_core import DictationPreview
        return DictationPreview(sample_rate=100, interval=0, window_seconds=20, min_seconds=.1,
                                commit_after=3.0, keep=1.5, pad=.5, tolerance=.3)

    def test_long_hold_commits_early_words_and_decodes_only_the_tail(self):
        preview = self.preview()
        session = preview.start()
        preview.push(b'a' * 800, voiced=True)                      # 4 s at 100 Hz
        preview.request(0)
        tokens = [' Please', ' keep', ' the', ' orb', ' fast']
        stamps = [0.2, 0.9, 1.6, 2.4, 3.1]
        self.assertEqual('Please keep the orb fast', preview.complete(session, 'Please keep the orb fast', tokens, stamps))
        # Words that started before 4 - 1.5 = 2.5 s end the committed text at the newest of them (' orb', 2.4 s);
        # the audio before 2.4 - 0.5 s is dropped, so the next request decodes only the tail.
        self.assertEqual('Please keep the', preview.committed)
        self.assertEqual(int(1.9 * 100) * 2, preview.base)
        preview.push(b'b' * 200, voiced=True)
        _, audio = preview.request(1)
        self.assertEqual(800 + 200 - preview.base, len(audio))
        # The new window starts at 1.9 s: it decodes 'the' again (a repeat of the committed tail), then continues.
        shown = preview.complete(session, 'The orb fast and calm', [' The', ' orb', ' fast', ' and', ' calm'],
                                 [0.1, 0.55, 1.2, 2.0, 2.6])
        self.assertEqual('Please keep the orb fast and calm', shown)

    def test_stitching_never_shows_text_from_a_previous_hold(self):
        preview = self.preview()
        old = preview.start()
        preview.push(b'a' * 800, voiced=True)
        preview.request(0)
        new = preview.start()
        self.assertIsNone(preview.complete(old, 'old words', [' old', ' words'], [0.5, 2.0]))
        self.assertEqual('', preview.committed)
        preview.push(b'b' * 80, voiced=True)
        preview.request(0)
        self.assertEqual('Fresh', preview.complete(new, 'Fresh', [' Fresh'], [0.1]))

    def test_window_continuing_a_sentence_drops_the_decoder_capital(self):
        from t3_voice_core import _continue_case
        self.assertEqual('library and more', _continue_case('Library and more', 'use our asset'))
        self.assertEqual('Library and more', _continue_case('Library and more', 'A full stop.'))
        self.assertEqual("I'm here", _continue_case("I'm here", 'and then'))
        self.assertEqual('GPU time', _continue_case('GPU time', 'the'))
        self.assertEqual('Words', _continue_case('Words', ''))

    def test_transcribe_result_keeps_token_times_and_rejects_malformed_ones(self):
        import sys
        import types
        import t3_voice_core
        replies = [json.dumps({'text': ' Hi there ', 'tokens': [' Hi', ' there'], 'timestamps': [0.1, 0.4]}),
                   json.dumps({'text': 'x', 'tokens': [' x'], 'timestamps': []})]

        class Socket:
            def send_binary(self, data): pass
            def recv(self): return replies.pop(0)
            def send(self, data): pass
            def close(self): pass
        fake = types.SimpleNamespace(create_connection=lambda *a, **k: Socket())
        with patch.dict(sys.modules, {'websocket': fake}):
            self.assertEqual({'text': 'Hi there', 'tokens': [' Hi', ' there'], 'timestamps': [0.1, 0.4]},
                             t3_voice_core.transcribe_result(bytes(64)))
            self.assertEqual({'text': 'x', 'tokens': [], 'timestamps': []}, t3_voice_core.transcribe_result(bytes(64)))

    def test_wake_queue_wakes_the_loop_on_every_notice(self):
        from t3_voice_core import WakeQueue
        notices = WakeQueue()
        self.assertFalse(notices.wake.is_set())
        notices.put_nowait(('dict-stop', 1.0))
        self.assertTrue(notices.wake.is_set())
        self.assertEqual(('dict-stop', 1.0), notices.get_nowait())
        background = WakeQueue(quiet=('active-thread',))
        background.put(('active-thread', None))
        self.assertFalse(background.wake.is_set())
        self.assertEqual(1, background.qsize())
        background.put(('review', None))
        self.assertTrue(background.wake.is_set())

    def test_timing_log_is_silent_without_a_path_and_never_raises(self):
        import t3_voice_core
        path = Path(self.tmp.name) / 'timing.log'
        with patch.object(t3_voice_core, 'TIMING_LOG', None):
            t3_voice_core.log_timing('nothing', ms=1.0)
        self.assertFalse(path.exists())
        with patch.object(t3_voice_core, 'TIMING_LOG', path):
            t3_voice_core.log_timing('review-shown', rowToReviewMs=12.345, words=3)
        record = json.loads(path.read_text('utf-8'))
        self.assertEqual(('review-shown', 12.3, 3), (record['event'], record['rowToReviewMs'], record['words']))
        with patch.object(t3_voice_core, 'TIMING_LOG', Path(self.tmp.name) / 'missing-dir' / 'x.log'):
            t3_voice_core.log_timing('ignored')
