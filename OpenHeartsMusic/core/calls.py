# ==============================================================================
# calls.py - Voice Call Handler (PyTgCalls Integration)
# ==============================================================================
# This file manages voice/video chat functionality using PyTgCalls.
# Features:
# - Stream audio/video to Telegram voice chats
# - Playback controls (play, pause, resume, stop, seek)
# - Queue management (play next track automatically)
# - Multi-assistant support (load balancing)
# - Live stream support
# - Thumbnail updates during playback
# ==============================================================================

import asyncio
import html
import logging
from pathlib import Path
from ntgcalls import ConnectionNotFound, TelegramServerError
from hydrogram import Client, enums, errors, raw
from hydrogram.errors import MessageIdInvalid
from hydrogram.types import InputMediaPhoto, Message
from pytgcalls import PyTgCalls, exceptions, types
from pytgcalls.pytgcalls_session import PyTgCallsSession

from OpenHeartsMusic import app, config, db, lang, logger, preload, queue, userbot, yt
from OpenHeartsMusic.helpers import (
    Media,
    Track,
    build_now_playing_buttons,
    build_now_playing_caption,
    buttons,
    thumb,
)
from OpenHeartsMusic.helpers._assistant_invite import (
    _unwrap_assistant_client,
    ensure_assistant_in_chat,
)
from OpenHeartsMusic.helpers._message_cleanup import (
    AUTO_DELETE_CACHE,
    auto_clean_track_messages,
    register_msg_to_delete,
)

# Audio normalization and karaoke filter presets used by playback and tests
# Ensures safe vocal cut filter and stable ffmpeg reconnect/format params
SAFE_KARAOKE_FILTER = "aformat=channel_layouts=stereo,pan=stereo|c0=0.5*c0-0.5*c1|c1=0.5*c1-0.5*c0,volume=0.5"

# Use the highest available stereo profile for clearer group-call audio.
GROUP_CALL_AUDIO_QUALITY = types.AudioQuality.STUDIO

# Keep video/audio FFmpeg processes alive across mute/unmute renegotiation.
VIDEO_STREAM_FFMPEG_PARAMETERS = "-loglevel panic -re -fflags +genpts -async 1 -vsync 0"


def _handle_task_exception(task: asyncio.Task) -> None:
    if task.cancelled():
        return
    exc = task.exception()
    if exc is None or isinstance(exc, asyncio.CancelledError):
        return
    logger.debug(f"Background task failed: {exc}")


class CallManager:
    """A lightweight PyTgCalls v3 wrapper for join/pause/resume playback."""

    DEFAULT_FFMPEG_PARAMETERS = "-reconnect 1 -reconnect_streamed 1 -ar 48000 -ac 2"

    def __init__(self, app: Client, cache_duration: int = 100):
        self.pytgcalls = PyTgCalls(app, cache_duration=cache_duration)

    async def start(self) -> None:
        await self.pytgcalls.start()

    async def _build_stream(self, file_path: str, audio_filter: str | None = None) -> types.MediaStream:
        ffmpeg_parameters = self.DEFAULT_FFMPEG_PARAMETERS
        if audio_filter:
            ffmpeg_parameters = f"{ffmpeg_parameters} -af {audio_filter}"

        return types.MediaStream(
            media_path=file_path,
            audio_parameters=GROUP_CALL_AUDIO_QUALITY,
            audio_flags=types.MediaStream.Flags.REQUIRED,
            video_flags=types.MediaStream.Flags.IGNORE,
            ffmpeg_parameters=ffmpeg_parameters,
        )

    async def join_call(
        self,
        chat_id: int,
        file_path: str,
        audio_filter: str | None = None,
    ) -> None:
        stream = await self._build_stream(file_path, audio_filter)

        try:
            await self.pytgcalls.play(chat_id=chat_id, stream=stream)
        except exceptions.NoActiveGroupCall:
            raise Exception("No active group call found in this chat!")

    async def leave_call(self, chat_id: int) -> None:
        try:
            await self.pytgcalls.leave_call(chat_id)
        except Exception:
            pass

    async def pause_stream(self, chat_id: int) -> None:
        await self.pytgcalls.pause(chat_id)

    async def resume_stream(self, chat_id: int) -> None:
        await self.pytgcalls.resume(chat_id)


# Karaoke presets: Presets MUST start with the SAFE_KARAOKE_FILTER so tests
# and audio pipelines can rely on a safe vocal removal baseline.
# CRITICAL: Use commas (,) to chain FFmpeg audio filters properly, NOT pipes (|).
KARAOKE_PRESETS = {
    "standard": SAFE_KARAOKE_FILTER,
    "reverb": SAFE_KARAOKE_FILTER + ",aecho=0.8:0.9:1000:0.3,volume=100",
    "high_pitch": SAFE_KARAOKE_FILTER + ",asetrate=44100*1.1,atempo=1.05,volume=100",
    "deep_bass": SAFE_KARAOKE_FILTER + ",bass=g=8,volume=100",
    "studio": "bass=g=12,treble=g=8,aecho=0.8:0.9:500:0.5,volume=100",
    "off": "",
}
# Memory set to track chats where Studio Karaoke is active.
STUDIO_CHATS = set()

async def get_studio_audio_stream(file_path: str, chat_id: int, ffmpeg_parameters: str, video_flags=types.MediaStream.Flags.IGNORE):
    """
    Applies high-level audio filters for a professional studio sound when Karaoke Studio is enabled.

    Args:
        file_path: Path to the media file
        chat_id: Chat ID to check if studio mode is active
        ffmpeg_parameters: Base ffmpeg parameters
        video_flags: Video handling flags for audio-only or video playback.
    """
    audio_filter = ""

    if chat_id in STUDIO_CHATS:
        audio_filter = "bass=g=12,treble=g=8,aecho=0.8:0.9:500:0.5"

    ffmpeg_command = ffmpeg_parameters
    if audio_filter:
        ffmpeg_command = f"{ffmpeg_parameters} -af {audio_filter}"

    return types.MediaStream(
        media_path=file_path,
        audio_path=file_path,  # Explicitly set audio path to prevent audio drop
        audio_parameters=GROUP_CALL_AUDIO_QUALITY,
        audio_flags=(
            types.MediaStream.Flags.AUTO_DETECT
            if video_flags == types.MediaStream.Flags.REQUIRED
            else types.MediaStream.Flags.REQUIRED
        ),
        video_flags=video_flags,
        ffmpeg_parameters=ffmpeg_command,
    )

# Suppress pytgcalls harmless errors (library bugs - not critical)


class PyTgCallsErrorFilter(logging.Filter):
    def filter(self, record):
        # Filter out UpdateGroupCall errors
        if 'UpdateGroupCall' in record.getMessage():
            return False
        # Filter out ConnectionNotFound errors (happens when call ends but updates still arrive)
        if 'Connection with chat id' in record.getMessage() and 'not found' in record.getMessage():
            return False
        return True


