import os
import asyncio
import logging
from hydrogram import Client
from pytgcalls import PyTgCalls, types
from pytgcalls.exceptions import NoActiveGroupCall, NotInCallError

logger = logging.getLogger(__name__)

# ADVANCED FIX: '-vn' parameter strictly ignores album arts/covers to prevent FFmpeg crashes.
# This ensures sound works perfectly for BOTH normal songs and karaoke streams.
DEFAULT_FFMPEG_PARAMETERS = "-vn"

class CallManager:
    """Robust PyTgCalls helper for managing voice chat connections and streaming."""

    def __init__(self, app: Client, cache_duration: int = 100):
        self.pytgcalls = PyTgCalls(app, cache_duration=cache_duration)

    async def start(self) -> None:
        """Start the PyTgCalls client."""
        try:
            await self.pytgcalls.start()
            logger.info("PyTgCalls client started successfully.")
        except Exception as e:
            logger.error(f"Failed to start PyTgCalls client: {e}")
            raise

    async def _build_stream(self, file_path: str, audio_filter: str | None = None) -> types.MediaStream:
        """Build a clean MediaStream with optional FFmpeg filters.

        CRITICAL: Uses IGNORE for video_flags to prevent silent audio in video group calls.
        """
        if not file_path:
            raise ValueError("File path cannot be empty for streaming.")

        # ADVANCED SAFETY FIX: Check if the audio file actually exists before streaming
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Audio file not found on server: {file_path}")

        ffmpeg_parameters = DEFAULT_FFMPEG_PARAMETERS
        if audio_filter:
            ffmpeg_parameters = f"{ffmpeg_parameters} -af {audio_filter}"

        return types.MediaStream(
            media_path=file_path,
            audio_path=file_path,  # Explicitly set audio path to prevent audio drop
            audio_parameters=types.AudioQuality.STUDIO,
            audio_flags=types.MediaStream.Flags.REQUIRED,
            video_flags=types.MediaStream.Flags.IGNORE,  # Always IGNORE video to preserve audio
            ffmpeg_parameters=ffmpeg_parameters,
        )

    async def join_call(self, chat_id: int, file_path: str, audio_filter: str | None = None) -> None:
        """Join a voice call and stream audio safely with built-in fallback."""
        try:
            stream = await self._build_stream(file_path, audio_filter)
        except Exception as e:
            logger.error(f"Stream building error for chat {chat_id}: {e}")
            raise RuntimeError(f"Could not prepare audio stream: {e}")

        try:
            # Play or seamlessly update the stream
            await self.pytgcalls.play(chat_id=chat_id, stream=stream)
            logger.info(f"Successfully streaming to chat {chat_id}")

        except NoActiveGroupCall:
            logger.warning(f"No active group call found in chat {chat_id}")
            raise RuntimeError("No active group call found! Please start a voice chat first.")

        except NotInCallError:
            logger.warning(f"Assistant is not in call for chat {chat_id}, attempting fresh join...")
            # Fallback: Force a clean state reset if call session desyncs
            try:
                await self.pytgcalls.leave_call(chat_id)
                await asyncio.sleep(0.5)
            except Exception:
                pass
            # Re-attempt streaming
            await self.pytgcalls.play(chat_id=chat_id, stream=stream)

        except Exception as e:
            logger.error(f"Unexpected streaming error in chat {chat_id}: {e}")
            raise RuntimeError(f"Failed to stream media: {e}")

    async def leave_call(self, chat_id: int) -> None:
        """Safely leave the voice chat."""
        try:
            await self.pytgcalls.leave_call(chat_id)
            logger.info(f"Left voice chat for chat {chat_id}")
        except Exception as e:
            logger.debug(f"Error leaving call for chat {chat_id}: {e}")

    async def pause_stream(self, chat_id: int) -> None:
        """Pause current stream playback."""
        try:
            await self.pytgcalls.pause(chat_id)
            logger.info(f"Stream paused for chat {chat_id}")
        except Exception as e:
            logger.debug(f"Error pausing stream for chat {chat_id}: {e}")

    async def resume_stream(self, chat_id: int) -> None:
        """Resume paused stream playback."""
        try:
            await self.pytgcalls.resume(chat_id)
            logger.info(f"Stream resumed for chat {chat_id}")
        except Exception as e:
            logger.debug(f"Error resuming stream for chat {chat_id}: {e}")
