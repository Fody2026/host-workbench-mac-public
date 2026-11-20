"""跨平台静态/模拟测试：macOS 遥控解码与去重。

Windows 上没有 Quartz/AppKit，但 mac_remote 仍应可导入；以下测试不依赖真机。
"""
import unittest

import mac_remote as m


class TransportDecodeTest(unittest.TestCase):
    def test_play_pause_key_down(self):
        self.assertEqual(m.decode_transport(0x100A00), ("play_pause", True, False))

    def test_next_and_prev(self):
        self.assertEqual(m.decode_transport(0x110A00)[0], "next")
        self.assertEqual(m.decode_transport(0x120A00)[0], "prev")

    def test_key_up(self):
        self.assertEqual(m.decode_transport(0x100B00), ("play_pause", False, False))

    def test_repeat_bit(self):
        self.assertEqual(m.decode_transport(0x110A01), ("next", True, True))

    def test_unknown_key_ignored(self):
        self.assertEqual(m.decode_transport(0x220A00), (None, True, False))


class TransportGateTest(unittest.TestCase):
    def setUp(self):
        self.gate = m.TransportGate()

    def test_one_action_per_press(self):
        self.assertTrue(self.gate.feed("next", True, False))
        self.assertFalse(self.gate.feed("next", True, True))  # long-press repeat
        self.assertFalse(self.gate.feed("next", True, False))  # duplicate callback
        self.assertFalse(self.gate.feed("next", False, False))  # release
        self.assertTrue(self.gate.feed("next", True, False))  # next physical press

    def test_rapid_presses_are_not_debounced(self):
        self.assertTrue(self.gate.feed("next", True, False))
        self.gate.feed("next", False, False)
        self.assertTrue(self.gate.feed("next", True, False))
        self.gate.feed("next", False, False)
        self.assertTrue(self.gate.feed("next", True, False))

    def test_play_pause_and_track_are_independent(self):
        self.assertTrue(self.gate.feed("play_pause", True, False))
        self.assertTrue(self.gate.feed("next", True, False))
        self.assertFalse(self.gate.feed("play_pause", True, False))
        self.assertFalse(self.gate.feed("next", True, False))

    def test_release_unknown_action_is_noop(self):
        self.assertFalse(self.gate.feed("prev", False, False))


class HookAvailabilityTest(unittest.TestCase):
    def test_hook_reports_reason_on_non_macos(self):
        hook = m.MacMediaKeyHook(lambda action: None)
        if m.CG is None:
            self.assertFalse(hook.available)
            self.assertIn("Quartz", hook.error)
        hook.uninstall()


if __name__ == "__main__":
    unittest.main()
