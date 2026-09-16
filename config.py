# ==============================================================================
# config.py - Configuration
# ==============================================================================
# Pulls in all environment variables and sets defaults.
# Don't commit your .env file!
# ==============================================================================

from os import getenv
from pathlib import Path
from typing import List
from dotenv import load_dotenv
COOKIES_PATH = "cookies/cookies.txt"

# Load environment variables from .env file (create one from sample.env)
load_dotenv()


class Config:
    def __init__(self):

        # ============ TELEGRAM API CREDENTIALS ============
        # Get these from https://my.telegram.org
        # Telegram API ID (numeric)
        self.API_ID: int = self._get_int("API_ID", "")
        # Telegram API Hash (hexadecimal)
        self.API_HASH: str = self._get_str("API_HASH", "")

        # ============== DEVELOPER INFORMATION =============
        # Your numeric Telegram user ID
        self.DEVELOPER_ID: int = self._get_int("DEVELOPER_ID", "")
        # Your display name
        self.DEVELOPER_NAME: str = self._get_str("DEVELOPER_NAME", "")
        # Your Telegram username without the @ symbol
        self.DEVELOPER_USERNAME: str = self._get_str("DEVELOPER_USERNAME", "")

        # ========== BOT CONFIGURATION ============
        # Bot token from @BotFather
        self.BOT_TOKEN: str = self._get_str(
            "BOT_TOKEN", "")
        # Group/channel ID or username for logs
        # Logging is optional; do not fall back to an unknown channel ID.
        self.LOG_CHANNEL: int | str = self._get_chat_id("LOGGER_ID", "")
        self.LOGGER_ID: int | str = self.LOG_CHANNEL
        # Your user ID (get from @userinfobot)
        self.OWNER_ID: int = self._get_int("OWNER_ID", "")

        # ============ DATABASE CONFIGURATION ============
        # MongoDB connection URL (mongodb+srv://...)
        self.MONGO_URL: str = self._get_str(
            "MONGO_DB_URI",
            "")

        # Optional Spotify metadata credentials. Apple Music uses its public iTunes API.
        self.SPOTIFY_CLIENT_ID: str = self._get_str("SPOTIFY_CLIENT_ID", "")
        self.SPOTIFY_CLIENT_SECRET: str = self._get_str("SPOTIFY_CLIENT_SECRET", "")

        # ============ MUSIC BOT LIMITS ============
        # Convert minutes to seconds for duration limit
        # Max song duration (default: 300 min)
        self.DURATION_LIMIT: int = self._get_int("DURATION_LIMIT", 300) * 60
        # Max songs in queue (default: 30)
        self.QUEUE_LIMIT: int = self._get_int("QUEUE_LIMIT", 30)
        # Max songs from playlist (default: 20)
        self.PLAYLIST_LIMIT: int = self._get_int("PLAYLIST_LIMIT", 20)




        # ============ ASSISTANT/USERBOT SESSIONS ============
        # Hydrogram session strings - get from @StringFatherBot
        # You can have up to 3 assistants for handling multiple groups
        # Primary assistant (optional; configure STRING_SESSION1 or STRING_SESSION1)

        self.SESSION1 = getenv("STRING_SESSION1", "")
                               
        self.SESSION2 = getenv("STRING_SESSION2", "")

        self.SESSION3 = getenv("STRING_SESSION3", "")



        # ============ AUTOPLAY & WELCOME ============
        # Automatically play a related track when the queue ends
        self.AUTO_PLAY: bool = self._str_to_bool(getenv("AUTO_PLAY", "False"))
        # Enable welcome messages for new group members
        self.WELCOME_ENABLED: bool = self._str_to_bool(getenv("WELCOME_ENABLED", "True"))

        self.SUPPORT_CHANNEL: str = getenv(
            "SUPPORT_CHANNEL", "https://t.me/ShreyanshMusicSupport")
        self.SUPPORT_CHAT: str = getenv("SUPPORT_CHAT", "https://t.me/ShreyanshMusicSupport")

        # ============ WELCOME CONFIGURATION ============
        # Welcome image URL for new group members
        self.WELCOME_IMG: str = self._get_str(
            "WELCOME_IMG",
            getenv("START_IMG", "https://img.sanishtech.com/u/76d9a10831d8195da5f7ebbf998aacc5.jpg")
        )

        # ============ EXCLUDED CHATS ============
        # Parse comma-separated chat IDs that assistants should never leave
        self.EXCLUDED_CHATS: List[int] = self._parse_excluded_chats()

        # ============ FEATURE FLAGS ============
        # Auto-end stream when queue is empty
        self.AUTO_END: bool = self._str_to_bool(getenv("AUTO_END", "False"))
        # Auto-leave inactive chats
        self.AUTO_LEAVE: bool = self._str_to_bool(getenv("AUTO_LEAVE", "False"))
        # Enable/disable thumbnail generation (set False to use default thumb)
        self.THUMB_GEN: bool = self._str_to_bool(getenv("THUMB_GEN", "True"))
        # Enable/disable video playback commands (/vplay)
        self.VIDEO_PLAY: bool = self._str_to_bool(getenv("VIDEO_PLAY", "True"))
        # Optional inline button accent color. Supported values: red, green, blue,
        # yellow, orange, purple, pink, cyan, black, white. Leave empty to disable.
        self.BUTTON_BG_COLOR: str | None = self._get_button_bg_color()
        # Maximum video height (in pixels) when downloading /vplay media
        self.VIDEO_MAX_HEIGHT: int = self._parse_video_height()

        # ============ YOUTUBE COOKIES ============
        # Parse space-separated cookie URLs for age-restricted content
        self.COOKIES_URL: List[str] = self._parse_cookies()

        # ============ IMAGE URLS ============
        # URLs for various bot images
        self.DEFAULT_THUMB: str = getenv(
            "DEFAULT_THUMB",
            "https://files.catbox.moe/kgrs8f.png"  # Default thumbnail
        )
        self.PING_IMG: str = getenv(
            "PING_IMG", "https://files.catbox.moe/djilyq.png")    # Ping command image
        self.START_IMG: str = getenv(
            "START_IMG", "https://img.sanishtech.com/u/d690a144239c86c30184a7c83587d8ca.jpg")  # Start command image


        # ============ MODERATION ============
        # List of usernames to exclude from admin mentions
        self.EXCLUDED_USERNAMES: List[str] = getenv("EXCLUDED_USERNAMES", "").split()

    def _get_int(self, name: str, default: int) -> int:
        value = getenv(name)
        if value is None or value == "":
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _get_chat_id(self, name: str, default: str | int) -> str | int:
        value = getenv(name)
        if value is None or value == "":
            value = str(default)
        if isinstance(value, str) and value.lstrip("+-").isdigit():
            try:
                return int(value)
            except ValueError:
                return value
        return value

    def _get_str(self, name: str, default: str) -> str:
        value = getenv(name)
        if value is None or value == "":
            return default
        return value

    def _get_button_bg_color(self) -> str | None:
        value = getenv("BUTTON_BG_COLOR", "green")
        if value is None or value == "":
            return None
        normalized = value.strip().lower()
        supported = {"red", "green", "blue", "yellow", "orange", "purple", "pink", "cyan", "black", "white"}
        return normalized if normalized in supported else None

    def _parse_video_height(self) -> int:
        """Clamp configured video height to a safe HD range."""
        default_height = 1080
        raw_value = getenv("VIDEO_MAX_HEIGHT", str(default_height))
        if raw_value is None or raw_value == "":
            return default_height
        try:
            height = int(raw_value)
        except (TypeError, ValueError):
            return default_height

        # Allow disabling the cap by setting to 0 or negative (interpreted as unlimited)
        if height <= 0:
            return 0

        # Clamp between 480p and 2160p to avoid unrealistic requests
        return max(480, min(height, 2160))

    def _parse_excluded_chats(self) -> List[int]:
        excluded = getenv("EXCLUDED_CHATS", "")
        if not excluded:
            return []

        chat_ids = []
        for chat_id in excluded.split(","):
            chat_id = chat_id.strip()
            if chat_id.lstrip('-').isdigit():
                chat_ids.append(int(chat_id))
        return chat_ids

    def _parse_cookies(self) -> List[str]:
        cookie_str = getenv("COOKIE_URL", "")
        if not cookie_str:
            return []

        valid_sources = ["batbin.me", "pastebin.com", "paste.ee", "rentry.co"]
        return [
            url.strip()
            for url in cookie_str.split()
            if url.strip() and any(source in url for source in valid_sources)
        ]

    @staticmethod
    def _str_to_bool(value: str | None) -> bool:
        if value is None:
            return False
        return value.strip().lower() in ("true", "1", "yes", "y", "on")

    def check(self) -> None:
        required_vars = {
            "API_ID": self.API_ID,
            "API_HASH": self.API_HASH,
            "BOT_TOKEN": self.BOT_TOKEN,
            "MONGO_URL": self.MONGO_URL,
            "OWNER_ID": self.OWNER_ID,
        }

        missing = [
            name for name, value in required_vars.items()
            if not value or (isinstance(value, int) and value == 0)
        ]

        if missing:
            # Allow startup to continue with bundled defaults if the user has not
            # provided real credentials yet. Real bot functionality will still fail
            # later until the values are replaced with valid ones.
            if "BOT_TOKEN" in missing and self.BOT_TOKEN == "":
                return
            raise SystemExit(
                f"❌ Missing required environment variables: {', '.join(missing)}\n"
                f"Please check your .env file and ensure all required variables are set."
            )


