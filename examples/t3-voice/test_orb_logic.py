"""Visibility and bubble rules of the orb engine, without audio, microphone or a window."""
import sys
import time
import unittest
import queue
import threading
from collections import deque
from unittest.mock import Mock, patch
from types import SimpleNamespace
from pathlib import Path

sys.argv = ['test']
import t3_voice
from live_reader_core import Message


def engine(**fields):
    e = t3_voice.Engine.__new__(t3_voice.Engine)
    defaults = dict(review_poll_at=0,dictation_started_wall=0,settled_feed_run='',synthesis_done_run='',agent={},visual_events={'sent':0,'interrupt':0},high_contrast=False,reduced_motion=False,choosing_delivery=False, mic_device="", speaker_device="", asr_pending=0, panel_extra=False, review=None, delivery='immediate', follow_active=False, active_thread=None, dock=False, dict_state='', expanded=False, hovered=False, pin_until=0.0, pending=None, state='ready', confirmed=False,
                    sent_at=0.0, error_at=0.0, t3_min=False, bubble=None, bubble_until=0.0, bubble_seq=0,
                    bubble_run=None, silent=deque(), meta={}, dict_preview_text='', dict_preview_until=0,
                    dict_preview_session=0, dict_preview=None, dictating=False, mic_level=0, current=None,
                    bubble_layout_until=0,mic_bands=[0.0]*11,mic_peak=0)
    defaults.update(fields)
    e.__dict__.update(defaults)
    return e


