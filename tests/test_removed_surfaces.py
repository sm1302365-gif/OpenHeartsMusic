import pathlib
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


class RemovedSurfacesTests(unittest.TestCase):
    def test_live_video_format_is_preserved(self):
        repo_root = pathlib.Path(__file__).resolve().parents[1]
        youtube_py = (repo_root / "OpenHeartsMusic" / "core" / "youtube.py").read_text(encoding="utf-8")

        self.assertIn('"bestvideo[height<=1080]+bestaudio/"', youtube_py)
        self.assertIn('"bestaudio/best"', youtube_py)

    def test_removed_radio_and_stream_surfaces(self):
        repo_root = pathlib.Path(__file__).resolve().parents[1]

        play_py = (repo_root / "OpenHeartsMusic" / "plugins" / "playback" / "play.py").read_text(encoding="utf-8")
        example_radio = (repo_root / "OpenHeartsMusic" / "plugins" / "playback" / "example_radio.py").read_text(encoding="utf-8")
        locale = (repo_root / "OpenHeartsMusic" / "locales" / "en.json").read_text(encoding="utf-8")

        self.assertNotIn("/radio", play_py)
        self.assertNotIn("radio", example_radio.lower())
        self.assertNotIn("/radio", locale)
        self.assertNotIn("live streams", locale.lower())

    def test_removed_player_control_surface(self):
        repo_root = pathlib.Path(__file__).resolve().parents[1]

        inline_py = (repo_root / "OpenHeartsMusic" / "helpers" / "_inline.py").read_text(encoding="utf-8")
        callbacks_py = (repo_root / "OpenHeartsMusic" / "plugins" / "events" / "callbacks.py").read_text(encoding="utf-8")

        self.assertNotIn("now_playing_panel", inline_py)
        self.assertNotIn("player_close", callbacks_py)
        self.assertNotIn("player_pause", callbacks_py)
        self.assertNotIn("player_play", callbacks_py)
        self.assertNotIn("player_skip", callbacks_py)

    def test_broadcast_parser_has_single_implementation(self):
        repo_root = pathlib.Path(__file__).resolve().parents[1]
        broadcast_py = (repo_root / "OpenHeartsMusic" / "plugins" / "admin" / "broadcast.py").read_text(encoding="utf-8")

        self.assertEqual(broadcast_py.count("def _parse_broadcast_command"), 1)


if __name__ == "__main__":
    unittest.main()
