# ==============================================================================
# dir.py - Directory Management
# ==============================================================================
# This file ensures that required directories exist for the bot to store:
# - cache: Temporary cache files
# - downloads: Downloaded audio/video files from Telegram or YouTube
# These directories are created automatically on startup if they don't exist.
# ==============================================================================

from pathlib import Path

from OpenHeartsMusic import logger


ROOT = Path(__file__).resolve().parents[1]


def ensure_dirs():
    """
    Create necessary directories if they don't exist.

    Creates:
    - cache/: For temporary cache files
    - downloads/: For downloaded media files
    """
    # List of required directories
    for rel_path in ["cache", "downloads", "cookies"]:
        path = (ROOT / rel_path).resolve()
        path.mkdir(parents=True, exist_ok=True)
    logger.info("📁 Cache directories updated.")
