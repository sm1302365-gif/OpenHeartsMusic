# ==============================================================================
# __main__.py - Entry Point
# ==============================================================================
# Bootstraps the bot: connects to Mongo, starts the client and assistants,
# loads plugins, and idles until killed.
# ==============================================================================

import asyncio
import importlib
import sys
import shutil
import os
from pathlib import Path

from hydrogram import idle

# Raise the file descriptor limit on Linux to avoid "[Errno 24] Too many open files"
# when serving many groups concurrently (each audio stream + ffmpeg probe opens FDs).
if sys.platform != "win32":
    try:
        import resource
        _soft, _hard = resource.getrlimit(resource.RLIMIT_NOFILE)  # type: ignore
        _target = min(65536, _hard)
        if _soft < _target:
            resource.setrlimit(resource.RLIMIT_NOFILE, (_target, _hard))  # type: ignore
    except Exception:
        pass

from OpenHeartsMusic import (
    tune,
    app,
    config,
    db,
    logger,
    stop,
    userbot,
    yt,
)
from OpenHeartsMusic.plugins import all_modules


def load_plugins() -> int:
    """Import plugin modules before the client starts processing updates."""
    loaded = 0
    modules = [
        *(f"OpenHeartsMusic.plugins.{module}" for module in all_modules),
        "OpenHeartsMusic.helpers.nowplaying",
    ]

    for module_name in modules:
        try:
            importlib.import_module(module_name)
            loaded += 1
        except Exception as error:
            logger.error(f"Failed to load plugin {module_name}: {error}", exc_info=True)

    logger.info(f"🔌 Loaded {loaded}/{len(modules)} plugin modules.")
    return loaded


async def main():
    # Verify ffprobe (part of FFmpeg) is available — required for media probing.
    if shutil.which("ffprobe") is None:
        # Try to detect a winget-installed Gyan.FFmpeg package and add its bin
        # folder to PATH so users don't need to restart their shell.
        local_pkg_dir = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
        if local_pkg_dir.exists():
            for child in local_pkg_dir.iterdir():
                if child.name.lower().startswith("gyan.ffmpeg") and child.is_dir():
                    # look for a bin subfolder containing ffprobe
                    for sub in child.rglob("*\ffmpeg*\bin"):
                        ffprobe_path = Path(sub) / "ffprobe.exe"
                        if ffprobe_path.exists():
                            os.environ["PATH"] = str(sub) + os.pathsep + os.environ.get("PATH", "")
                            break
                    if shutil.which("ffprobe"):
                        break

    if shutil.which("ffprobe") is None:
        msg = (
            "❌ ffprobe (part of FFmpeg) is not installed or not on PATH.\n"
            "Install FFmpeg and ensure `ffprobe` is available on your PATH.\n"
            "Linux: `sudo apt install ffmpeg`\n"
            "macOS: `brew install ffmpeg`\n"
            "Windows: install a static build from https://ffmpeg.org/download.html and add to PATH"
        )
        logger.critical(msg)
        raise SystemExit(msg)

    try:
        # Register all handlers before starting the client.
        load_plugins()

        # Connect to DB
        await db.connect()

        # Start the main bot client
        await app.boot()

        # Start assistant/userbot clients
        await userbot.boot()

        # Initialize voice call handler
        await tune.boot()

        # Download YouTube cookies if provided
        if config.COOKIES_URL:
            try:
                await yt.save_cookies(config.COOKIES_URL)
            except Exception as e:
                logger.error(f"Failed to download cookies: {e}")

        # Load sudoers and blacklisted users
        sudoers = await db.get_sudoers()
        app.sudoers.update({int(uid) for uid in sudoers if uid is not None})
        app.refresh_sudo_filter()
        app.bl_users.update(await db.get_blacklisted())
        logger.info(f"👑 Loaded {len(app.sudoers)} sudo users.")
        logger.info("\n🎉 Bot started successfully! Ready to play music! 🎵\n")

        # Keep running until Ctrl+C
        try:
            await idle()
        except KeyboardInterrupt:
            logger.info("Received stop signal...")
        except Exception as e:
            logger.error(f"Error during idle: {e}", exc_info=True)

        # Cleanup
        await stop()
    except Exception as e:
        logger.error(f"Critical error in main: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user (Ctrl+C)")
    except SystemExit as e:
        logger.error(f"Bot exited with system error: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error caused bot to stop: {e}", exc_info=True)
        # Don't raise - allow clean shutdown
    finally:
        # Ensure cleanup happens
        try:
            if loop.is_running():
                loop.stop()
        except:
            pass
