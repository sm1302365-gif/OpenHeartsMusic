# ==============================================================================
# misc.py - Background Tasks & Events
# ==============================================================================
# Background jobs like auto-leaving empty calls, tracking playback time,
# updating progress bars, and handling voice chat state changes.
# ==============================================================================

import asyncio
import time

from hydrogram import enums, filters, types
from hydrogram.errors import MessageIdInvalid, MessageNotModified, RPCError


from OpenHeartsMusic import tune, app, config, db, lang, logger, queue, tasks, userbot, yt
from OpenHeartsMusic.helpers import (
    buttons,
    build_now_playing_buttons,
    build_now_playing_caption,
)


def _consume_task_exception(task: asyncio.Task) -> None:
    """Retrieve task exceptions without raising during normal cancellation."""
    if task.cancelled() or not task.done():
        return
    task.exception()




@app.on_message(filters.video_chat_started, group=19)
@app.on_message(filters.video_chat_ended, group=20)
async def _watcher_vc(_, m: types.Message):
    await tune.stop(m.chat.id)


async def auto_leave():
    while True:
        try:
            await asyncio.sleep(1800)
            for ub in userbot.clients:
                left = 0
                try:
                    for dialog in await ub.get_dialogs():
                        chat_id = dialog.chat.id
                        if left >= 20:
                            break
                        # Skip logger and any excluded chats
                        excluded = [app.logger] + config.EXCLUDED_CHATS
                        if chat_id in excluded:
                            continue
                        if dialog.chat.type in [
                            enums.ChatType.GROUP,
                            enums.ChatType.SUPERGROUP,
                        ]:
                            if chat_id in db.active_calls:
                                continue
                            await ub.leave_chat(chat_id)
                            left += 1
                        await asyncio.sleep(5)
                except Exception as e:
                    logger.error(f"Auto-leave error for assistant {ub.me.username if hasattr(ub, 'me') and ub.me else 'Unknown'}: {e}")
                    continue
        except Exception as e:
            logger.error(f"Critical error in auto_leave task: {e}")
            await asyncio.sleep(60)  # Wait before retrying
            continue


async def track_time():
    while True:
        try:
            await asyncio.sleep(1)
            for chat_id in list(db.active_calls):
                try:
                    if not await db.playing(chat_id):
                        continue
                    media = queue.get_current(chat_id)
                    if not media:
                        continue
                    media.time += 1
                except Exception as e:
                    # Log error but continue tracking other chats
                    logger.debug(f"track_time error for chat {chat_id}: {e}")
                    continue
        except Exception as e:
            logger.error(f"Critical error in track_time task: {e}")
            await asyncio.sleep(1)  # Brief pause before retrying
            continue


def format_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return (
        f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        if hours
        else f"{minutes:02d}:{seconds:02d}"
    )


async def refresh_now_playing_message(message, song, bot_username: str):
    if not message or not song:
        return

    current_time_str = format_duration(getattr(song, "time", 0))
    total_time_str = format_duration(getattr(song, "duration_sec", 0))

    requester_name = getattr(song, "user", None) or "User"
    caption = build_now_playing_caption(song, requester_name=requester_name)
    autoplay_enabled = await db.get_autoplay(message.chat.id)
    buttons = build_now_playing_buttons(
        bot_username=bot_username,
        chat_id=message.chat.id,
        current_time=current_time_str,
        total_time=total_time_str,
        autoplay_enabled=autoplay_enabled,
    )

    try:
        await message.edit_caption(
            caption=caption,
            reply_markup=buttons,
            parse_mode=enums.ParseMode.HTML,
        )
    except Exception as exc:
        logger.debug(f"Failed to refresh now playing caption: {exc}")


