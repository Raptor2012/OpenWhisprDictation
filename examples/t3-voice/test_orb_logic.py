"""Visibility and bubble rules of the orb engine, without audio, microphone or a window."""
import sys
import time
import unittest
from collections import deque

sys.argv = ['test']
import t3_voice
from live_reader_core import Message


def engine(**fields):
    e = t3_voice.Engine.__new__(t3_voice.Engine)
    defaults = dict(expanded=False, hovered=False, pin_until=0.0, pending=None, state='ready', confirmed=False,
                    sent_at=0.0, error_at=0.0, t3_min=False, bubble=None, bubble_until=0.0, bubble_seq=0,
                    bubble_run=None, silent=deque(), meta={})
    defaults.update(fields)
    e.__dict__.update(defaults)
    return e


class VisibilityTests(unittest.TestCase):
    def test_idle_orb_is_hidden(self):
        self.assertFalse(engine().wants_visible(time.monotonic()))

    def test_unconfirmed_noise_does_not_show_the_orb(self):
        now = time.monotonic()
        self.assertFalse(engine(state='hearing').wants_visible(now))
        self.assertTrue(engine(state='hearing', confirmed=True).wants_visible(now))

    def test_speaking_and_sending_show_the_orb(self):
        now = time.monotonic()
        for state in ('speaking', 'reading', 'transcribing', 'sending'):
            self.assertTrue(engine(state=state).wants_visible(now), state)

    def test_waiting_shows_briefly_then_hides(self):
        now = time.monotonic()
        self.assertTrue(engine(state='waiting', sent_at=now - 1).wants_visible(now))
        self.assertFalse(engine(state='waiting', sent_at=now - 5).wants_visible(now))

    def test_hover_pin_and_card_keep_it_visible(self):
        now = time.monotonic()
        self.assertTrue(engine(hovered=True).wants_visible(now))
        self.assertTrue(engine(expanded=True).wants_visible(now))
        self.assertTrue(engine(pin_until=now + 2).wants_visible(now))

    def test_bubble_only_keeps_orb_when_t3_is_minimized(self):
        now = time.monotonic()
        bubble = {'id': 1, 'who': 'maeve', 'text': 'Hi.', 'new': 0}
        self.assertFalse(engine(bubble=bubble, bubble_until=now + 3).wants_visible(now))
        self.assertTrue(engine(bubble=bubble, bubble_until=now + 3, t3_min=True).wants_visible(now))


class BubbleTests(unittest.TestCase):
    def test_chunks_of_one_reply_accumulate(self):
        e = engine()
        e.show_reply(Message('m1', 'run-1', 'First sentence.'))
        e.show_reply(Message('m1', 'run-1', 'Second sentence.'))
        self.assertEqual('First sentence. Second sentence.', e.bubble['text'])
        self.assertEqual(1, e.bubble['id'])
        self.assertEqual(len('First sentence. '), e.bubble['new'])

    def test_new_reply_or_user_turn_starts_a_new_bubble(self):
        e = engine()
        e.show_reply(Message('m1', 'run-1', 'Old reply.'))
        e.show_bubble('you', 'My question', None, 3.0)
        self.assertEqual(('you', 'My question', 2), (e.bubble['who'], e.bubble['text'], e.bubble['id']))
        e.show_reply(Message('m2', 'run-2', 'New reply.'))
        self.assertEqual(('maeve', 'New reply.', 3), (e.bubble['who'], e.bubble['text'], e.bubble['id']))

    def test_long_replies_keep_only_the_tail(self):
        e = engine()
        e.show_reply(Message('m1', 'run-1', 'a' * 1100))
        e.show_reply(Message('m1', 'run-1', 'b' * 300))
        self.assertEqual(1200, len(e.bubble['text']))
        self.assertTrue(e.bubble['text'].endswith('b' * 300))


if __name__ == '__main__':
    unittest.main()