class CustomFonts:
    """Custom title styles for the bot UI.

    Use stylized script fonts when supported, but always keep plain-text
    fallbacks for Telegram clients that render them poorly.
    """

    START_STUDIO = "𝓢𝓽𝓾𝓭𝓲𝓸"
    HELP_NORMAL = "𝓗𝓮𝓵𝓹"
    HELP_BTN = "𝓗𝓮𝓵𝓹"
    PLAYING_TITLE = "𝑵𝒐𝒘 𝑷𝒍𝒂𝒚𝒊𝒏𝒈"
    PLAYING_STUDIO = " 𝑺𝒕𝒖𝒅𝒊𝒐"
    SAFE_LABELS = {
        "START_STUDIO": "Studio",
        "HELP_NORMAL": "Help",
        "HELP_BTN": "Help",
        "PLAYING_TITLE": "Now Playing",
        "PLAYING_STUDIO": "Studio",
    }

    @classmethod
    def safe(cls, name: str, fallback: str | None = None) -> str:
        if fallback is not None:
            return fallback
        return cls.SAFE_LABELS.get(name, name.replace("_", " ").title())


config = Config()

# ==============================================================================
# Button Styles & UI Color Configurations for config.py
# ==============================================================================

class ButtonStyles:
    """Button styles and color definitions for inline interactive buttons."""
    SUCCESS = "success"        # For active or ON state (Green)
    DANGER = "danger"          # For inactive or OFF state (Red)
    PRIMARY = "primary"        # For primary or main actions (Blue)
    SECONDARY = "secondary"    # For general or secondary actions (Grey)

# Alternative theme colors (If hex codes are needed for your frontend or mini app)
class ButtonColors:
    SUCCESS_HEX = "#28a745"
    DANGER_HEX = "#dc3545"
    PRIMARY_HEX = "#007bff"
    SECONDARY_HEX = "#6c757d"