async def refresh_now_playing_keyboard(message, song, bot_username: str):
    if not message or not song:
        return

    current_time_str = format_duration(getattr(song, "time", 0))
    total_time_str = format_duration(getattr(song, "duration_sec", 0))

    autoplay_enabled = await db.get_autoplay(message.chat.id)
    buttons = build_now_playing_buttons(
        bot_username=bot_username,
        chat_id=message.chat.id,
        current_time=current_time_str,
        total_time=total_time_str,
        autoplay_enabled=autoplay_enabled,
    )

    try:
        await message.edit_reply_markup(reply_markup=buttons)
    except Exception as exc:
        logger.debug(f"Failed to refresh now playing keyboard: {exc}")


async def auto_update_timer(chat_id: int, message, song, bot_username: str):
    # 1. Validate that the message object exists
    if not message:
        return

    while True:
        await asyncio.sleep(10)

        # 2. Safely check if song exists and extract duration
        if not song:
            break

        total_time_str = getattr(song, "duration", "04:56")
        current_time_str = format_duration(getattr(song, "time", 0))

        # 3. Ensure valid message id
        msg_id = getattr(message, "id", None)
        try:
            msg_id = int(msg_id)
        except (TypeError, ValueError):
            msg_id = None
        if not msg_id or msg_id <= 0:
            break

        autoplay_enabled = await db.get_autoplay(chat_id)
        updated_buttons = build_now_playing_buttons(
            bot_username=bot_username,
            chat_id=chat_id,
            current_time=current_time_str,
            total_time=total_time_str,
            autoplay_enabled=autoplay_enabled,
        )

        try:
            await message.edit_reply_markup(reply_markup=updated_buttons)
        except (MessageIdInvalid, MessageNotModified):
            break
        except RPCError as err:
            logger.debug(f"Timer error for chat {chat_id}: {err}")
            break
        except Exception as err:
            logger.debug(f"Update_timer error for chat {chat_id}: {err}")
            break


async def update_timer(length=10):
    chat_tasks = {}  # Track individual chat update tasks

    async def _preload_next(chat_id, next_media):
        try:
            if not next_media or not getattr(next_media, "id", None):
                return
            if getattr(next_media, "file_path", None):
                return
            next_media.file_path = await yt.download(
                next_media.id,
                video=getattr(next_media, "video", False),
            )
        except Exception as e:
            print(f"Preload error for chat {chat_id}: {e}")

    async def update_chat_timer(chat_id):
        bot_info = await app.get_me()
        bot_username = bot_info.username or "OpenHeartsMusicBot"

        while True:
            try:
                await asyncio.sleep(20)

                # Check if chat is still active and playing
                if chat_id not in db.active_calls or not await db.playing(chat_id):
                    break

                media = queue.get_current(chat_id)
                if not media:
                    break

                # Ensure media.time is initialized
                if not hasattr(media, 'time') or media.time is None:
                    media.time = 0

                duration = getattr(media, "duration_sec", None)
                message_id = getattr(media, "message_id", None)
                try:
                    message_id = int(message_id)
                except (TypeError, ValueError):
                    message_id = None

                if not duration or not message_id or message_id <= 0:
                    continue

                played = getattr(media, "time", 0) or 0
                remaining = duration - played

                # Pre-download next song if needed (don't block timer update)
                if remaining <= 30:
                    next_media = queue.get_next(chat_id, check=True)
                    if next_media and getattr(next_media, "id", None) and not getattr(next_media, "file_path", None):
                        task = asyncio.create_task(_preload_next(chat_id, next_media))
                        task.add_done_callback(_consume_task_exception)

                message = await app.get_messages(chat_id, message_id)
                if not message:
                    continue
                await refresh_now_playing_keyboard(message, media, bot_username)

            except Exception as e:
                error_str = str(e)
                # Silently ignore expected Telegram API errors
                if not any(err in error_str for err in [
                    "MESSAGE_NOT_MODIFIED",
                    "MESSAGE_ID_INVALID",
                    "MESSAGE_DELETE",
                    "MESSAGE_AUTHOR_REQUIRED",
                    "CHAT_ADMIN_REQUIRED",
                    "CHANNEL_PRIVATE",
                    "haven't joined this channel"
                ]):
                    print(f"update_timer error for chat {chat_id}: {e}")
                # Stop tracking chats with CHANNEL_PRIVATE errors
                if "CHANNEL_PRIVATE" in error_str:
                    break
                await asyncio.sleep(1)  # Brief pause before retry

    # Monitor and spawn individual chat timers
    while True:
        await asyncio.sleep(2)  # Check for new chats every 2 seconds

        for chat_id in list(db.active_calls):
            # Start timer for new active chats
            if chat_id not in chat_tasks:
                task = asyncio.create_task(update_chat_timer(chat_id))
                task.add_done_callback(_consume_task_exception)
                chat_tasks[chat_id] = task

        # Clean up finished tasks
        finished_chats = [
            chat_id for chat_id, task in chat_tasks.items()
            if task.done() or chat_id not in db.active_calls
        ]
        for chat_id in finished_chats:
            chat_tasks.pop(chat_id, None)