class VisibilityTests(unittest.TestCase):
    def test_a_previous_completion_cannot_replace_the_current_held_preview(self):
        e=engine(dictating=True,dict_state='dictating',dict_preview_text='I am still speaking',
                 env_read_at=float('inf'),manage_pill=Mock(),
                 dict_watch=Mock(poll=lambda:[{'status':'completed','text':'Previous dictation','error':''}]))
        e.dictation_tick()
        self.assertEqual('dictating',e.dict_state)
        self.assertEqual('I am still speaking',e.dictation_bubble(time.monotonic())['text'])
        self.assertTrue(e.dictation_bubble(time.monotonic())['live'])

    def test_short_voice_peaks_survive_between_ui_polls_then_decay(self):
        e=engine(mic_level=0)
        e.mic_callback((1600).to_bytes(2,'little',signed=True)*t3_voice.FRAME,t3_voice.FRAME,None,None)
        peak=e.mic_level
        e.mic_callback(bytes(t3_voice.FRAME*2),t3_voice.FRAME,None,None)
        self.assertGreater(e.mic_level,peak*.7)
        self.assertLess(e.mic_level,peak)

    def test_preview_never_delivers_and_release_rejects_late_recognition(self):
        preview=t3_voice.DictationPreview()
        e=engine(dict_preview=preview,notice=queue.Queue(),dispatch=Mock(),dict_state='dictating')
        session=preview.start()
        preview.push(b'a'*32000)
        request=preview.request(0)
        with patch.object(t3_voice,'transcribe',return_value='Words still being spoken'), patch.object(t3_voice,'send_message') as send:
            e.preview_audio(*request)
            kind,value=e.notice.get_nowait()
            self.assertEqual('dict-preview',kind)
            e.accept_dictation_preview(*value)
            self.assertEqual('Words still being spoken',e.dict_preview_text)
            preview.push(b'b'*32000)
            preview.request(2)
            preview.stop()
            e.accept_dictation_preview(session,'Late words after release',10,'')
            self.assertEqual('Words still being spoken',e.dict_preview_text)
            send.assert_not_called()
            e.dispatch.assert_not_called()

    def test_live_user_bubble_is_visible_with_t3_open_and_in_toolbar(self):
        for dock in (False,True):
            e = engine(dict_state='dictating',dict_preview_text='These are my words',dock=dock)
            bubble = e.dictation_bubble(time.monotonic())
            self.assertEqual('These are my words',bubble['text'])
            self.assertEqual(('you',True),(bubble['who'],bubble['live']))
            self.assertEqual(t3_voice.BAR_BUBBLE if dock else t3_voice.BUBBLE,e.target_size())
            e.expanded=True
            self.assertIsNone(e.dictation_bubble(time.monotonic()))
            e.expanded=False;e.review={'id':1}
            self.assertIsNone(e.dictation_bubble(time.monotonic()))

    def test_final_user_text_lingers_then_expires_without_t3_minimized(self):
        now=time.monotonic()
        e=engine(dict_preview_text='Final words',dict_preview_until=now+3)
        self.assertTrue(e.wants_visible(now))
        self.assertEqual('Final words',e.dictation_bubble(now)['text'])
        self.assertIsNone(e.dictation_bubble(now+4))
        self.assertFalse(e.wants_visible(now+4))

    def test_new_dictation_replaces_an_unsent_draft(self):
        e = engine(review={'id':1,'text':'Old draft'},openwhispr=Mock(poll=lambda:['newer words']),
                   routes=Mock(ticket=lambda: 'ticket'),stop=Mock(),mic_muted=False)
        with patch.object(t3_voice.threading, 'Thread') as thread:
            e.forward_openwhispr()
        thread.assert_called_once()
        self.assertEqual(('newer words', 'ticket'), thread.call_args.kwargs['args'])

    def test_text_for_a_draft_already_sending_is_not_forwarded(self):
        e = engine(review={'id':1,'text':'Old draft','sending':True},openwhispr=Mock(poll=lambda:['more']),
                   routes=Mock(),stop=Mock(),mic_muted=False)
        e.forward_openwhispr()
        e.routes.ticket.assert_not_called()

    def test_level_monitor_opens_only_while_dictation_button_is_held(self):
        e = engine(ready=True, voice_on=lambda: True, mode='handsfree', mic_muted=False,
                   dictating=False,mic_stream=None,openwhispr=Mock())
        with patch.object(t3_voice.sd,'RawInputStream') as stream:
            e.update_mic()
            stream.assert_not_called()
            e.dictating=True
            e.update_mic()
            stream.assert_called_once()
            stream.return_value.start.assert_called_once()
            e.dictating=False
            e.update_mic()
            stream.return_value.abort.assert_called_once()
            stream.return_value.close.assert_called_once()

    def test_microphone_never_endpoints_or_delivers_even_if_legacy_listening_flag_is_set(self):
        for dictating in (False, True):
            gate = Mock()
            e = engine(listening=True, dictating=dictating, dict_quiet_until=0, gate=gate, vad=Mock(), notice=Mock())
            e.mic_callback(bytes(t3_voice.FRAME*2),t3_voice.FRAME,None,None)
            gate.push.assert_not_called()
            e.vad.is_speech.assert_not_called()
            e.notice.put.assert_not_called()

    def test_expanded_panels_stay_inside_monitor_work_area(self):
        for anchor in ((1900,1070), (20,1070), (960,20)):
            cx, bottom = t3_voice.clamp_anchor(anchor, (480,504), (0,0,1920,1080))
            self.assertGreaterEqual(cx-240, 0)
            self.assertLessEqual(cx+240, 1920)
            self.assertGreaterEqual(bottom-504, 0)
            self.assertLessEqual(bottom, 1080)

    def test_all_recorder_overlays_are_hidden_and_new_windows_are_discovered(self):
        e = engine(pill_hwnds=set(), pill_scan_at=0, hide_pill=True, quit=Mock(is_set=lambda: False))
        with patch.object(t3_voice, 'find_openwhispr_pills', return_value=[11, 22]) as find, \
                patch.object(t3_voice, 'set_hidden_region') as hide, \
                patch.object(t3_voice.user32, 'IsWindow', return_value=True):
            e.manage_pill(force=True)
            self.assertEqual({11,22}, e.pill_hwnds)
            self.assertEqual({(11,True),(22,True)}, {call.args for call in hide.call_args_list})
            find.return_value = [11,22,33]
            e.manage_pill(force=True)
            self.assertIn(33, e.pill_hwnds)
            hide.assert_any_call(33, True)

    def test_overlay_matching_keeps_settings_windows_available(self):
        self.assertTrue(t3_voice.is_dictation_overlay('Voice Recorder', 0, 0))
        self.assertTrue(t3_voice.is_dictation_overlay('OpenWhispr', 0x14020000, 0x08200008))
        self.assertFalse(t3_voice.is_dictation_overlay('OpenWhispr', 0x00C00000, 0))
        self.assertFalse(t3_voice.is_dictation_overlay('Control Panel', 0, 0x08000000))

    def test_punctuation_and_length_never_bypass_continuation_grace(self):
        for text in ('I was thinking.', ' '.join(['word'] * 20)):
            e = engine(routes=Mock(current=lambda t: True), dispatch=Mock())
            e.accept_transcript(text, 'ticket', 10, 1)
            e.dispatch.assert_not_called()
            self.assertEqual(text, e.pending['text'])
            self.assertGreater(e.pending['deadline'], time.monotonic() + .5)

    def test_continuation_merges_and_waits_until_capture_and_asr_finish(self):
        e = engine(routes=Mock(current=lambda t: True), dispatch=Mock(), gate=Mock(frames=None))
        e.accept_transcript('I was thinking.', 'ticket', 10, 1)
        e.gate.frames = [b'voice']
        e.accept_transcript('We should try again.', 'ticket', 20, 2)
        self.assertEqual('hearing', e.state)
        self.assertIsNone(e.pending['deadline'])
        e.pending['deadline'] = time.monotonic() - 1
        e.flush_pending(time.monotonic())
        e.dispatch.assert_not_called()
        e.gate.frames = None
        e.asr_pending = 1
        e.flush_pending(time.monotonic())
        e.dispatch.assert_not_called()
        e.asr_pending = 0
        e.flush_pending(time.monotonic())
        e.dispatch.assert_called_once_with('I was thinking. We should try again.', 'ticket', 30, 1)
        self.assertIsNone(e.pending)

    def test_stale_transcript_cannot_replace_current_pending_turn(self):
        pending = {'text': 'current', 'ticket': 'current-ticket'}
        e = engine(routes=Mock(current=lambda t: False), dispatch=Mock(), pending=pending.copy())
        e.accept_transcript('Old thread.', 'stale-ticket', 0, 0)
        self.assertEqual(pending, e.pending)
        e.dispatch.assert_not_called()

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
        ticket = SimpleNamespace(thread='chosen')  # opaque ticket; the mock verifies identity
        e = engine(lock=__import__('threading').RLock(), review={'id': 7, 'ticket': ticket, 'started': 1, 'asr': 2},
                   dispatch=Mock(), update_mic=Mock(), set_review_focus=Mock())
        e.confirm_review(6, 'wrong preview')
        e.dispatch.assert_not_called()
        e.confirm_review(7, 'Edited transcript')
        e.dispatch.assert_called_once_with('Edited transcript', ticket, 2, 1, approved=True)
        e.confirm_review(7, 'duplicate')
        self.assertEqual(1, e.dispatch.call_count)
        self.assertIsNotNone(e.review)
        self.assertEqual('Edited transcript', e.review['text'])
        self.assertTrue(e.review['sending'])
        e.finish_review('Temporary network failure')
        self.assertFalse(e.review['sending'])
        self.assertEqual('Edited transcript', e.review['text'])
        e.confirm_review(7, 'Retry edited transcript')
        self.assertEqual(2, e.dispatch.call_count)
        e.finish_review()
        self.assertIsNone(e.review)

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
            if status == 'completed':
                self.assertEqual(text,e.dict_preview_text)
                self.assertGreater(e.dict_preview_until,time.monotonic())

    def test_dictation_suppresses_handsfree_capture_and_cooldown(self):
        for dictating, quiet_until in [(True, 0), (False, time.monotonic() + 1)]:
            gate = t3_voice.UtteranceGate()
            gate.push(b'x', True)
            gate.push(b'x', True)
            e = engine(listening=True, dictating=dictating, dict_quiet_until=quiet_until,
                       gate=gate, vad=Mock(), notice=Mock())
            e.mic_callback(bytes(t3_voice.FRAME * 2), t3_voice.FRAME, None, None)
            self.assertIsNotNone(gate.frames)  # the meter does not touch transcription buffers
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

    def test_reply_bubble_keeps_orb_visible_whether_or_not_t3_is_minimized(self):
        now = time.monotonic()
        bubble = {'id': 1, 'who': 'maeve', 'text': 'Hi.', 'new': 0}
        self.assertTrue(engine(bubble=bubble, bubble_until=now + 3).wants_visible(now))
        self.assertTrue(engine(bubble=bubble, bubble_until=now + 3, t3_min=True).wants_visible(now))
        self.assertTrue(engine(bubble=bubble, bubble_until=now + 3).reply_bubble_visible(now))
        self.assertFalse(engine(bubble=bubble, bubble_until=now - 5).wants_visible(now))


