import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from live_reader_core import MessageFeed, clean_prose


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'state.sqlite'
        self.db = sqlite3.connect(self.path)
        self.addCleanup(self.db.close)
        self.db.execute('CREATE TABLE orchestration_v2_projection_messages (message_id TEXT PRIMARY KEY,thread_id TEXT,run_id TEXT,role TEXT,streaming INTEGER,created_at TEXT,updated_at TEXT,payload_json TEXT)')
        self.counter = 0

    def add(self, mid, text, role='assistant', thread='chosen', streaming=0, run='run-1'):
        self.counter += 1
        stamp = f'2026-11-01T10:00:{self.counter:02d}Z'
        self.db.execute('INSERT OR REPLACE INTO orchestration_v2_projection_messages VALUES (?,?,?,?,?,?,?,?)',
                        (mid, thread, run, role, streaming, stamp, stamp, json.dumps({'text': text, 'creationSource': 'provider', 'createdBy': 'agent'})))
        self.db.commit()

    def test_history_is_not_replayed(self):
        self.add('old', 'Old answer.')
        feed = MessageFeed(self.path, 'chosen')
        self.assertEqual([], feed.poll())
        self.add('new', 'New answer.')
        self.assertEqual(['New answer.'], [m.text for m in feed.poll()])
        self.assertEqual([], feed.poll())

    def test_only_chosen_thread_assistant_complete_messages(self):
        feed = MessageFeed(self.path, 'chosen')
        self.add('user', 'Never read this', role='user')
        self.add('tool', 'Tool output', role='tool')
        self.add('other', 'Other thread', thread='other')
        self.add('partial', 'Unfinished', streaming=1)
        self.assertEqual([], feed.poll())
        self.add('partial', 'Finished answer.', streaming=0)
        self.assertEqual(['Finished answer.'], [m.text for m in feed.poll()])

    def test_stop_suppresses_whole_run_but_not_next_reply(self):
        feed = MessageFeed(self.path, 'chosen')
        self.add('one', 'First sentence.')
        self.assertEqual(1, len(feed.poll()))
        feed.suppress('run-1')
        self.add('two', 'More commentary.', run='run-1')
        self.add('three', 'New reply.', run='run-2')
        self.assertEqual(['New reply.'], [m.text for m in feed.poll()])

    def test_markdown_fences_links_and_indented_code(self):
        source = '# Explanation\n**Hello** [there](https://example.com).\n```python\nprint("SECRET")\n```\nAfter.\n\n    hidden_code()\n\nEnd `filename.py`.'
        result = clean_prose(source)
        self.assertNotIn('SECRET', result)
        self.assertNotIn('hidden_code', result)
        self.assertNotIn('https', result)
        self.assertEqual('Explanation. Hello there. After. End filename.py.', result)

    def test_unclosed_fence_is_silent_to_end(self):
        self.assertEqual('Before.', clean_prose('Before.\n~~~sh\nsecret log'))
        self.assertEqual('', clean_prose('```\nonly code'))

    def test_pause_can_discard_backlog(self):
        feed = MessageFeed(self.path, 'chosen')
        self.add('one', 'Missed while paused.')
        feed.discard_pending()
        self.assertEqual([], feed.poll())
        self.add('two', 'After resume.', run='run-2')
        self.assertEqual(['After resume.'], [m.text for m in feed.poll()])

    def test_suppressed_streaming_run_cannot_block_next_reply(self):
        feed = MessageFeed(self.path, 'chosen')
        self.add('abandoned', 'Partial', streaming=1)
        feed.suppress('run-1')
        self.add('next', 'Next answer.', run='run-2')
        self.assertEqual(['Next answer.'], [m.text for m in feed.poll()])

    def test_new_run_supersedes_abandoned_streaming_row(self):
        feed = MessageFeed(self.path, 'chosen')
        self.add('abandoned', 'Partial', streaming=1)
        self.add('next', 'Next answer.', run='run-2')
        self.assertEqual(['Next answer.'], [m.text for m in feed.poll()])


if __name__ == '__main__':
    unittest.main()