async def vc_watcher(sleep=15):
    alone_times = {}  # Track when assistant started being alone in VC
    LEAVE_TIMEOUT = 300  # 5 minutes in seconds (hardcoded)

    while True:
        await asyncio.sleep(sleep)
        current_time = time.time()

        for chat_id in list(db.active_calls):
            try:
                # Check if auto-leave is enabled for this chat
                if not await db.get_autoleave(chat_id):
                    alone_times.pop(chat_id, None)
                    continue

                client = await db.get_assistant(chat_id)

                # Check if userbot is actually in the call
                try:
                    participants = await client.get_participants(chat_id)
                except Exception as call_err:
                    # Userbot is not in the call or call doesn't exist
                    # Remove from tracking and continue
                    alone_times.pop(chat_id, None)
                    continue

                # Check if only assistant is in VC (participants < 2 means only assistant)
                if len(participants) < 2:
                    # Start tracking alone time
                    if chat_id not in alone_times:
                        alone_times[chat_id] = current_time
                    else:
                        # Check if alone for 5 minutes
                        alone_duration = current_time - alone_times[chat_id]
                        if alone_duration >= LEAVE_TIMEOUT:
                            _lang = await lang.get_lang(chat_id)
                            try:
                                current_media = queue.get_current(chat_id)
                                if current_media and current_media.message_id:
                                    sent = await app.edit_message_reply_markup(
                                        chat_id=chat_id,
                                        message_id=current_media.message_id,
                                        reply_markup=buttons.controls(
                                            chat_id=chat_id, status=_lang["stopped"], remove=True
                                        ),
                                    )
                                    await sent.reply_text(_lang["auto_left"])
                            except:
                                pass

                            # Stop playback and leave
                            await tune.stop(chat_id)
                            try:
                                await client.leave_call(chat_id, close=False)
                            except Exception as e:
                                # Suppress expected call disconnection errors
                                error_msg = str(e).lower()
                                if not any(ignore in error_msg for ignore in [
                                    "not in a call",
                                    "not in the group call",
                                    "no active group call",
                                    "call was already stopped",
                                    "call already disconnected"
                                ]):
                                    print(f"Error leaving call for {chat_id}: {e}")
                            alone_times.pop(chat_id, None)
                else:
                    # Reset timer if users join
                    alone_times.pop(chat_id, None)

            except Exception as e:
                print(f"vc_watcher error for chat {chat_id}: {e}")
                alone_times.pop(chat_id, None)
                continue


# Always run VC watcher to check for empty voice chats. This must be scheduled
# only when an event loop is actively running; importing the plugin during
# discovery should not fail simply because no loop is alive yet.
try:
    asyncio.get_running_loop()
except RuntimeError:
    pass
else:
    task = asyncio.create_task(vc_watcher())
    task.add_done_callback(_consume_task_exception)
    tasks.append(task)
    if config.AUTO_LEAVE:
        task = asyncio.create_task(auto_leave())
        task.add_done_callback(_consume_task_exception)
        tasks.append(task)
    task = asyncio.create_task(track_time())
    task.add_done_callback(_consume_task_exception)
    tasks.append(task)
    task = asyncio.create_task(update_timer())
    task.add_done_callback(_consume_task_exception)
    tasks.append(task)
