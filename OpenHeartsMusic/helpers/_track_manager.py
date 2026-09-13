# ==============================================================================
# _track_manager.py - Track Download & Effect Management
# ==============================================================================
# Manages song downloads and effect application for playback control.
# Integrates with the existing V3 call system via MediaStream.
# ==============================================================================

import asyncio
import os
from pathlib import Path

import yt_dlp

from OpenHeartsMusic import config, logger


class TrackManager:
    """
    Manages track downloads and effect application.

    Features:
    - Download songs from YouTube via yt_dlp
    - Cache downloads locally
    - Apply effects via FFmpeg filters (not file preprocessing)
    - Per-chat track tracking

    Example:
        tm = TrackManager()

        # Download a song
        original_path = await tm.download_track("Faded Alan Walker")

        # Track is cached locally at: downloads/YouTube_ID.mp3
        # Effect versions created on-demand (not stored, applied via ffmpeg -af)

        # Get path for original
        path = await tm.get_track_path(chat_id, "original")
    """

    # Directory to store downloads
    DOWNLOADS_DIR = Path(config.DOWNLOAD_PATH) if hasattr(config, "DOWNLOAD_PATH") else Path("downloads")

    def __init__(self):
        """Initialize TrackManager and ensure download directory exists."""
        self.DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

        # Cache: chat_id -> {"original": path, "title": title, "url": url}
        self._chat_tracks = {}

    async def download_track(self, query: str) -> str | None:
        """
        Download a track from YouTube and save it locally.

        Args:
            query: Song name or YouTube URL

        Returns:
            Path to downloaded MP3 file, or None if download failed

        Example:
            >>> path = await tm.download_track("Faded Alan Walker")
            >>> print(path)
            downloads/dQw4w9WgXcQ.mp3
        """
        ydl_opts = {
            "format": "bestaudio/best",
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ],
            "outtmpl": str(self.DOWNLOADS_DIR / "%(id)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
        }

        try:
            def _download():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    # If query is a URL, download it directly; otherwise search
                    search_query = query if "youtube.com" in query or "youtu.be" in query else f"ytsearch1:{query}"
                    info = ydl.extract_info(search_query, download=True)

                    # Handle both direct downloads and search results
                    if isinstance(info, dict) and "entries" in info:
                        info = info["entries"][0]

                    return {
                        "id": info["id"],
                        "title": info.get("title", "Unknown"),
                        "url": query if "youtube.com" in query or "youtu.be" in query else f"https://youtu.be/{info['id']}",
                        "path": str(self.DOWNLOADS_DIR / f"{info['id']}.mp3"),
                    }

            # Run in thread pool to avoid blocking
            result = await asyncio.to_thread(_download)

            if result and os.path.exists(result["path"]):
                logger.info(f"Downloaded: {result['title']} -> {result['path']}")
                return result["path"]

            return None

        except Exception as exc:
            logger.error(f"Failed to download track '{query}': {exc}")
            return None

    async def cache_track(self, chat_id: int, file_path: str, title: str, url: str = "") -> None:
        """
        Cache track info for a chat (for quick effect switching without re-downloading).

        Args:
            chat_id: Telegram chat ID
            file_path: Path to the downloaded MP3
            title: Track title
            url: Original YouTube URL (optional)
        """
        self._chat_tracks[chat_id] = {
            "original": file_path,
            "title": title,
            "url": url,
        }
        logger.debug(f"Cached track for chat {chat_id}: {title}")

    async def get_cached_track(self, chat_id: int) -> dict | None:
        """
        Get cached track info for a chat.

        Returns:
            Dict with keys "original", "title", "url" or None if not cached
        """
        return self._chat_tracks.get(chat_id)

    async def clear_cache(self, chat_id: int) -> None:
        """Clear cached track for a chat."""
        self._chat_tracks.pop(chat_id, None)
        logger.debug(f"Cleared track cache for chat {chat_id}")

    async def cleanup_old_downloads(self, max_age_days: int = 7) -> int:
        """
        Remove downloaded files older than max_age_days.

        Args:
            max_age_days: Only remove files older than this (default: 7 days)

        Returns:
            Number of files deleted
        """
        import time

        count = 0
        now = time.time()
        cutoff = now - (max_age_days * 86400)

        try:
            for file_path in self.DOWNLOADS_DIR.glob("*.mp3"):
                if os.path.getmtime(file_path) < cutoff:
                    os.remove(file_path)
                    count += 1
                    logger.debug(f"Cleaned up old download: {file_path}")
        except Exception as exc:
            logger.warning(f"Error during cleanup: {exc}")

        if count > 0:
            logger.info(f"Cleaned up {count} old download(s)")

        return count

    @staticmethod
    def get_download_path(video_id: str) -> str:
        """Get the expected download path for a video ID."""
        return str(TrackManager.DOWNLOADS_DIR / f"{video_id}.mp3")

    @staticmethod
    def track_exists(file_path: str) -> bool:
        """Check if a track file exists locally."""
        return os.path.exists(file_path) and os.path.isfile(file_path)


# Singleton instance for bot-wide use
track_manager = TrackManager()
