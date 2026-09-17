import unittest

from OpenHeartsMusic.core.youtube import YTDLP_COMMON_OPTIONS


class YoutubeUserAgentTests(unittest.TestCase):
    def test_common_yt_dlp_headers_include_browser_user_agent(self):
        self.assertEqual(
            YTDLP_COMMON_OPTIONS["http_headers"]["User-Agent"],
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36 Edg/151.0.0.0",
        )


if __name__ == "__main__":
    unittest.main()
