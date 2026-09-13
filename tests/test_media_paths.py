import unittest
from pathlib import Path


class MediaPathTests(unittest.TestCase):
    def test_download_directory_is_package_relative(self):
        telegram_py = Path(__file__).resolve().parents[1] / "OpenHeartsMusic" / "core" / "telegram.py"
        source = telegram_py.read_text(encoding="utf-8")

        self.assertIn("Path(__file__).resolve().parents[1] / \"downloads\"", source)
        self.assertIn(".resolve())", source)

    def test_stream_uses_normalized_path(self):
        calls_py = Path(__file__).resolve().parents[1] / "OpenHeartsMusic" / "core" / "calls.py"
        source = calls_py.read_text(encoding="utf-8")

        self.assertIn("Path(media.file_path).resolve().as_posix()", source)

    def test_stream_requires_audio_and_video_for_video_media(self):
        calls_py = Path(__file__).resolve().parents[1] / "OpenHeartsMusic" / "core" / "calls.py"
        source = calls_py.read_text(encoding="utf-8")

        self.assertIn("types.MediaStream.Flags.REQUIRED", source)
        self.assertIn("if is_video", source)
        self.assertIn("types.MediaStream.Flags.IGNORE", source)
        self.assertNotIn("-vcodec libx264", source)
        self.assertNotIn("-pix_fmt yuv420p", source)

    def test_audio_effect_stream_preserves_video(self):
        effects_py = Path(__file__).resolve().parents[1] / "OpenHeartsMusic" / "helpers" / "_audio_effects.py"
        source = effects_py.read_text(encoding="utf-8")

        self.assertIn("if is_video", source)
        self.assertIn('"video_flags": (', source)


if __name__ == "__main__":
    unittest.main()