class BubbleTests(unittest.TestCase):
    def test_reply_bubble_stays_when_t3_is_restored_then_expires(self):
        e=engine(t3_min=True,t3_scan_at=float('inf'),hwnd=None,
                 bubble={'id':1,'who':'maeve','text':'Last words'},bubble_until=110)
        with patch.object(t3_voice.time,'monotonic',return_value=100):
            e.desktop_tick()
        e.t3_min=False
        with patch.object(t3_voice.time,'monotonic',return_value=101):
            self.assertEqual(t3_voice.BUBBLE,e.target_size())
        with patch.object(t3_voice.time,'monotonic',return_value=130):
            self.assertEqual(t3_voice.COMPACT,e.target_size())

    def test_playing_reply_does_not_expire_on_its_estimated_reading_time(self):
        now=time.monotonic()
        e=engine(t3_min=True,bubble={'id':1,'who':'maeve','text':'Still speaking'},bubble_run='run-1',
                 bubble_until=now-2,current=Message('m1','run-1','Still speaking'))
        self.assertTrue(e.reply_bubble_visible(now))
        self.assertEqual(t3_voice.BUBBLE,e.target_size())

    def test_native_window_keeps_bubble_space_until_the_exit_fade_finishes(self):
        for dock in (False,True):
            e=engine(dock=dock,t3_min=True,bubble={'id':1,'who':'maeve','text':'Finished'},bubble_until=100)
            with patch.object(t3_voice.time,'monotonic',return_value=100.05):
                self.assertEqual(t3_voice.BAR_BUBBLE if dock else t3_voice.BUBBLE,e.target_size())
            with patch.object(t3_voice.time,'monotonic',return_value=101):
                self.assertEqual(t3_voice.BAR if dock else t3_voice.COMPACT,e.target_size())

    def test_same_playing_run_does_not_reopen_a_new_bubble_after_estimate_expires(self):
        e=engine()
        e.show_reply(Message('m1','run-1','First words.'))
        e.bubble_until=time.monotonic()-10
        e.current=Message('m2','run-1','More words.')
        e.show_reply(e.current)
        self.assertEqual(1,e.bubble['id'])
        self.assertEqual('First words. More words.',e.bubble['text'])

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


