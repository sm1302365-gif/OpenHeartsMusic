# ==============================================================================
# ˹OpenHeartsMusic˼ Core Initialization
# ==============================================================================
# Sets up logging, config, and instantiates the main singleton objects (db, bot, etc.)
# ==============================================================================

import asyncio
import logging
import os
import site
import sys
import sysconfig
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import List

try:
    asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

ROOT = Path(__file__).resolve().parent


def _find_project_venv() -> Path | None:
    candidates = [
        ROOT / ".venv",
        ROOT.parent / ".venv",
        ROOT.parent.parent / ".venv",
        ROOT.parent.parent.parent / ".venv",
    ]
    for candidate in candidates:
        try:
            if candidate.exists():
                return candidate.resolve()
        except Exception:
            continue
    return None


def _is_running_from_project_venv(venv_dir: Path | None) -> bool:
    if not venv_dir:
        return False

    exe = str(Path(sys.executable).resolve()).lower()
    prefix = str(Path(sys.prefix).resolve()).lower()
    venv_path = str(venv_dir).lower()
    return venv_path in exe or venv_path in prefix


def _get_venv_python(venv_dir: Path | None) -> Path | None:
    if not venv_dir:
        return None

    if os.name == "nt":
        candidates = [
            venv_dir / "Scripts" / "python.exe",
            venv_dir / "Scripts" / "python",
        ]
    else:
        candidates = [
            venv_dir / "bin" / "python3",
            venv_dir / "bin" / "python",
        ]

    for candidate in candidates:
        try:
            if candidate.exists():
                return candidate.resolve()
        except Exception:
            continue
    return None


# Ensure the project's virtual environment is used when available. If the current
# interpreter is not the project venv, prepend the venv site-packages to the
# import path so startup uses the intended environment automatically.
try:
    venv_dir = _find_project_venv()
    if venv_dir and not _is_running_from_project_venv(venv_dir):
        venv_python = _get_venv_python(venv_dir)
        if venv_python is not None:
            venv_site = venv_dir / "Lib" / "site-packages"
            if os.name == "nt":
                venv_site = venv_dir / "Lib" / "site-packages"
            else:
                venv_site = venv_dir / "lib"
                python_version = f"python{sys.version_info.major}.{sys.version_info.minor}"
                venv_site = venv_site / python_version / "site-packages"

            if venv_site.exists():
                site.addsitedir(str(venv_site))
                sys.path.insert(0, str(venv_site))
except Exception:
    # If any error occurs while checking the venv, continue — don't block
    # startup (best-effort only).
    pass


def _get_channel_invalid():
    try:
        from hydrogram.errors import ChannelInvalid
        return ChannelInvalid
    except Exception:
        return None


_ChannelInvalid = None


class Utf8StreamHandler(logging.StreamHandler):
    def __init__(self):
        super().__init__()
        self.stream = None

    def emit(self, record):
        try:
            msg = self.format(record)
            stream = os.fdopen(
                sys.__stdout__.fileno(),
                "w",
                encoding="utf-8",
                errors="replace",
                closefd=False,
            )
            stream.write(msg + self.terminator)
            stream.flush()
        except Exception:
            self.handleError(record)


stream_handler = Utf8StreamHandler()

root_logger = logging.getLogger()
root_logger.handlers.clear()
root_logger.setLevel(logging.INFO)
root_logger.propagate = False

root_logger.addHandler(RotatingFileHandler(str(ROOT / "log.txt"), maxBytes=10485760, backupCount=5))
root_logger.addHandler(stream_handler)

# Reduce noise from third-party libraries
logging.getLogger("httpx").setLevel(logging.ERROR)
logging.getLogger("ntgcalls").setLevel(logging.CRITICAL)
logging.getLogger("pymongo").setLevel(logging.ERROR)
logging.getLogger("hydrogram").setLevel(logging.ERROR)
logging.getLogger("pytgcalls").setLevel(logging.ERROR)

logger = logging.getLogger("OpenHeartsMusic")
logger.setLevel(logging.INFO)
logger.propagate = False
logger.addHandler(stream_handler)


def _asyncio_exception_handler(loop: asyncio.AbstractEventLoop, context: dict) -> None:
    exc = context.get("exception")
    if exc is not None:
        global _ChannelInvalid
        if _ChannelInvalid is None:
            _ChannelInvalid = _get_channel_invalid()
        if _ChannelInvalid is not None and isinstance(exc, _ChannelInvalid):
            logger.warning("Ignoring CHANNEL_INVALID update (channel probably removed).")
            return
    loop.default_exception_handler(context)


asyncio.get_event_loop().set_exception_handler(_asyncio_exception_handler)

# PyTgCalls can receive legacy lowercase-c error identifiers from Telegram.
# Hydrogram also sometimes receives ChannelForbidden payloads without a `verified`
# field when a channel is inaccessible; guard the parser to avoid crashes.
from .compat import install_hydrogram_channel_compat_patch, install_hydrogram_error_aliases
install_hydrogram_error_aliases()
install_hydrogram_channel_compat_patch()

# Version
__version__ = "3.0.1"

# Load configuration
# `config.py` lives at the project root, import it as a top-level module so
# `python -m OpenHeartsMusic` can find it when run from the project folder.
from config import Config

config = Config()
config.check()

# Global task list for background tasks
tasks: List = []
boot: float = time.time()

# Initialize bot client
from .core.bot import Bot
app = Bot()

# Ensure required directories exist
from .core.dir import ensure_dirs
ensure_dirs()

# Initialize userbot/assistant clients
from .core.userbot import Userbot
userbot = Userbot()

# Initialize database connection
from .core.mongo import MongoDB
db = MongoDB()

# Initialize language system
from .core.lang import Language
lang = Language()

# Initialize Telegram and YouTube utilities
from .core.telegram import Telegram
from .core.youtube import YouTube
tg = Telegram()
yt = YouTube()

# Initialize preload manager for background track downloading
from .core.preload import PreloadManager
preload = PreloadManager()

# Initialize queue manager
from .helpers import Queue
queue = Queue()

# Initialize call handler
from .core.calls import TgCall
tune = TgCall()


async def stop() -> None:
    logger.info("🛑 Stopping bot...")

    # Cancel all background tasks
    for task in tasks:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            # Expected when cancelling tasks - suppress the error
            pass
        except Exception:
            pass

    # Close all connections
    try:
        from importlib import import_module
        stop_lyrics_tasks = import_module(
            "OpenHeartsMusic.plugins.utilities.lyrics"
        ).stop_lyrics_tasks
        await stop_lyrics_tasks()
    except ImportError:
        pass
    await app.exit()
    await userbot.exit()
    await db.close()

    logger.info("✅ Bot stopped successfully.\n")
