import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import test_live_reader
from t3_voice_core import McpSender, OpenWhisprFeed, Routes, StreamingFeed, UtteranceGate, send_message_cli


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


class UtteranceTests(unittest.TestCase):
    def test_speech_interrupts_before_silence_submits_once(self):
        gate = UtteranceGate(start_frames=3, silence_frames=4)
        self.assertEqual([], gate.push(b'a', True))
        self.assertEqual([], gate.push(b'b', True))
        self.assertEqual('start', gate.push(b'c', True)[0][0])
        for _ in range(3):
            self.assertEqual([], gate.push(b'z', False))
        events = gate.push(b'z', False)
        self.assertEqual('end', events[0][0])
        self.assertIn(b'abc', events[0][1])
        self.assertEqual([], gate.push(b'z', False))

    def test_short_noise_is_not_an_utterance(self):
        gate = UtteranceGate(start_frames=3, silence_frames=4)
        for voiced in (True, False, True, False, False):
            self.assertEqual([], gate.push(b'x', voiced))