class PlaybackMeterTests(unittest.TestCase):
    def test_microphone_and_playback_publish_different_frequency_bands(self):
        import numpy as np
        for rate in (16000,24000):
            peaks=[]
            for frequency in (400,1600):
                pcm=(np.sin(2*np.pi*frequency*np.arange(rate//50)/rate)*.003*32767).astype('<i2').tobytes()
                if rate==16000:
                    e=engine();e.mic_callback(pcm,320,None,None);bands=e.mic_bands
                else:
                    with patch('live_reader.sd.RawOutputStream'):
                        audio=t3_voice.ContinuousAudio()
                    audio.put(pcm,audio.epoch,__import__('threading').Event())
                    audio.callback(bytearray(960),480,None,SimpleNamespace(output_underflow=False));bands=audio.spectrum
                self.assertGreater(max(bands)-min(bands),.2)
                peaks.append(int(np.argmax(bands)))
            self.assertNotEqual(peaks[0],peaks[1])

    def test_meter_tracks_played_samples_instead_of_queued_generation(self):
        with patch('live_reader.sd.RawOutputStream'):
            audio=t3_voice.ContinuousAudio()
        cancel=__import__('threading').Event()
        audio.put((1600).to_bytes(2,'little',signed=True)*480,audio.epoch,cancel)
        self.assertEqual(0,audio.level)
        audio.callback(bytearray(960),480,None,SimpleNamespace(output_underflow=False))
        self.assertAlmostEqual(1600/32768,audio.level,places=5)
        peak=audio.level
        audio.callback(bytearray(960),480,None,SimpleNamespace(output_underflow=False))
        self.assertGreater(audio.level,peak*.7)
        self.assertLess(audio.level,peak)
        audio.reset()
        self.assertEqual(0,audio.level)


if __name__ == '__main__':
    unittest.main()


class CardWatchTests(unittest.TestCase):
    def watch(self, foreground, cursor_inside, focused=False, outside_for=0.0):
        e = engine(expanded=True, hwnd=100, review=None, expanded_at=time.monotonic() - 2,
                   card_focused=focused, outside_since=(time.monotonic() - outside_for) if outside_for else None)
        e.set_expanded = Mock()

        def cursor(point):
            point._obj.x, point._obj.y = (5, 5) if cursor_inside else (500, 500)
            return 1

        def rect(hwnd, r):
            r._obj.left, r._obj.top, r._obj.right, r._obj.bottom = 0, 0, 100, 100
            return 1
        with patch.object(t3_voice.user32, 'GetForegroundWindow', return_value=foreground), \
                patch.object(t3_voice.user32, 'GetAncestor', return_value=foreground), \
                patch.object(t3_voice.user32, 'GetCursorPos', side_effect=cursor), \
                patch.object(t3_voice.user32, 'GetWindowRect', side_effect=rect):
            e.card_watch(time.monotonic())
        return e

    def test_focus_blip_inside_the_card_keeps_it_open(self):
        self.watch(foreground=999, cursor_inside=True, focused=True).set_expanded.assert_not_called()

    def test_click_on_another_window_closes_it(self):
        self.watch(foreground=999, cursor_inside=False, focused=True).set_expanded.assert_called_once_with(False)

    def test_sustained_pointer_exit_closes_it(self):
        self.watch(foreground=100, cursor_inside=False, outside_for=3.0).set_expanded.assert_called_once_with(False)
        self.watch(foreground=100, cursor_inside=False, outside_for=1.0).set_expanded.assert_not_called()


class DeviceSwitchTests(unittest.TestCase):
    def test_failed_speaker_open_keeps_old_stream_and_preference(self):
        old = Mock()
        e = engine(lock=threading.RLock(), speaker_device='old', audio=old,
                   stop=Mock(), prefs=Mock(), cue=Mock(), device_index=Mock(return_value=7))
        with patch.object(t3_voice, 'ContinuousAudio', side_effect=RuntimeError('unavailable')):
            e.set_speaker_device('new')
        self.assertIs(e.audio, old)
        self.assertEqual('old', e.speaker_device)
        old.close.assert_not_called()
        e.prefs.set.assert_not_called()
        e.cue.assert_not_called()

    def test_speaker_switch_stops_swaps_closes_saves_and_chimes(self):
        old, fresh = Mock(), Mock()
        e = engine(lock=threading.RLock(), audio=old, stop=Mock(), prefs=Mock(),
                   cue=Mock(), device_index=Mock(return_value=7))
        def opened(**kwargs):
            e.stop.assert_called_once()
            old.close.assert_not_called()
            self.assertEqual({'device':7}, kwargs)
            return fresh
        with patch.object(t3_voice, 'ContinuousAudio', side_effect=opened):
            e.set_speaker_device('new')
        self.assertIs(e.audio, fresh)
        old.close.assert_called_once()
        e.prefs.set.assert_called_once_with('speakerDevice', 'new')
        e.cue.assert_called_once_with([523, 659], 60)

    def test_mic_switch_reopens_active_stream_and_saves_default(self):
        old = Mock()
        e = engine(lock=threading.RLock(), mic_stream=old, prefs=Mock(), update_mic=Mock())
        e.set_mic_device('usb mic')
        old.abort.assert_called_once()
        old.close.assert_called_once()
        self.assertIsNone(e.mic_stream)
        e.update_mic.assert_called_once()
        e.prefs.set.assert_called_with('micDevice', 'usb mic')
        e.set_mic_device('')
        self.assertEqual('', e.mic_device)
        e.prefs.set.assert_called_with('micDevice', '')


class NativeDropdownTests(unittest.TestCase):
    def test_open_dropdown_suspends_card_dismissal_and_resets_leave_timer(self):
        e=engine(choosing_delivery=True,expanded=True,hwnd=123,expanded_at=0,
                 outside_since=1,set_expanded=Mock())
        with patch.object(t3_voice.user32,'GetForegroundWindow') as foreground:
            e.card_watch(100)
        foreground.assert_not_called()
        e.set_expanded.assert_not_called()
        self.assertIsNone(e.outside_since)


class ReplyProgressTests(unittest.TestCase):
    def audio(self):
        with patch('live_reader.sd.RawOutputStream'):
            return t3_voice.ContinuousAudio()

    def play(self,audio,samples):
        audio.callback(bytearray(samples*2),samples,None,SimpleNamespace(output_underflow=False))

    def test_reply_progress_excludes_cues_and_stays_indeterminate_until_final(self):
        audio=self.audio();cancel=threading.Event()
        self.assertTrue(hasattr(audio,'begin_reply'),'reply tracking is missing')
        audio.put(bytes(20),audio.epoch,cancel)
        audio.begin_reply('run')
        audio.put(bytes(200),audio.epoch,cancel,reply_run='run')
        self.play(audio,60)
        self.assertEqual(50,audio.playback_progress()['played'])
        self.assertIsNone(audio.playback_progress()['fraction'])
        audio.finish_reply('run')
        self.assertEqual(.5,audio.playback_progress()['fraction'])
        self.play(audio,100)
        self.assertEqual(1,audio.playback_progress()['fraction'])
        self.assertFalse(audio.playback_progress()['active'])

    def test_sentence_continuity_and_interruption_clear_reply_progress(self):
        audio=self.audio();cancel=threading.Event()
        self.assertTrue(hasattr(audio,'begin_reply'),'reply tracking is missing')
        for i in range(2):
            audio.begin_reply('run');audio.put(bytes(100),audio.epoch,cancel,reply_run='run');self.play(audio,50)
        audio.finish_reply('run')
        self.assertEqual(100,audio.playback_progress()['total'])
        audio.reset()
        self.assertEqual('',audio.playback_progress()['run'])
        self.assertFalse(audio.playback_progress()['active'])


class VisualEngineTests(unittest.TestCase):
    def test_playback_becomes_determinate_after_final_synthesis_before_drain(self):
        with patch('live_reader.sd.RawOutputStream'):
            audio=t3_voice.ContinuousAudio()
        audio.begin_reply('run');audio.put(bytes(200),audio.epoch,threading.Event(),reply_run='run')
        e=engine(audio=audio,jobs=queue.Queue(),agent={'activity':'thinking','run':'run'},synthesis_done_run='run',settled_feed_run='run')
        self.assertTrue(hasattr(e,'finalize_playback'),'final synthesis integration missing')
        e.finalize_playback();self.assertIsNone(audio.playback_progress()['fraction'])
        e.agent['activity']='idle';e.synthesis_done_run=''
        e.finalize_playback();self.assertIsNone(audio.playback_progress()['fraction'])
        e.synthesis_done_run='run';e.finalize_playback()
        self.assertEqual(0,audio.playback_progress()['fraction'])
        self.assertTrue(audio.playback_progress()['active'])

    def test_appearance_preferences_round_trip_through_normal_api(self):
        import tempfile
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent/'runtime') as folder:
            path=Path(folder)/'prefs.json'
            e=engine(lock=threading.RLock(),prefs=t3_voice.Prefs(path))
            e.set_appearance(True,True)
            reopened=t3_voice.Prefs(path)
            self.assertTrue(reopened.get('highContrast'))
            self.assertTrue(reopened.get('reducedMotion'))

    def test_only_an_active_reply_triggers_interruption_event(self):
        for current,expected in ((None,0),(Message('m','r','Words'),1)):
            e=engine(current=current,audio=None,feed=None,generation=0,cancel=threading.Event(),jobs=queue.Queue())
            e.stop()
            self.assertEqual(expected,e.visual_events['interrupt'])

    def test_actual_agent_waits_remain_visible(self):
        for activity in ('approval','input','thinking'):
            self.assertTrue(engine(agent={'activity':activity}).wants_visible(time.monotonic()))


class PlaybackFinalizationEdgeTests(unittest.TestCase):
    def make(self, run):
        with patch('live_reader.sd.RawOutputStream'):
            audio=t3_voice.ContinuousAudio()
        audio.begin_reply(run);audio.put(bytes(200),audio.epoch,threading.Event(),reply_run=run)
        return engine(audio=audio,jobs=queue.Queue(),synthesis_done_run=run,current=Message('m',run,'Text'),
                      agent={'activity':'idle','run':'run'},settled_feed_run='')

    def test_final_metadata_waits_for_a_completed_feed_poll(self):
        e=self.make('run');e.finalize_playback()
        self.assertIsNone(e.audio.playback_progress()['fraction'])
        e.settled_feed_run='run';e.finalize_playback()
        self.assertEqual(0,e.audio.playback_progress()['fraction'])

    def test_voice_test_finishes_without_a_database_run(self):
        e=self.make('voice-test-123');e.finalize_playback()
        self.assertEqual(0,e.audio.playback_progress()['fraction'])


class HoverRecoveryTests(unittest.TestCase):
    def test_empty_transparent_window_space_cannot_keep_orb_hovered(self):
        e=engine(hovered=True,hwnd=100,expanded=False,scale=lambda:1)
        self.assertTrue(hasattr(e,'refresh_hover'),'native hover recovery missing')
        def rect(hwnd,r):
            r._obj.left,r._obj.top,r._obj.right,r._obj.bottom=0,0,340,300
        for point,want in [((170,234),True),((110,234),True),((20,20),False),((500,500),False)]:
            e.hovered=True
            def cursor(p):p._obj.x,p._obj.y=point
            with patch.object(t3_voice.user32,'GetWindowRect',side_effect=rect),patch.object(t3_voice.user32,'GetCursorPos',side_effect=cursor):
                e.refresh_hover()
            self.assertEqual(want,e.hovered,point)

    def test_toolbar_hover_is_limited_to_toolbar_in_bubble_window(self):
        e=engine(hovered=True,hwnd=100,dock=True,expanded=False,scale=lambda:1)
        self.assertTrue(hasattr(e,'refresh_hover'),'native hover recovery missing')
        def rect(hwnd,r):r._obj.left,r._obj.top,r._obj.right,r._obj.bottom=0,0,340,214
        def cursor(p):p._obj.x,p._obj.y=170,30
        with patch.object(t3_voice.user32,'GetWindowRect',side_effect=rect),patch.object(t3_voice.user32,'GetCursorPos',side_effect=cursor):e.refresh_hover()
        self.assertFalse(e.hovered)


class DirectReviewTests(unittest.TestCase):
    def test_manual_submission_clears_review_and_used_preview_without_resending(self):
        e=engine(review={'text':'Please inspect the build','ticket':SimpleNamespace(thread='chosen'),'since':10},
                 review_poll_at=0,state='reviewing',dict_state='done',dict_preview_text='Please inspect the build',dict_preview_until=999999999,
                 set_review_focus=Mock(),update_mic=Mock(),voice_on=lambda:True,dispatch=Mock())
        self.assertTrue(hasattr(e,'reconcile_direct_submission'),'direct submit acknowledgement missing')
        with patch.object(t3_voice,'matching_user_submission',return_value=True):e.reconcile_direct_submission()
        self.assertIsNone(e.review);self.assertEqual('',e.dict_preview_text);self.assertEqual('',e.dict_state)
        self.assertEqual('ready',e.state);e.dispatch.assert_not_called()

    def test_in_flight_orb_send_is_not_acknowledged_as_a_manual_submission(self):
        e=engine(review={'sending':True},review_poll_at=0)
        self.assertTrue(hasattr(e,'reconcile_direct_submission'),'direct submit acknowledgement missing')
        with patch.object(t3_voice,'matching_user_submission',return_value=True) as read:e.reconcile_direct_submission()
        read.assert_not_called();self.assertIsNotNone(e.review)


class DirectSubmissionSendRaceTests(unittest.TestCase):
    def test_manual_submit_is_rechecked_before_orb_send(self):
        e=engine(lock=threading.RLock(),review={'id':7,'text':'Inspect the build','ticket':SimpleNamespace(thread='chosen'),'since':10,'asr':0,'started':1},
                 review_poll_at=time.monotonic()+10,state='reviewing',set_review_focus=Mock(),update_mic=Mock(),voice_on=lambda:True,dispatch=Mock())
        with patch.object(t3_voice,'matching_user_submission',return_value=True):e.confirm_review(7,'Inspect the build')
        self.assertIsNone(e.review)
        e.dispatch.assert_not_called()


class EditedDirectReviewTests(unittest.TestCase):
    def test_latest_review_edit_wins_out_of_order_updates(self):
        e=engine(lock=threading.RLock(),review={'id':7,'text':'Original'})
        self.assertTrue(hasattr(e,'update_review_text'),'review edit synchronization missing')
        e.update_review_text(7,'Corrected text',2)
        e.update_review_text(7,'Stale text',1)
        self.assertEqual('Corrected text',e.review['text'])
        e.update_review_text(6,'Wrong review',3)
        self.assertEqual('Corrected text',e.review['text'])

    def test_confirm_checks_the_current_edited_text_for_manual_submission(self):
        e=engine(lock=threading.RLock(),review={'id':7,'text':'Original text','ticket':SimpleNamespace(thread='chosen'),'since':10,'asr':0,'started':1},
                 state='reviewing',set_review_focus=Mock(),update_mic=Mock(),voice_on=lambda:True,dispatch=Mock())
        with patch.object(t3_voice,'matching_user_submission',side_effect=lambda path,thread,text,since:text=='Corrected text'):
            e.confirm_review(7,'Corrected text')
        self.assertIsNone(e.review);e.dispatch.assert_not_called()
