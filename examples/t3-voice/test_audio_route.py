"""Endpoint watching: settle logic and signatures, without real audio devices."""
import threading
import time
import unittest
from unittest.mock import Mock, patch

import audio_route
from audio_route import EndpointWatch, endpoint_signature, settle


class SettleTests(unittest.TestCase):
    def test_returns_once_notifications_go_quiet(self):
        wake, stop = threading.Event(), threading.Event()
        self.assertTrue(settle(wake, stop, 0.01))

    def test_a_burst_of_notifications_extends_the_wait(self):
        wake, stop = threading.Event(), threading.Event()
        burst = threading.Timer(0.02, wake.set); burst.start()
        started = time.monotonic()
        self.assertTrue(settle(wake, stop, 0.05))
        self.assertGreaterEqual(time.monotonic() - started, 0.065)

    def test_stopping_ends_the_wait_without_firing(self):
        watch = EndpointWatch(Mock(), quiet=0.01)
        watch.stop()
        self.assertEqual('old', watch.check(Mock(return_value='new'), 'old'))
        watch.on_change.assert_not_called()


class CheckTests(unittest.TestCase):
    def test_fires_only_when_the_endpoints_really_changed(self):
        watch = EndpointWatch(Mock(), quiet=0.01)
        self.assertEqual('same', watch.check(Mock(return_value='same'), 'same'))
        watch.on_change.assert_not_called()
        self.assertEqual('headphones', watch.check(Mock(return_value='headphones'), 'speakers'))
        watch.on_change.assert_called_once()
        self.assertEqual(1, watch.changes)

    def test_a_failing_reroute_is_recorded_and_the_new_state_kept(self):
        watch = EndpointWatch(Mock(side_effect=RuntimeError('busy')), quiet=0.01)
        self.assertEqual('bt', watch.check(Mock(return_value='bt'), 'speakers'))
        self.assertEqual('RuntimeError', watch.error)


def device(ident):
    return Mock(GetId=Mock(return_value=ident))


class SignatureTests(unittest.TestCase):
    def test_defaults_and_active_sets_for_both_directions(self):
        render, capture = [device('r2'), device('r1')], [device('c1')]
        enumerator = Mock()
        enumerator.GetDefaultAudioEndpoint.side_effect = lambda flow, role: (render if flow == 0 else capture)[0]
        enumerator.EnumAudioEndpoints.side_effect = lambda flow, mask: Mock(
            GetCount=Mock(return_value=len(render if flow == 0 else capture)),
            Item=lambda i: (render if flow == 0 else capture)[i])
        with patch.object(audio_route, '_take_string', side_effect=lambda value: value):
            self.assertEqual(('r2', 'c1', ('r1', 'r2'), ('c1',)), endpoint_signature(enumerator))

    def test_no_capture_device_reads_as_empty_default(self):
        enumerator = Mock()
        enumerator.GetDefaultAudioEndpoint.side_effect = lambda flow, role: device('r1') if flow == 0 else (_ for _ in ()).throw(OSError())
        enumerator.EnumAudioEndpoints.side_effect = lambda flow, mask: Mock(
            GetCount=Mock(return_value=1 if flow == 0 else 0), Item=lambda i: device('r1'))
        with patch.object(audio_route, '_take_string', side_effect=lambda value: value):
            self.assertEqual(('r1', '', ('r1',), ()), endpoint_signature(enumerator))


if __name__ == '__main__':
    unittest.main()
