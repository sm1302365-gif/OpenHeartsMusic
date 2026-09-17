import unittest
from dataclasses import fields
from pathlib import Path
from unittest.mock import patch

from OpenHeartsMusic.core.mongo import MongoDB
from OpenHeartsMusic.core.youtube import YouTube
from OpenHeartsMusic.helpers._dataclass import Track
from OpenHeartsMusic.helpers._thumbnails import make_timeline


class DummyCache:
    def __init__(self):
        self.docs = {}

    async def find_one(self, query):
        return self.docs.get(query.get("_id"))

    async def update_one(self, query, update, upsert=False):
        self.docs[query["_id"]] = update.get("$set", {})

    async def delete_one(self, query):
        self.docs.pop(query.get("_id"), None)


class AutoplayTests(unittest.IsolatedAsyncioTestCase):
    def test_get_cookies_uses_absolute_project_paths(self):
        youtube = YouTube()
        cookie = youtube.get_cookies()

        if cookie:
            self.assertTrue(Path(cookie).is_absolute())

    def test_autostream_alias_is_registered(self):
        repo_root = Path(__file__).resolve().parents[1]
        autoplay_py = (
            repo_root / "OpenHeartsMusic" / "plugins" / "settings" / "autoplay.py"
        ).read_text(encoding="utf-8")

        self.assertIn('filters.command(["autoplay", "autostream"])', autoplay_py)

    def test_autoplay_help_button_uses_registered_callback(self):
        repo_root = Path(__file__).resolve().parents[1]
        inline_py = (
            repo_root / "OpenHeartsMusic" / "helpers" / "_inline.py"
        ).read_text(encoding="utf-8")
        callbacks_py = (
            repo_root / "OpenHeartsMusic" / "plugins" / "events" / "callbacks.py"
        ).read_text(encoding="utf-8")

        self.assertIn('text="🔄 Auto-Play Mode", callback_data="autoplay_help"', inline_py)
        self.assertIn('r"^(?:help|autoplay_help)"', callbacks_py)

    def test_now_playing_autoplay_button_uses_callback(self):
        repo_root = Path(__file__).resolve().parents[1]
        thumbnails_py = (
            repo_root / "OpenHeartsMusic" / "helpers" / "_thumbnails.py"
        ).read_text(encoding="utf-8")
        callbacks_py = (
            repo_root / "OpenHeartsMusic" / "plugins" / "events" / "callbacks.py"
        ).read_text(encoding="utf-8")

        self.assertIn('callback_data="toggle_autoplay"', thumbnails_py)
        self.assertIn('r"^toggle_autoplay$"', callbacks_py)

    def test_make_timeline_uses_full_progress_range(self):
        timelines = [
            make_timeline("00:00", "01:00"),
            make_timeline("00:30", "01:00"),
            make_timeline("01:00", "01:00"),
        ]
        bars = [timeline.split("  ")[1] for timeline in timelines]

        self.assertEqual({len(bar) for bar in bars}, {10})
        self.assertEqual(bars[0], "▱" * 10)
        self.assertEqual(bars[-1], "▬" * 10)

    def test_track_supports_video_autoplay_state(self):
        field_names = {field.name for field in fields(Track)}

        self.assertIn("video", field_names)
        self.assertTrue(
            Track(
                id="video-id",
                channel_name="channel",
                duration="1 min",
                duration_sec=60,
                title="Video",
                url="https://youtube.com/watch?v=video-id",
                video=True,
            ).video
        )

    async def test_autoplay_round_trip(self):
        db = MongoDB()
        db.cache = DummyCache()

        self.assertFalse(await db.get_autoplay(101))

        await db.set_autoplay(101, True)
        self.assertTrue(await db.get_autoplay(101))

        await db.set_autoplay(101, False)
        self.assertFalse(await db.get_autoplay(101))

    async def test_stream_url_resolves_audio_without_downloading(self):
        class FakeYDL:
            def __init__(self, options):
                self.options = options

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def extract_info(self, url, download=False):
                self.download = download
                return {"url": "https://audio.example/song.m4a"}

        with patch("OpenHeartsMusic.core.youtube.yt_dlp.YoutubeDL", FakeYDL), patch(
            "asyncio.to_thread", side_effect=lambda func, *args, **kwargs: func(*args)
        ):
            stream_url = await YouTube().stream_url("song-id")

        self.assertEqual(stream_url, "https://audio.example/song.m4a")

    async def test_stream_url_retries_after_youtube_reload_error(self):
        attempts = []

        class FakeYDL:
            def __init__(self, options):
                attempts.append(options)

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def extract_info(self, url, download=False):
                if len(attempts) == 1:
                    raise RuntimeError("The page needs to be reloaded")
                return {"url": "https://audio.example/recovered.m4a"}

        with patch("OpenHeartsMusic.core.youtube.yt_dlp.YoutubeDL", FakeYDL), patch(
            "OpenHeartsMusic.core.youtube.YouTube._cookie_options", return_value={"cookiefile": "stale.txt"}
        ), patch(
            "asyncio.to_thread", side_effect=lambda func, *args, **kwargs: func(*args)
        ):
            stream_url = await YouTube().stream_url("song-id")

        self.assertEqual(stream_url, "https://audio.example/recovered.m4a")
        self.assertEqual(len(attempts), 2)
        self.assertNotIn("cookiefile", attempts[1])

    async def test_related_autoplay_skips_current_track(self):
        class FakeYDL:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def extract_info(self, url, download=False):
                return {
                    "related_videos": [
                        {
                            "id": "current-song-id",
                            "title": "Current Song",
                            "uploader": "Current Artist",
                            "duration": 180,
                            "thumbnail": "https://example.com/current.jpg",
                            "view_count": "100k",
                            "url": "https://www.youtube.com/watch?v=current-song-id",
                        },
                        {
                            "id": "different-song-id",
                            "title": "Different Song",
                            "uploader": "Another Artist",
                            "duration": 220,
                            "thumbnail": "https://example.com/different.jpg",
                            "view_count": "200k",
                            "url": "https://www.youtube.com/watch?v=different-song-id",
                        },
                    ]
                }

        with patch("OpenHeartsMusic.core.youtube.yt_dlp.YoutubeDL", FakeYDL), patch(
            "asyncio.to_thread", side_effect=lambda func, *args, **kwargs: func()
        ):
            track = await YouTube().related("current-song-id", 0, parent_title="Current Song")

        self.assertIsNotNone(track)
        self.assertEqual(track.id, "different-song-id")
        self.assertNotEqual(track.id, "current-song-id")
        self.assertEqual(track.user, "Autoplay")

    async def test_related_autoplay_skips_chat_history(self):
        class FakeYDL:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def extract_info(self, url, download=False):
                return {
                    "related_videos": [
                        {"id": "already-played", "title": "Old Song", "duration": 180},
                        {"id": "new-song", "title": "New Song", "duration": 180},
                    ]
                }

        with patch("OpenHeartsMusic.core.youtube.yt_dlp.YoutubeDL", FakeYDL), patch(
            "asyncio.to_thread", side_effect=lambda func, *args, **kwargs: func()
        ):
            youtube = YouTube()
            youtube._autoplay_history[101] = ["already-played"]
            track = await youtube.related("current-song-id", 0, chat_id=101)

        self.assertIsNotNone(track)
        self.assertEqual(track.id, "new-song")
        self.assertIn("new-song", youtube._autoplay_history[101])

    async def test_random_autoplay_tracks_avoid_recent_history(self):
        class FakeYDL:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def extract_info(self, url, download=False):
                return {
                    "entries": [
                        {"id": "recent", "title": "Recent Song"},
                        {"id": "fresh", "title": "Fresh Song", "duration": 180},
                    ]
                }

        with patch("OpenHeartsMusic.core.youtube.yt_dlp.YoutubeDL", FakeYDL), patch(
            "asyncio.to_thread", side_effect=lambda func, *args, **kwargs: func()
        ):
            youtube = YouTube()
            youtube._autoplay_history[101] = ["recent"]
            track = await youtube.random_autoplay_track(101)

        self.assertIsNotNone(track)
        self.assertEqual(track.id, "fresh")
        self.assertEqual(youtube._autoplay_history[101], ["recent", "fresh"])

    def test_autoplay_candidate_filter_rejects_non_songs(self):
        self.assertFalse(YouTube._is_autoplay_song({
            "id": "radio",
            "title": "Top Hits Radio Live",
            "duration": 180,
            "is_live": True,
        }))
        self.assertFalse(YouTube._is_autoplay_song({
            "id": "mix",
            "title": "Bollywood Party Mix",
            "duration": 600,
        }))
        self.assertTrue(YouTube._is_autoplay_song({
            "id": "song",
            "title": "Popular Bollywood Song",
            "duration": 240,
        }))

    def test_autoplay_keywords_include_popular_bollywood(self):
        youtube_source = (
            Path(__file__).resolve().parents[1]
            / "OpenHeartsMusic"
            / "core"
            / "youtube.py"
        ).read_text(encoding="utf-8")

        self.assertIn('"popular Bollywood songs"', youtube_source)


if __name__ == "__main__":
    unittest.main()
