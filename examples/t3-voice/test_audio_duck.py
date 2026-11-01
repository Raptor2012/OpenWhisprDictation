import json
import tempfile
import time
import unittest
from pathlib import Path

import audio_duck
from audio_duck import DUCK_LEVEL, AudioDucker, DuckBook, step_factor


class DuckBookTests(unittest.TestCase):
    def test_nothing_is_touched_while_not_ducking(self):
        self.assertEqual({}, DuckBook().plan({'music': .8}, 1.0))

    def test_each_session_drops_to_ten_percent_of_its_own_level_and_restores_exactly(self):
        book = DuckBook()
        sessions = {'music': .8, 'video': .5}
        changes = book.plan(sessions, DUCK_LEVEL)
        self.assertAlmostEqual(.08, changes['music'])
        self.assertAlmostEqual(.05, changes['video'])
        sessions.update(changes)
        restored = book.plan(sessions, 1.0)
        self.assertAlmostEqual(.8, restored['music'])
        self.assertAlmostEqual(.5, restored['video'])
        self.assertEqual({}, book.original)

    def test_app_that_starts_mid_duck_is_ducked_too(self):
        book = DuckBook()
        sessions = {'music': 1.0}
        sessions.update(book.plan(sessions, DUCK_LEVEL))
        sessions['browser'] = .6
        self.assertAlmostEqual(.06, book.plan(sessions, DUCK_LEVEL)['browser'])

    def test_user_slider_change_while_ducked_becomes_the_level_to_restore(self):
        book = DuckBook()
        sessions = {'music': 1.0}
        sessions.update(book.plan(sessions, DUCK_LEVEL))
        sessions['music'] = .05                      # the user turned it down in the Volume Mixer
        book.plan(sessions, DUCK_LEVEL)
        self.assertAlmostEqual(.5, book.plan(sessions, 1.0)['music'])

    def test_final_restore_is_exact_even_after_a_nearly_complete_fade(self):
        book = DuckBook()
        sessions = {'music': .8}
        sessions.update(book.plan(sessions, DUCK_LEVEL))
        sessions.update(book.plan(sessions, .9997))      # last fade step lands within rounding of the original
        self.assertEqual(.8, book.plan(sessions, 1.0).get('music', sessions['music']))

    def test_closed_sessions_are_forgotten(self):
        book = DuckBook()
        book.plan({'music': 1.0}, DUCK_LEVEL)
        book.plan({}, DUCK_LEVEL)
        self.assertEqual({}, book.original)


class FadeTests(unittest.TestCase):
    def test_ducks_quickly_and_recovers_gently(self):
        f, t = 1.0, 0.0
        while f > DUCK_LEVEL:
            f, t = step_factor(f, True, .01), t + .01
        self.assertLessEqual(t, audio_duck.FADE_DOWN + .02)
        t = 0.0
        while f < 1.0:
            f, t = step_factor(f, False, .01), t + .01
        self.assertGreaterEqual(t, audio_duck.FADE_UP - .02)


class FakeMixer:
    sessions = {}

    def __init__(self, exclude_pids=(), only_pids=None):
        self.exclude = exclude_pids

    def scan(self):
        return dict(FakeMixer.sessions)

    def set(self, key, level):
        FakeMixer.sessions[key] = level


def wait_until(predicate, timeout=3.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(.01)
    return False


class AudioDuckerTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.journal = Path(self.dir.name) / 'duck.json'
        FakeMixer.sessions = {'music': .8, 'video': .5}

    def tearDown(self):
        self.dir.cleanup()

    def test_want_ducks_other_sessions_journals_them_and_restores_on_release(self):
        ducker = AudioDucker(self.journal, exclude_pids={1234}, mixer_factory=FakeMixer).start()
        try:
            ducker.want = True
            self.assertTrue(wait_until(lambda: abs(FakeMixer.sessions['music'] - .08) < 1e-6))
            self.assertAlmostEqual(.05, FakeMixer.sessions['video'])
            self.assertEqual({'music': .8, 'video': .5}, json.loads(self.journal.read_text('utf-8')))
            ducker.want = False
            self.assertTrue(wait_until(lambda: abs(FakeMixer.sessions['music'] - .8) < 1e-6))
            self.assertAlmostEqual(.5, FakeMixer.sessions['video'])
            self.assertTrue(wait_until(lambda: not self.journal.exists()))
        finally:
            ducker.stop()
        self.assertEqual('', ducker.error)

    def test_stop_while_ducked_restores_before_exiting(self):
        ducker = AudioDucker(self.journal, mixer_factory=FakeMixer).start()
        ducker.want = True
        self.assertTrue(wait_until(lambda: FakeMixer.sessions['music'] < .1))
        ducker.stop()
        self.assertAlmostEqual(.8, FakeMixer.sessions['music'])
        self.assertFalse(self.journal.exists())

    def test_crash_journal_is_restored_on_next_start(self):
        FakeMixer.sessions = {'music': .08}
        self.journal.write_text(json.dumps({'music': .8, 'gone': .4}), 'utf-8')
        ducker = AudioDucker(self.journal, mixer_factory=FakeMixer).start()
        try:
            self.assertTrue(wait_until(lambda: abs(FakeMixer.sessions['music'] - .8) < 1e-6))
            self.assertFalse(self.journal.exists())
        finally:
            ducker.stop()


if __name__ == '__main__':
    unittest.main()
