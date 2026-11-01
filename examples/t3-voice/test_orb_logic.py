"""Visibility and bubble rules of the orb engine, without audio, microphone or a window."""
import sys
import time
import unittest
import queue
from collections import deque
from unittest.mock import Mock, patch
from types import SimpleNamespace
from pathlib import Path

sys.argv = ['test']
import t3_voice
from live_reader_core import Message


def engine(**fields):
    e = t3_voice.Engine.__new__(t3_voice.Engine)
    defaults = dict(panel_extra=False, review=None, delivery='immediate', follow_active=False, active_thread=None, dock=False, dict_state='', expanded=False, hovered=False, pin_until=0.0, pending=None, state='ready', confirmed=False,
                    sent_at=0.0, error_at=0.0, t3_min=False, bubble=None, bubble_until=0.0, bubble_seq=0,
                    bubble_run=None, silent=deque(), meta={})
    defaults.update(fields)
    e.__dict__.update(defaults)
    return e


class VisibilityTests(unittest.TestCase):
    def test_composer_appends_existing_draft_only_in_exact_destination(self):
        for active in ('one', 'other', 'already-pasted'):
            doc_value = Mock(Current=SimpleNamespace(Value='t3code://app/#/local/' + ('one' if active == 'already-pasted' else active)))
            edit_value = Mock(Current=SimpleNamespace(Value='Existing draft\nDictated words.' if active == 'already-pasted' else 'Existing draft'))
            edit_value.SetValue.side_effect = lambda text: setattr(edit_value.Current, 'Value', text)
            editor = Mock(Current=SimpleNamespace(ClassName='tiptap ProseMirror composer-tiptap'))
            editor.GetCurrentPattern.return_value = edit_value
            doc = Mock()
            doc.GetCurrentPattern.return_value = doc_value
            doc.FindAll.return_value = [editor]
            root = Mock()
            root.FindAll.return_value = [doc]
            automation = SimpleNamespace(AutomationElement=Mock(), ControlType=Mock(), PropertyCondition=Mock(),
                                         TreeScope=Mock(), ValuePattern=Mock())
            automation.AutomationElement.FromHandle.return_value = root
            e = engine(mode='openwhispr', routes=Mock(current=lambda t: True))
            with patch.dict(sys.modules, {'System': SimpleNamespace(IntPtr=lambda h: h),
                                          'System.Windows.Automation': automation}), \
                    patch.object(t3_voice, 'find_t3_window', return_value=123), \
                    patch.object(t3_voice.user32, 'GetForegroundWindow', return_value=0), \
                    patch.object(Path, 'read_text', return_value='local'):
                if active == 'one':
                    e.draft_in_composer(Mock(thread='one'), 'Dictated words.')
                    edit_value.SetValue.assert_called_once_with('Existing draft\n\nDictated words.')
                elif active == 'other':
                    with self.assertRaises(RuntimeError):
                        e.draft_in_composer(Mock(thread='one'), 'Dictated words.')
                    edit_value.SetValue.assert_not_called()
                else:
                    e.draft_in_composer(Mock(thread='one'), 'Dictated words.')
                    edit_value.SetValue.assert_not_called()

    def test_delivery_modes_stage_or_draft_without_sending(self):
        for mode in ('immediate', 'review', 'composer'):
            e = engine(delivery=mode, cleanup=False, routes=Mock(current=lambda t: True),
                       notice=queue.Queue(), draft_in_composer=Mock())
            with patch.object(t3_voice, 'send_message') as send:
                ticket = Mock(thread='one')
                e.deliver_text('My words.', ticket, 20, time.perf_counter())
                if mode == 'immediate':
                    send.assert_called_once_with('one', 'My words.')
                else:
                    send.assert_not_called()
                if mode == 'review':
                    self.assertEqual('review', e.notice.get_nowait()[0])
                if mode == 'composer':
                    e.draft_in_composer.assert_called_once_with(ticket, 'My words.')

    def test_stale_transcript_never_sends_or_writes_a_draft(self):
        e = engine(delivery='composer', cleanup=False, routes=Mock(current=lambda t: False),
                   notice=queue.Queue(), draft_in_composer=Mock())
        with patch.object(t3_voice, 'send_message') as send:
            e.deliver_text('Stale words.', Mock(thread='one'), 0, 0)
            send.assert_not_called()
            e.draft_in_composer.assert_not_called()
        self.assertEqual('discarded', e.notice.get_nowait()[0])

    def test_review_blocks_follow_and_keeps_preview_visible(self):
        e = engine(review={'id': 1}, follow_active=True, active_thread={'id': 'two'}, thread='one', select=Mock())
        e.follow_tick()
        e.select.assert_not_called()
        self.assertTrue(e.wants_visible(time.monotonic()))
        self.assertEqual(t3_voice.BUBBLE, e.target_size())

    def test_review_does_not_send_until_confirmed_and_only_once(self):
        ticket = object()  # opaque ticket; the mock verifies identity
        e = engine(lock=__import__('threading').RLock(), review={'id': 7, 'ticket': ticket, 'started': 1, 'asr': 2},
                   dispatch=Mock(), update_mic=Mock(), set_review_focus=Mock())
        e.confirm_review(6, 'wrong preview')
        e.dispatch.assert_not_called()
        e.confirm_review(7, 'Edited transcript')
        e.dispatch.assert_called_once_with('Edited transcript', ticket, 2, 1, approved=True)
        e.confirm_review(7, 'duplicate')
        self.assertEqual(1, e.dispatch.call_count)

    def test_follow_requires_a_resolved_active_thread(self):
        e = engine(follow_active=True, thread='one', routes=Mock(preferences={'one': True}))
        self.assertFalse(e.voice_on())
        e.active_thread = {'id': 'one'}
        self.assertTrue(e.voice_on())
        e.follow_active = False
        e.active_thread = None
        self.assertTrue(e.voice_on())

    def test_manual_selection_pins_and_automatic_selection_preserves_voice(self):
        for automatic in (True, False):
            prefs = Mock()
            routes = Mock(preferences={'one': True})
            e = engine(follow_active=True, thread='one', routes=routes, prefs=prefs,
                       lock=__import__('threading').RLock(), stop=Mock(), after_route_change=Mock(), threads=[])
            with patch.object(t3_voice, 'StreamingFeed'):
                e.select('two', automatic=automatic)
            self.assertEqual(automatic, e.follow_active)
            self.assertEqual('two', e.thread)
            if automatic:
                routes.enable.assert_called_once_with(True)
            else:
                prefs.set.assert_any_call('followActive', False)

    def test_follow_does_not_enable_a_previously_enabled_destination_when_voice_is_off(self):
        routes = Mock(preferences={'one': False, 'two': True})
        e = engine(follow_active=True, thread='one', routes=routes, prefs=Mock(),
                   lock=__import__('threading').RLock(), stop=Mock(), after_route_change=Mock(), threads=[])
        with patch.object(t3_voice, 'StreamingFeed'):
            e.select('two', automatic=True)
        routes.enable.assert_called_once_with(False)

    def test_follow_changes_only_when_no_capture_is_in_flight(self):
        e = engine(follow_active=True, active_thread={'id': 'two', 'title': 'Two'}, thread='one',
                   select=Mock(), dictating=False, gate=Mock(frames=None), voice_on=lambda: True)
        e.follow_tick()
        e.select.assert_called_once_with('two', automatic=True)
        for state in ('hearing', 'transcribing', 'sending'):
            e.select.reset_mock()
            e.state = state
            e.follow_tick()
            e.select.assert_not_called()
        e.state = 'ready'
        e.dict_state = 'processing'
        e.follow_tick()
        e.select.assert_not_called()

    def test_manual_pin_does_not_follow(self):
        e = engine(active_thread={'id': 'two'}, thread='one', select=Mock())
        e.follow_tick()
        e.select.assert_not_called()

    def test_dictation_completion_and_failure_feedback(self):
        for status, text, expected in [('completed', 'Pasted words.', 'done'), ('failed', '', 'failed')]:
            e = engine(dict_state='processing', env_read_at=float('inf'), manage_pill=Mock(),
                       dict_watch=Mock(poll=lambda: [{'status': status, 'text': text, 'error': 'No audio'}]))
            e.dictation_tick()
            self.assertEqual(expected, e.dict_state)
            self.assertGreater(e.dict_until, time.monotonic())

    def test_dictation_suppresses_handsfree_capture_and_cooldown(self):
        for dictating, quiet_until in [(True, 0), (False, time.monotonic() + 1)]:
            gate = t3_voice.UtteranceGate()
            gate.push(b'x', True)
            gate.push(b'x', True)
            e = engine(listening=True, dictating=dictating, dict_quiet_until=quiet_until,
                       gate=gate, vad=Mock(), notice=Mock())
            e.mic_callback(bytes(t3_voice.FRAME * 2), t3_voice.FRAME, None, None)
            self.assertIsNone(gate.frames)
            e.vad.is_speech.assert_not_called()
            e.notice.put.assert_not_called()

    def test_toolbar_and_dictation_remain_visible(self):
        now = time.monotonic()
        self.assertTrue(engine(dock=True).wants_visible(now))
        for state in ('dictating', 'processing', 'done', 'failed'):
            self.assertTrue(engine(dict_state=state).wants_visible(now))

    def test_toolbar_sizes_and_expired_bubble(self):
        now = time.monotonic()
        e = engine(dock=True, t3_min=True, bubble={'text': 'old'}, bubble_until=now - 1)
        self.assertEqual(t3_voice.BAR, e.target_size())
        e.bubble_until = now + 3
        self.assertEqual(t3_voice.BAR_BUBBLE, e.target_size())
        e.expanded = True
        self.assertEqual(t3_voice.BAR_CARD, e.target_size())

    def test_mic_update_does_not_skip_new_dictation(self):
        feed = Mock(cursor=42)
        e = engine(ready=False, voice_on=lambda: False, mode='openwhispr', mic_muted=False,
                   dictating=False, mic_stream=None, openwhispr=feed)
        e.update_mic()
        self.assertEqual(42, feed.cursor)

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