logging.getLogger('hydrogram.dispatcher').addFilter(PyTgCallsErrorFilter())


class TgCall(PyTgCalls):
    def __init__(self):
        self.clients = []
        self._chat_locks = {}  # Unified lock to prevent concurrent playback mutations per chat
        self._stream_end_cache = {}  # Cache to prevent duplicate stream end processing
        self._stream_replacements = set()  # Chats currently replacing an active source
        self._playback_intros = set()  # Track intros already sent per chat/track
        self._karaoke_modes = {}  # Per-chat karaoke mode cache
        self._audio_fx = {}  # Per-chat audio effect cache (bassboost, 8d, nightcore, lofi, none)
        self._assistant_mute_state = {}
        self._video_resync_tasks = {}
        self._autoplay_prefetch_tasks = {}
        self._autoplay_prefetched = {}
        self._autoplay_prefetch_sources = {}

    def get_lock(self, chat_id: int) -> asyncio.Lock:
        if chat_id not in self._chat_locks:
            self._chat_locks[chat_id] = asyncio.Lock()
        return self._chat_locks[chat_id]

    async def _prefetch_autoplay(self, chat_id: int, current_track) -> Track | None:
        try:
            related = await yt.related(
                video_id=current_track.id,
                m_id=0,
                parent_title=getattr(current_track, "title", None),
                video=getattr(current_track, "video", False),
                chat_id=chat_id,
            )
            if not related:
                related = await yt.random_autoplay_track(
                    chat_id,
                    m_id=0,
                    exclude_id=current_track.id,
                )
            if not related or related.id == current_track.id:
                return None

            if not related.file_path:
                related.file_path = await yt.download(
                    related.id,
                    is_live=getattr(related, "is_live", False),
                    video=getattr(related, "video", False),
                )
            return related if related.file_path else None
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.debug(f"Autoplay prefetch failed for {chat_id}: {error}")
            return None

    def _schedule_autoplay_prefetch(self, chat_id: int, current_track) -> None:
        if not current_track or queue.peek_next(chat_id, 1):
            return
        existing = self._autoplay_prefetch_tasks.get(chat_id)
        if existing and not existing.done():
            return

        task = asyncio.create_task(self._prefetch_autoplay(chat_id, current_track))
        self._autoplay_prefetch_tasks[chat_id] = task
        self._autoplay_prefetch_sources[chat_id] = current_track.id

        def _store_result(done_task: asyncio.Task) -> None:
            if done_task.cancelled():
                return
            try:
                result = done_task.result()
            except Exception:
                return
            if result:
                self._autoplay_prefetched[chat_id] = result

        task.add_done_callback(_store_result)

    async def _take_autoplay_prefetch(
        self, chat_id: int, current_track_id: str | None = None
    ) -> Track | None:
        source_id = self._autoplay_prefetch_sources.pop(chat_id, None)
        task = self._autoplay_prefetch_tasks.pop(chat_id, None)
        if source_id != current_track_id:
            self._autoplay_prefetched.pop(chat_id, None)
            if task and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            return None
        if task and not task.done():
            await task
        return self._autoplay_prefetched.pop(chat_id, None)

    async def _cancel_autoplay_prefetch(self, chat_id: int) -> None:
        task = self._autoplay_prefetch_tasks.pop(chat_id, None)
        self._autoplay_prefetched.pop(chat_id, None)
        self._autoplay_prefetch_sources.pop(chat_id, None)
        if task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def _clear_stream_replacement(self, chat_id: int) -> None:
        await asyncio.sleep(5)
        self._stream_replacements.discard(chat_id)

    async def _send_animated_intro_message(self, chat_id: int, text: str) -> None:
        """Send one message and reveal its text in small, smooth steps."""
        await app.send_chat_action(chat_id, enums.ChatAction.TYPING)
        step_size = max(1, (len(text) + 2) // 3)
        message = await app.send_message(
            chat_id=chat_id,
            text=text[:step_size],
            parse_mode=enums.ParseMode.HTML,
        )
        register_msg_to_delete(chat_id, message.id)
        for end in range(step_size * 2, len(text), step_size):
            await asyncio.sleep(0.2)
            await message.edit_text(text[:end], parse_mode=enums.ParseMode.HTML)
        if len(text) > step_size:
            await asyncio.sleep(0.2)
            await message.edit_text(text, parse_mode=enums.ParseMode.HTML)

    async def _send_playback_intro(self, chat_id: int, media, lang_data: dict) -> None:
        """Send the animated heart and text intro once for a track."""
        track_key = (chat_id, str(getattr(media, "id", None) or media.file_path))
        if track_key in self._playback_intros:
            return
        self._playback_intros.add(track_key)

        intro_values = {
            "song_title": html.escape(str(getattr(media, "title", None) or "Unknown Track")),
            "song_dur": html.escape(str(getattr(media, "duration", None) or "00:00")),
            "requester_name": html.escape(str(getattr(media, "user", None) or "User")),
        }

        raw_messages = (
            lang_data.get("play_text1", "I Love Music"),
            lang_data.get("play_text2", "Music Not a Language"),
            lang_data.get("play_text3", "Music is a Universal Language"),
        )
        messages = []
        for text in raw_messages:
            text = str(text).strip()
            if not text:
                continue
            try:
                text = text.format(**intro_values)
            except (KeyError, ValueError):
                pass
            messages.append(text)

        for index, text in enumerate(messages):
            started_at = asyncio.get_running_loop().time()
            try:
                if index == 0:
                    await app.send_chat_action(chat_id, enums.ChatAction.TYPING)
                    await asyncio.sleep(0.35)
                    intro_message = await app.send_message(
                        chat_id=chat_id,
                        text=text,
                        parse_mode=enums.ParseMode.HTML,
                    )
                    register_msg_to_delete(chat_id, intro_message.id)
                else:
                    await self._send_animated_intro_message(chat_id, text)
            except Exception as e:
                logger.debug(f"Could not send playback intro message in {chat_id}: {e}")
            if index < len(messages) - 1:
                elapsed = asyncio.get_running_loop().time() - started_at
                await asyncio.sleep(max(0, 1 - elapsed))

    def get_karaoke_mode(self, chat_id: int) -> str:
        """Return the current karaoke mode for a chat. Defaults to 'off'."""
        return self._karaoke_modes.get(chat_id, "off")

    async def set_karaoke_mode(self, chat_id: int, mode: str) -> bool:
        """Set karaoke mode for a chat and apply it to the active stream."""
        key = str(mode or "off").strip().lower()
        if key not in KARAOKE_PRESETS:
            return False

        try:
            active = await db.get_call(chat_id)
        except Exception:
            active = False

        self._karaoke_modes[chat_id] = key
        if key == "studio":
            STUDIO_CHATS.add(chat_id)
        else:
            STUDIO_CHATS.discard(chat_id)

        if not active:
            return True

        try:
            return await self.restart_stream(chat_id)
        except Exception as e:
            logger.error(f"Failed to apply karaoke mode {key} to {chat_id}: {e}", exc_info=True)
            return False

    def get_audio_fx(self, chat_id: int) -> str:
        """Return the current audio effect for a chat. Defaults to 'none'."""
        return self._audio_fx.get(chat_id, "none")

    async def set_audio_fx(self, chat_id: int, fx_type: str) -> bool:
        """Apply an audio effect and restart playback with the new effect.

        Args:
            chat_id: The chat to apply the effect in
            fx_type: Effect type (bassboost, 8d, nightcore, lofi, none)

        Returns:
            True if effect was applied, False if call not active or error occurred
        """
        from OpenHeartsMusic.helpers import AudioEffectManager

        if not await db.get_call(chat_id):
            return False

        media = queue.get_current(chat_id)
        if not media:
            return False

        # Validate effect type
        if not AudioEffectManager.is_valid_effect(fx_type):
            return False

        # Store the current effect
        self._audio_fx[chat_id] = fx_type

        # Restart stream with new effect applied
        try:
            await self.restart_stream(chat_id)
            return True
        except Exception as e:
            logger.error(f"Failed to apply audio effect {fx_type} to {chat_id}: {e}")
            return False

    async def _edit_media_with_retry(self, message: Message, media_obj: InputMediaPhoto, reply_markup):
        """Edit media with basic FloodWait handling."""
        try:
            return await message.edit_media(media=media_obj, reply_markup=reply_markup)
        except errors.FloodWait as fw:
            await asyncio.sleep(fw.value + 1)
            try:
                return await message.edit_media(media=media_obj, reply_markup=reply_markup)
            except Exception:
                return None
        except errors.MessageNotModified:
            return None
        except Exception:
            return None

    async def _send_photo_with_retry(self, chat_id: int, photo, caption: str, reply_markup):
        """Send photo with FloodWait handling and a plain-text fallback."""
        try:
            sent = await app.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=caption,
                reply_markup=reply_markup,
                parse_mode=enums.ParseMode.HTML,
            )
            register_msg_to_delete(chat_id, sent.id)
            return sent
        except errors.FloodWait as fw:
            await asyncio.sleep(fw.value + 1)
            try:
                sent = await app.send_photo(
                    chat_id=chat_id,
                    photo=photo,
                    caption=caption,
                    reply_markup=reply_markup,
                    parse_mode=enums.ParseMode.HTML,
                )
                register_msg_to_delete(chat_id, sent.id)
                return sent
            except Exception:
                pass
        except Exception:
            pass

        try:
            sent = await app.send_message(
                chat_id=chat_id,
                text=caption,
                reply_markup=reply_markup,
                parse_mode=enums.ParseMode.HTML,
            )
            register_msg_to_delete(chat_id, sent.id)
            return sent
        except Exception:
            try:
                sent = await app.send_message(
                    chat_id=chat_id,
                    text=caption,
                    reply_markup=reply_markup,
                    parse_mode=enums.ParseMode.HTML,
                )
                register_msg_to_delete(chat_id, sent.id)
                return sent
            except Exception:
                return None

    async def pause(self, chat_id: int) -> bool:
        client = await db.get_assistant(chat_id)
        try:
            await client.pause(chat_id)
            await db.playing(chat_id, paused=True)
            return True
        except (ConnectionNotFound, exceptions.NotInCallError):
            await db.playing(chat_id, paused=False)
            await db.remove_call(chat_id)
            queue.clear(chat_id)
            logger.warning(
                f"Pause requested but assistant not in call for {chat_id}, syncing state")
            return False
        except Exception as e:
            await db.playing(chat_id, paused=False)
            logger.error(f"Pause failed for {chat_id}: {e}")
            return False

    async def resume(self, chat_id: int) -> bool:
        client = await db.get_assistant(chat_id)
        try:
            await client.resume(chat_id)
            await db.playing(chat_id, paused=False)
            return True
        except (ConnectionNotFound, exceptions.NotInCallError):
            await db.playing(chat_id, paused=False)
            await db.remove_call(chat_id)
            queue.clear(chat_id)
            logger.warning(
                f"Resume requested but assistant not in call for {chat_id}, syncing state")
            return False
        except Exception as e:
            logger.error(f"Resume failed for {chat_id}: {e}")
            return False

    async def stop(self, chat_id: int) -> None:
        async with self.get_lock(chat_id):
            await self._stop_impl(chat_id)

    async def _stop_impl(self, chat_id: int) -> None:
        client = await db.get_assistant(chat_id)

        await self._cancel_autoplay_prefetch(chat_id)

        await auto_clean_track_messages(app, chat_id)

        # Cancel any active preload tasks when stopping
        try:
            await preload.cancel_preload(chat_id)
        except Exception as e:
            logger.debug(f"Error cancelling preload for {chat_id}: {e}")

        try:
            queue.clear(chat_id)
            await db.remove_call(chat_id)
            self._assistant_mute_state = {
                key: state for key, state in self._assistant_mute_state.items()
                if key[0] != chat_id
            }
            video_resync = self._video_resync_tasks.pop(chat_id, None)
            if video_resync and not video_resync.done():
                video_resync.cancel()
            self._playback_intros = {
                key for key in self._playback_intros if key[0] != chat_id
            }
            # Clear karaoke mode when a call stops to avoid stale state
            try:
                self._karaoke_modes.pop(chat_id, None)
            except Exception:
                pass
        except Exception as e:
            logger.warning(f"Error clearing queue/call for {chat_id}: {e}")

        try:
            await client.leave_call(chat_id, close=False)
            # Small delay to let group call state stabilize after leaving
            await asyncio.sleep(0.5)
        except (ConnectionNotFound, exceptions.NotInCallError):
            # Expected: userbot is not in a call
            pass
        except Exception as e:
            # Only log unexpected errors
            error_msg = str(e).lower()
            if not any(ignore in error_msg for ignore in [
                "not in a call",
                "not in the group call",
                "groupcall_forbidden",
                "no active group call",
                "call was already stopped",
                "call already disconnected"
            ]):
                logger.warning(f"Error leaving call for {chat_id}: {e}")

    async def play_media(
        self,
        chat_id: int,
        message: Message | None,
        media: Media | Track,
        seek_time: int = 0,
    ) -> None:
        async with self.get_lock(chat_id):
            await self._play_media_impl(
                chat_id, message, media, seek_time
            )

    async def restart_stream(self, chat_id: int) -> bool:
        """Restart the current stream for the given chat without dropping video."""
        async with self.get_lock(chat_id):
            if not await db.get_call(chat_id):
                return False

            media = queue.get_current(chat_id)
            if not media:
                return False

            client = await db.get_assistant(chat_id)
            try:
                self._stream_replacements.add(chat_id)
                await self._play_media_impl(chat_id, None, media, preserve_call=True)
                asyncio.create_task(self._clear_stream_replacement(chat_id))
                return True
            except Exception as e:
                logger.warning(
                    f"In-place stream update failed for {chat_id}; rejoining call: {e}")
                self._stream_replacements.discard(chat_id)
                try:
                    await client.leave_call(chat_id, close=False)
                except (ConnectionNotFound, exceptions.NotInCallError):
                    pass
                except Exception as leave_error:
                    logger.debug(
                        f"Call cleanup before rejoin failed for {chat_id}: {leave_error}")
                await asyncio.sleep(0.5)
                await self._play_media_impl(chat_id, None, media, preserve_call=False)
                asyncio.create_task(self._clear_stream_replacement(chat_id))
                return True

    async def _resync_video_stream(self, chat_id: int) -> bool:
        """Rebuild the video track after Telegram renegotiates an assistant track."""
        for attempt in range(3):
            try:
                # Recreate the source first. Pause/resume alone can leave the
                # audio process alive while the dropped video process stays gone.
                if not await self.restart_stream(chat_id):
                    continue

                await asyncio.sleep(0.2)
                if await self.pause(chat_id):
                    await asyncio.sleep(0.2)
                    if await self.resume(chat_id):
                        return True
            except Exception as error:
                logger.debug(
                    f"Video stream resync attempt {attempt + 1} failed for {chat_id}: {error}"
                )

            if attempt < 2:
                await asyncio.sleep(0.5)

        return False

    def _schedule_video_resync(self, chat_id: int) -> None:
        """Debounce recovery requests generated by a video-track renegotiation."""
        task = self._video_resync_tasks.get(chat_id)
        if task and not task.done():
            return

        async def resync() -> None:
            try:
                await asyncio.sleep(0.75)
                if await db.get_call(chat_id) and queue.get_current(chat_id):
                    await self._resync_video_stream(chat_id)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.debug(f"Scheduled video resync failed for {chat_id}: {error}")
            finally:
                self._video_resync_tasks.pop(chat_id, None)

        task = asyncio.create_task(resync())
        self._video_resync_tasks[chat_id] = task
        task.add_done_callback(_handle_task_exception)

    async def _play_media_impl(
        self,
        chat_id: int,
        message: Message | None,
        media: Media | Track,
        seek_time: int = 0,
        preserve_call: bool = False,
    ) -> None:
        """Play media in voice/video chat with stable WebRTC keyframe handling.

        Args:
            chat_id: Telegram chat ID to stream audio/video to.
            message: Originating command message (if any).
            media: Track or Media object containing file details.
            seek_time: Seek offset in seconds.
            preserve_call: If True, updates stream in-place via change_stream.
        """
        client = await db.get_assistant(chat_id)
        telegram_client = _unwrap_assistant_client(client)
        request_client = getattr(message, "_client", None) or app
        _lang = await lang.get_lang(chat_id)

        # 1. Ensure assistant is present in the group
        try:
            joined = await ensure_assistant_in_chat(request_client, client, chat_id, logger)
            if not joined:
                logger.warning(f"Assistant could not join chat {chat_id} before playback; aborting.")
                if preserve_call:
                    raise RuntimeError(f"Assistant failed to join chat {chat_id}")
                if message:
                    try:
                        await message.edit_text(_lang["play_invite_error"].format("assistant_join_failed"))
                    except Exception:
                        pass
                await self._stop_impl(chat_id)
                return
        except Exception as exc:
            logger.warning(f"Unable to verify assistant membership for {chat_id}: {exc}")

        try:
            await telegram_client.get_chat(chat_id)
        except (errors.ChannelInvalid, errors.PeerIdInvalid, errors.UserNotParticipant):
            try:
                await telegram_client.resolve_peer(chat_id)
                await asyncio.sleep(0.5)
            except (errors.ChannelInvalid, errors.PeerIdInvalid, errors.UserNotParticipant):
                logger.warning(f"Assistant could not resolve chat {chat_id}; continuing with fallback.")
        except Exception:
            pass

        # 2. Resolve thumbnail and file path
        if config.THUMB_GEN and isinstance(media, Track):
            _thumb = await thumb.generate(media)
        else:
            _thumb = config.DEFAULT_THUMB

        if not media.file_path:
            if message:
                return await message.edit_text(_lang["error_no_file"].format(config.SUPPORT_CHAT))
            else:
                logger.error(f"No file path for media in {chat_id}")
                return

        stream_path = (
            Path(media.file_path).resolve().as_posix()
            if "://" not in str(media.file_path)
            else media.file_path
        )

        if message and message.chat.type not in [
            enums.ChatType.SUPERGROUP,
            enums.ChatType.GROUP,
        ]:
            logger.error(f"Invalid chat type for {chat_id}: {message.chat.type}")
            await message.edit_text("❌ ᴄᴀɴ ᴏɴʟʏ ᴘʟᴀʏ ɪɴ ɢʀᴏᴜᴘꜱ.")
            return

        # 3. Stream parameter configuration (Video vs Audio)
        is_video = bool(getattr(media, "video", False))

        if is_video:
            # PyTgCalls creates separate raw audio/video outputs. Keep these
            # options shared by both FFmpeg processes; output codec flags such
            # as -vcodec would corrupt the audio process.
            seek_params = f"-ss {seek_time} " if seek_time > 1 else ""
            ffmpeg_params = (
                f"{seek_params}{VIDEO_STREAM_FFMPEG_PARAMETERS} "
                "-probesize 32M -analyzeduration 10M"
            )
            video_flags = types.MediaStream.Flags.REQUIRED
            video_params = types.VideoQuality.HD_720p
        else:
            if seek_time > 1:
                ffmpeg_params = f"-ss {seek_time} -vn -probesize 32M -analyzeduration 10M"
            else:
                ffmpeg_params = "-vn -probesize 10M -analyzeduration 5M"
            video_flags = types.MediaStream.Flags.IGNORE
            video_params = None

        # 4. Build MediaStream object with explicit video parameters
        current_fx = self.get_audio_fx(chat_id)
        if current_fx != "none":
            from OpenHeartsMusic.helpers import AudioEffectManager
            stream = AudioEffectManager.build_media_stream(
                stream_path,
                effect=current_fx,
                ffmpeg_parameters=ffmpeg_params,
                is_video=is_video,
            )
        elif chat_id in STUDIO_CHATS:
            stream = await get_studio_audio_stream(
                stream_path, chat_id, ffmpeg_params, video_flags=video_flags
            )
        else:
            karaoke_mode = self.get_karaoke_mode(chat_id)
            karaoke_filter = KARAOKE_PRESETS.get(karaoke_mode)
            if karaoke_mode != "off" and karaoke_filter:
                ffmpeg_params = f"{ffmpeg_params} -af {karaoke_filter}"
            stream_options = {
                "media_path": stream_path,
                "audio_path": stream_path,
                "audio_parameters": GROUP_CALL_AUDIO_QUALITY,
                "audio_flags": (
                    types.MediaStream.Flags.AUTO_DETECT
                    if is_video
                    else types.MediaStream.Flags.REQUIRED
                ),
                "video_flags": video_flags,
                "ffmpeg_parameters": ffmpeg_params,
            }
            if is_video:
                stream_options["video_parameters"] = video_params
            stream = types.MediaStream(**stream_options)

        # 5. Clear previous ghost call if starting a fresh stream
        if not preserve_call:
            try:
                await client.leave_call(chat_id, close=False)
                await asyncio.sleep(0.3)
            except (ConnectionNotFound, exceptions.NotInCallError):
                pass
            except Exception as e:
                logger.debug(f"Error leaving call for ghost stream prevention in {chat_id}: {e}")

        max_retries = 3
        retry_delay = 1

        # 6. Execute play or change_stream with retry logic
        try:
            for attempt in range(max_retries):
                try:
                    if preserve_call:
                        try:
                            await client.change_stream(chat_id=chat_id, stream=stream)
                        except (exceptions.NotInCallError, ConnectionNotFound):
                            await client.play(
                                chat_id=chat_id,
                                stream=stream,
                                config=types.GroupCallConfig(auto_start=True),
                            )
                    else:
                        await client.play(
                            chat_id=chat_id,
                            stream=stream,
                            config=types.GroupCallConfig(auto_start=True),
                        )
                    break
                except (exceptions.NoActiveGroupCall, errors.RPCError) as e:
                    error_msg = str(e)
                    if (
                        "CHANNEL_INVALID" in error_msg
                        or "CHANNEL_PRIVATE" in error_msg
                        or "GetChannels" in error_msg
                        or "GROUPCALL_INVALID" in error_msg
                        or "GROUPCALL" in error_msg
                        or isinstance(e, exceptions.NoActiveGroupCall)
                    ):
                        if attempt < max_retries - 1:
                            logger.warning(
                                f"Assistant play for {chat_id} hit stale channel state; retrying ({attempt + 1}/{max_retries})"
                            )
                            await asyncio.sleep(retry_delay)
                            try:
                                await telegram_client.resolve_peer(chat_id)
                            except Exception:
                                pass
                            continue
                        raise
                    raise
                except Exception as e:
                    error_msg = str(e).lower()
                    if "cannot be initialized more than once" in error_msg or "connection" in error_msg:
                        if attempt < max_retries - 1:
                            logger.debug(
                                f"Connection error for {chat_id}, retrying... ({attempt + 1}/{max_retries})"
                            )
                            if not preserve_call:
                                try:
                                    await client.leave_call(chat_id, close=False)
                                except Exception:
                                    pass
                            await asyncio.sleep(retry_delay)
                            continue
                        raise
                    raise

            if seek_time:
                media.time = seek_time
            else:
                media.time = 1

            if not seek_time:
                await db.add_call(chat_id)
                queue.set_current(chat_id, media)
                await db.playing(chat_id, paused=False)

                requester_name = getattr(media, "user", None) or "User"
                text = build_now_playing_caption(media, requester_name)
                if not media.is_live and media.duration_sec:
                    import time as time_module
                    played = media.time
                    duration = media.duration_sec
                    bar_length = 12
                    if duration == 0:
                        percentage = 0
                    else:
                        percentage = min((played / duration) * 100, 100)
                    filled = int(round(bar_length * percentage / 100))
                    timer_bar = "—" * filled + "●" + \
                        "—" * (bar_length - filled)
                    if duration >= 3600:
                        played_time = time_module.strftime(
                            '%H:%M:%S', time_module.gmtime(played))
                        total_time = time_module.strftime(
                            '%H:%M:%S', time_module.gmtime(duration))
                    else:
                        played_time = time_module.strftime(
                            '%M:%S', time_module.gmtime(played))
                        total_time = time_module.strftime(
                            '%M:%S', time_module.gmtime(duration))
                    timer_text = f"{played_time} {timer_bar} {total_time}"
                    bot_info = await app.get_me()
                    autoplay_enabled = await db.get_autoplay(chat_id)
                    keyboard = build_now_playing_buttons(
                        bot_username=bot_info.username or "OpenHeartsMusicBot",
                        chat_id=chat_id,
                        current_time=played_time,
                        total_time=total_time,
                        autoplay_enabled=autoplay_enabled,
                    )
                else:
                    bot_info = await app.get_me()
                    autoplay_enabled = await db.get_autoplay(chat_id)
                    keyboard = build_now_playing_buttons(
                        bot_username=bot_info.username or "OpenHeartsMusicBot",
                        chat_id=chat_id,
                        current_time="00:00",
                        total_time=str(media.duration or "04:56"),
                        autoplay_enabled=autoplay_enabled,
                    )

                if message:
                    try:
                        await message.delete()
                    except Exception:
                        pass

                # Send the intro once for each new track.
                # IMPORTANT: Await the intro to ensure all three messages are sent
                # STRICTLY BEFORE the Now Playing message appears.
                if not preserve_call:
                    await self._send_playback_intro(chat_id, media, _lang)

                sent_photo = await self._send_photo_with_retry(
                    chat_id=chat_id,
                    photo=_thumb,
                    caption=text,
                    reply_markup=keyboard,
                )
                if sent_photo and getattr(sent_photo, "id", None):
                    media.message_id = int(sent_photo.id)
                else:
                    media.message_id = 0
                    logger.debug(f"Playback status message not created for chat {chat_id}; using text fallback.")

                try:
                    from OpenHeartsMusic.plugins.utilities.lyrics import send_auto_lyrics

                    asyncio.create_task(send_auto_lyrics(app, chat_id, media.title))
                except Exception as e:
                    logger.debug(f"Error scheduling auto lyrics for {chat_id}: {e}")

                try:
                    task = asyncio.create_task(
                        preload.start_preload(chat_id, count=2))
                    task.add_done_callback(_handle_task_exception)
                except Exception as e:
                    logger.debug(f"Error starting preload for {chat_id}: {e}")
                if await db.get_autoplay(chat_id) and not queue.peek_next(chat_id, 1):
                    self._schedule_autoplay_prefetch(chat_id, media)
        except FileNotFoundError:
            if preserve_call:
                raise
            if message:
                try:
                    await message.edit_text(_lang["error_no_file"].format(config.SUPPORT_CHAT))
                except Exception:
                    pass
            await self._play_next_impl(chat_id)
        except exceptions.NoActiveGroupCall:
            if preserve_call:
                raise
            await self._stop_impl(chat_id)
            if message:
                try:
                    await message.edit_text(_lang["error_vc_disabled"])
                except Exception:
                    pass
        except errors.RPCError as e:
            if preserve_call:
                raise
            error_str = str(e)

            if any(x in error_str for x in ["CHAT_ADMIN_REQUIRED", "phone.CreateGroupCall", "GROUPCALL_FORBIDDEN", "GROUPCALL_CREATE_FORBIDDEN", "VOICE_MESSAGES_FORBIDDEN"]):
                await self._stop_impl(chat_id)
                if message:
                    try:
                        await message.edit_text(_lang["error_vc_disabled"])
                    except Exception:
                        pass
            elif "GROUPCALL_INVALID" in error_str or "GROUPCALL" in error_str:
                await self._stop_impl(chat_id)
                if message:
                    try:
                        await message.edit_text(_lang["error_no_call"])
                    except Exception:
                        pass
            else:
                logger.error(f"RPC error in play_media for {chat_id}: {e}")
                await self._stop_impl(chat_id)
        except exceptions.NoAudioSourceFound:
            if preserve_call:
                raise
            if message:
                try:
                    await message.edit_text(_lang["error_no_audio"])
                except Exception:
                    pass
            await self._play_next_impl(chat_id)
        except (ConnectionNotFound, TelegramServerError):
            if preserve_call:
                raise
            await self._stop_impl(chat_id)
            if message:
                try:
                    await message.edit_text(_lang["error_tg_server"])
                except Exception:
                    pass
        except TimeoutError as e:
            if preserve_call:
                raise
            error_msg = str(e)
            logger.warning(
                f"⏱️ Timeout joining voice chat {chat_id}: {error_msg}")
            await self._stop_impl(chat_id)
            if message:
                try:
                    await message.edit_text(
                        "⏱️ <b>ᴄᴏɴɴᴇᴄᴛɪᴏɴ ᴛɪᴍᴇᴅ ᴏᴜᴛ!</b>\n\n"
                        "<blockquote>ꜰᴀɪʟᴇᴅ ᴛᴏ ᴊᴏɪɴ ᴠᴏɪᴄᴇ ᴄʜᴀᴛ. ᴘʟᴇᴀꜱᴇ ᴄʜᴇᴄᴋ ʏᴏᴜʀ ɴᴇᴛᴡᴏʀᴋ ᴀɴᴅ ᴛʀʏ ᴀɢᴀɪɴ.</blockquote>"
                    )
                except Exception:
                    pass
            await asyncio.sleep(2)
            await self._play_next_impl(chat_id)
        except Exception as e:
            if preserve_call:
                raise
            logger.error(
                f"Unexpected error in play_media for {chat_id}: {e}", exc_info=True)
            await self._stop_impl(chat_id)
            if message:
                try:
                    await message.edit_text(f"❌ Playback error: {str(e)[:100]}")
                except Exception:
                    pass

    async def replay(self, chat_id: int) -> None:
        try:
            if not await db.get_call(chat_id):
                return

            media = queue.get_current(chat_id)
            _lang = await lang.get_lang(chat_id)
            msg = await app.send_message(chat_id=chat_id, text=_lang["play_again"])
            register_msg_to_delete(chat_id, msg.id)
            await self.play_media(chat_id, msg, media)
        except Exception as e:
            logger.error(f"Error in replay for {chat_id}: {e}", exc_info=True)

    async def seek_stream(self, chat_id: int, seconds: int) -> bool:
        """Seek to a specific position in the current stream."""
        try:
            if not await db.get_call(chat_id):
                return False

            media = queue.get_current(chat_id)
            if not media or media.is_live:
                return False

            client = await db.get_assistant(chat_id)
            _lang = await lang.get_lang(chat_id)

            media.time = seconds

            try:
                msg = await app.get_messages(chat_id, media.message_id)
            except Exception:
                msg = None

            if not msg:
                _lang = await lang.get_lang(chat_id)
                msg = await app.send_message(chat_id=chat_id, text=_lang["seeking"])
                register_msg_to_delete(chat_id, msg.id)

            await self.play_media(chat_id, msg, media, seek_time=seconds)
            return True
        except Exception as e:
            logger.warning(f"Seek stream failed for {chat_id}: {e}")
            return False

    async def validate_local_mp3(self, file_path: str) -> tuple[bool, str]:
        """Validate that a local MP3 file exists and is readable.

        Args:
            file_path: Path to the MP3 file

        Returns:
            Tuple of (is_valid, error_message)
        """
        import os

        if not file_path:
            return False, "File path is empty"

        if not os.path.exists(file_path):
            return False, f"File not found: {file_path}"

        if not os.path.isfile(file_path):
            return False, f"Path is not a file: {file_path}"

        if not os.access(file_path, os.R_OK):
            return False, f"File is not readable: {file_path}"

        file_size = os.path.getsize(file_path)
        if file_size == 0:
            return False, "File is empty"

        if file_size < 1024:  # Less than 1KB
            return False, "File is too small to be valid audio"

        return True, ""

    async def get_local_mp3_duration(self, file_path: str) -> int:
        """Get duration of local MP3 file in seconds using ffprobe.

        Args:
            file_path: Path to the MP3 file

        Returns:
            Duration in seconds, or 0 if unable to determine
        """
        import subprocess

        try:
            cmd = [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1:noesc=1",
                file_path,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                return int(float(result.stdout.strip()))
        except Exception as e:
            logger.debug(f"Failed to probe local MP3 duration: {e}")
        return 0

    async def stream_local_mp3(
        self,
        chat_id: int,
        file_path: str,
        title: str = "Local Karaoke Track",
        requester: str = "User",
        message: Message | None = None,
    ) -> bool:
        """Stream a local MP3 file as karaoke in voice chat.

        This feature allows streaming pre-downloaded or local MP3 files directly
        with full karaoke support (vocal removal, mode switching, effects).

        Args:
            chat_id: Target chat/group for streaming
            file_path: Absolute path to local MP3 file
            title: Track title for display (default: filename)
            requester: Name of user requesting the track
            message: Telegram message to edit with status

        Returns:
            True if streaming started successfully, False otherwise

        Example:
            success = await tune.stream_local_mp3(
                chat_id=12345,
                file_path="/path/to/song.mp3",
                title="Arijit Singh - Raabta",
                requester="John"
            )
        """
        try:
            # Validate file exists and is readable
            is_valid, error_msg = await self.validate_local_mp3(file_path)
            if not is_valid:
                if message:
                    await message.edit_text(f"❌ <b>File validation failed:</b> <code>{error_msg}</code>")
                logger.error(f"Local MP3 validation failed: {error_msg}")
                return False

            # Get audio duration
            duration_sec = await self.get_local_mp3_duration(file_path)

            # Format duration for display
            if duration_sec > 0:
                minutes = duration_sec // 60
                seconds = duration_sec % 60
                duration_str = f"{minutes}:{seconds:02d}"
            else:
                duration_str = "00:00"

            # Create Track object for local MP3
            import os
            from pathlib import Path

            filename = Path(file_path).name
            if not title or title == "Local Karaoke Track":
                title = filename.replace(".mp3", "").replace("_", " ")[:25]

            local_track = Track(
                id=Path(file_path).stem,
                channel_name="Local Karaoke",
                duration=duration_str,
                duration_sec=duration_sec,
                title=title,
                url=f"file://{file_path}",
                file_path=file_path,
                message_id=message.id if message else 0,
                user=requester,
                is_live=False,
                video=False,
            )

            # Add to queue and start playback
            queue.force_add(chat_id, local_track)

            if message:
                status_text = f"🎤 <b>Streaming local karaoke:</b> <code>{title}</code>\n<b>Duration:</b> {duration_str}"
                try:
                    await message.edit_text(status_text)
                except Exception:
                    pass

            await self.play_media(chat_id, message, local_track)
            logger.info(f"Local MP3 streaming started in {chat_id}: {file_path}")
            return True

        except Exception as e:
            logger.error(f"Error streaming local MP3 in {chat_id}: {e}", exc_info=True)
            if message:
                try:
                    await message.edit_text(f"❌ <b>Streaming error:</b> <code>{str(e)[:100]}</code>")
                except Exception:
                    pass
            return False

    async def play_next(self, chat_id: int) -> None:
        lock = self.get_lock(chat_id)

        if lock.locked():
            logger.info(
                f"play_next already running for {chat_id}, skipping duplicate call")
            return

        async with lock:
            await self._play_next_impl(chat_id)

    async def _play_next_impl(self, chat_id: int) -> None:
            try:
                if not await db.get_call(chat_id):
                    return

                await auto_clean_track_messages(app, chat_id)

                loop_mode = await db.get_loop(chat_id)
                autoplay_enabled = await db.get_autoplay(chat_id)

                if loop_mode == 1 and not autoplay_enabled:
                    media = queue.get_current(chat_id)
                    if media:
                        _lang = await lang.get_lang(chat_id)
                        try:
                            msg = await app.send_message(chat_id=chat_id, text=_lang["play_again"])
                            register_msg_to_delete(chat_id, msg.id)
                            await self._play_media_impl(chat_id, msg, media)
                        except errors.ChannelPrivate:
                            logger.warning(
                                f"Bot removed from {chat_id}, cleaning up")
                            try:
                                await self.leave_call(chat_id)
                            except (AttributeError, Exception) as leave_ex:
                                logger.debug(
                                    f"Could not leave call for {chat_id}: {leave_ex}")
                            await db.rm_chat(chat_id)
                        return

                current_track = queue.get_current(chat_id)
                media = queue.get_next(chat_id)

                if not media and loop_mode == 10:
                    all_items = queue.get_all(chat_id)
                    if all_items:
                        first_track = all_items[0]
                        _lang = await lang.get_lang(chat_id)
                        try:
                            msg = await app.send_message(chat_id=chat_id, text="🔁 Looping queue...")
                            register_msg_to_delete(chat_id, msg.id)
                            if not first_track.file_path:
                                is_live = getattr(
                                    first_track, 'is_live', False)
                                first_track.file_path = await yt.download(
                                    first_track.id,
                                    is_live=is_live,
                                    video=getattr(first_track, 'video', False),
                                )
                            first_track.message_id = msg.id
                            await self._play_media_impl(chat_id, msg, first_track)
                        except errors.ChannelPrivate:
                            logger.warning(
                                f"Bot removed from {chat_id}, cleaning up")
                            await self.leave_call(chat_id)
                            await db.rm_chat(chat_id)
                        return

                try:
                    if media and media.message_id:
                        await app.delete_messages(
                            chat_id=chat_id,
                            message_ids=media.message_id,
                            revoke=True,
                        )
                        media.message_id = 0
                except Exception as e:
                    logger.debug(
                        f"Could not delete previous message in {chat_id}: {e}")

                if not media:
                    if autoplay_enabled:
                        last_track = current_track
                        related = await self._take_autoplay_prefetch(
                            chat_id, getattr(last_track, "id", None)
                        )
                        if last_track:
                            if related is None:
                                try:
                                    related = await yt.related(
                                        video_id=last_track.id,
                                        m_id=0,
                                        parent_title=getattr(last_track, "title", None),
                                        video=getattr(last_track, "video", False),
                                        chat_id=chat_id,
                                    )
                                except Exception as e:
                                    logger.debug(
                                        f"Autoplay related lookup failed for {chat_id}: {e}")

                        if not related:
                            try:
                                related = await yt.random_autoplay_track(
                                    chat_id,
                                    m_id=0,
                                    exclude_id=getattr(last_track, "id", None),
                                )
                            except Exception as e:
                                logger.debug(
                                    f"Autoplay random fallback failed for {chat_id}: {e}")

                        for attempt in range(4):
                            if not related:
                                try:
                                    related = await yt.random_autoplay_track(
                                        chat_id,
                                        m_id=0,
                                        exclude_id=getattr(last_track, "id", None),
                                    )
                                except Exception as e:
                                    logger.debug(
                                        f"Autoplay random fallback failed for {chat_id}: {e}")
                            if not related:
                                continue

                            if last_track and related.id == last_track.id:
                                logger.warning(
                                    f"Autoplay returned the current track for {chat_id}; skipping it"
                                )
                                related = None
                                continue

                            if not related.file_path:
                                try:
                                    related.file_path = await yt.download(
                                        related.id,
                                        is_live=getattr(related, "is_live", False),
                                        video=getattr(related, "video", False),
                                    )
                                except Exception as e:
                                    logger.warning(
                                        f"Autoplay download failed for {related.id} in {chat_id}: {e}"
                                    )
                                    related = None
                                    continue

                            if related.file_path:
                                _lang = await lang.get_lang(chat_id)
                                msg = None
                                try:
                                    msg = await app.send_message(
                                        chat_id=chat_id,
                                        text="Spotify Radio 🟢",
                                    )
                                    if msg:
                                        register_msg_to_delete(chat_id, msg.id)
                                except errors.FloodWait as fw:
                                    logger.warning(
                                        f"FloodWait in autoplay for {chat_id}: skipping status message ({fw.value}s)")
                                except Exception as e:
                                    logger.debug(
                                        f"Could not send autoplay status message in {chat_id}: {e}")

                                related.user = "Autoplay"
                                related.message_id = msg.id if msg else 0
                                await self._play_media_impl(chat_id, msg, related)
                                return
                            related = None

                    if config.AUTO_END:
                        _lang = await lang.get_lang(chat_id)
                        try:
                            msg = await app.send_message(
                                chat_id=chat_id,
                                text=_lang.get(
                                    "auto_end", "✅ Queue finished. Stream ended automatically.")
                            )
                            register_msg_to_delete(chat_id, msg.id)
                        except Exception as e:
                            logger.debug(
                                f"Could not send auto_end message in {chat_id}: {e}")
                    return await self._stop_impl(chat_id)

                _lang = await lang.get_lang(chat_id)
                msg = None
                if not media.file_path:
                    is_live = getattr(media, 'is_live', False)
                    media.file_path = await yt.download(
                        media.id,
                        is_live=is_live,
                        video=getattr(media, 'video', False),
                    )
                    if not media.file_path:
                        await self._stop_impl(chat_id)
                        if msg:
                            try:
                                await msg.edit_text(
                                    _lang["error_no_file"].format(
                                        config.SUPPORT_CHAT)
                                )
                            except Exception:
                                pass
                        return

                try:
                    msg = await app.send_message(chat_id=chat_id, text=_lang["play_next"])
                    register_msg_to_delete(chat_id, msg.id)
                except errors.FloodWait as fw:
                    # Do not block playback on UI flood waits; continue without message.
                    logger.warning(
                        f"FloodWait in play_next for {chat_id}: skipping status message ({fw.value}s)")
                    msg = None
                except errors.ChannelPrivate:
                    logger.warning(f"Bot removed from {chat_id}, cleaning up")
                    await self.leave_call(chat_id)
                    await db.rm_chat(chat_id)
                    return
                except Exception as e:
                    logger.error(
                        f"Failed to send play_next message for {chat_id}: {e}")
                    msg = None

                media.message_id = msg.id if msg else 0
                if msg:
                    await self._play_media_impl(chat_id, msg, media)
                else:
                    logger.info(
                        f"Playing next track for {chat_id} without message update")
                    await self._play_media_impl(chat_id, None, media)

                try:
                    task = asyncio.create_task(
                        preload.start_preload(chat_id, count=2))
                    task.add_done_callback(_handle_task_exception)
                except Exception as e:
                    logger.debug(
                        f"Error starting preload after play_next for {chat_id}: {e}")
            except Exception as e:
                logger.error(
                    f"Error in play_next for {chat_id}: {e}", exc_info=True)
                try:
                    await self._stop_impl(chat_id)
                except Exception:
                    pass

    async def ping(self) -> float:
        pings = [client.ping for client in self.clients]
        return round(sum(pings) / len(pings), 2)

    async def _handle_assistant_unmute(
        self,
        client,
        assistant_id: int,
        update: raw.types.UpdateGroupCallParticipants,
    ) -> None:
        for chat_id in list(db.active_calls):
            try:
                assigned_client = await db.get_assistant(chat_id)
                if assigned_client is not client:
                    continue

                media = queue.get_current(chat_id)
                if not media or not getattr(media, "video", False):
                    continue

                for participant in update.participants:
                    peer = getattr(participant, "peer", None)
                    user_id = getattr(peer, "user_id", None)
                    if user_id != assistant_id:
                        continue
                    if participant.muted is None:
                        continue

                    state_key = (chat_id, user_id)
                    self._assistant_mute_state[state_key] = participant.muted
                    # Telegram can omit the muted=True update. Treat every
                    # unmuted report as a recovery signal; scheduling is
                    # debounced so duplicate participant updates are harmless.
                    if participant.muted is False:
                        self._schedule_video_resync(chat_id)
            except Exception as exc:
                logger.debug(f"Assistant unmute resync failed for {chat_id}: {exc}")

    async def decorators(self, client: PyTgCalls) -> None:
        for client in self.clients:
            @client.on_update()
            async def update_handler(_, update: types.Update) -> None:
                try:
                    if isinstance(update, types.StreamEnded):
                        chat_id = update.chat_id
                        if update.stream_type == types.StreamEnded.Type.VIDEO:
                            if chat_id in self._stream_replacements:
                                return
                            # Telegram can tear down only the video track during
                            # mute/unmute renegotiation while audio continues.
                            # Re-negotiate the active stream without advancing
                            # the queue.
                            current_media = queue.get_current(chat_id)
                            if (await db.get_call(chat_id)
                                    and current_media
                                    and getattr(current_media, "video", False)):
                                self._schedule_video_resync(chat_id)
                            return
                        if update.stream_type == types.StreamEnded.Type.AUDIO:
                            if chat_id in self._stream_replacements:
                                self._stream_replacements.discard(chat_id)
                                logger.debug(
                                    f"Ignoring replaced audio stream end for {chat_id}")
                                return
                            current_time = asyncio.get_event_loop().time()

                            if chat_id in self._stream_end_cache:
                                if current_time - self._stream_end_cache[chat_id] < 2.0:
                                    return

                            self._stream_end_cache[chat_id] = current_time

                            self._stream_end_cache = {
                                cid: t for cid, t in self._stream_end_cache.items()
                                if current_time - t < 5.0
                            }

                            await auto_clean_track_messages(app, chat_id)
                            await self._play_next_impl(chat_id)
                    elif isinstance(update, types.ChatUpdate):
                        if update.status in [
                            types.ChatUpdate.Status.KICKED,
                            types.ChatUpdate.Status.LEFT_GROUP,
                            types.ChatUpdate.Status.CLOSED_VOICE_CHAT,
                        ]:
                            await self.stop(update.chat_id)
                except (ConnectionNotFound, exceptions.NotInCallError, TelegramServerError):
                    return
                except Exception as e:
                    logger.debug(f"Ignoring update handler error: {e}")

    async def boot(self) -> None:
        PyTgCallsSession.notice_displayed = True
        for ub in userbot.clients:
            assistant_index = userbot.clients.index(ub)
            assistant_id = ub.me.id

            @ub.on_raw_update(group=19)
            async def assistant_unmute_handler(
                client, update, users, chats,
                index=assistant_index,
                user_id=assistant_id,
            ):
                if isinstance(update, raw.types.UpdateGroupCallParticipants):
                    if index < len(self.clients):
                        await self._handle_assistant_unmute(
                            self.clients[index], user_id, update
                        )

            client = PyTgCalls(ub, cache_duration=100)
            await client.start()
            self.clients.append(client)
            await self.decorators(client)
            logger.info("📞 PyTgCalls client(s) started.")
