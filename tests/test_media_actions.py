"""媒体动作去重回归：快速连按不能被旧版 0.28 秒防抖吞掉。"""
import unittest

from pages_music import MusicPage


class _FakePlayer:
    @staticmethod
    def playbackState():
        return 0


class _FakePage:
    def __init__(self):
        self.player = _FakePlayer()
        self.calls = []

    def toggle_play(self):
        self.calls.append("play_pause")

    def play_next(self):
        self.calls.append("next")

    def play_prev(self):
        self.calls.append("prev")

    def stop(self):
        self.calls.append("stop")

    def _status(self, _text):
        pass


class MediaActionTest(unittest.TestCase):
    def test_rapid_next_is_not_swallowed(self):
        page = _FakePage()
        MusicPage._on_media_key(page, "next")
        MusicPage._on_media_key(page, "next")
        MusicPage._on_media_key(page, "next")
        self.assertEqual(page.calls, ["next", "next", "next"])

    def test_play_and_track_actions_dispatch(self):
        page = _FakePage()
        MusicPage._on_media_key(page, "play_pause")
        MusicPage._on_media_key(page, "prev")
        MusicPage._on_media_key(page, "stop")
        self.assertEqual(page.calls, ["play_pause", "prev", "stop"])


if __name__ == "__main__":
    unittest.main()
