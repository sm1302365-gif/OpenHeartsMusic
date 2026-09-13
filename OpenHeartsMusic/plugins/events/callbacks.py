# ==============================================================================
# callbacks.py - Button Interactions & Styled UI Handling
# ==============================================================================
# All the logic for when users click inline buttons (skipping tracks, pausing,
# navigating the help menu, studio mode, and style parameters).
# ==============================================================================

import re
import asyncio
from functools import wraps

from hydrogram import filters, types, enums
from hydrogram.errors import FloodWait, QueryIdInvalid
from hydrogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from OpenHeartsMusic import tune, app, config, db, lang, logger, queue, tg, yt
from OpenHeartsMusic.helpers import admin_check, buttons, can_manage_vc
from OpenHeartsMusic.helpers._autoplay import toggle_autoplay
from OpenHeartsMusic.helpers._message_cleanup import register_msg_to_delete
from config import CustomFonts


def safe_callback(func):
    """Decorator to safely handle callback queries and prevent unhandled exceptions."""
    @wraps(func)
    async def wrapper(client, query: types.CallbackQuery):
        try:
            return await func(client, query)
        except QueryIdInvalid:
            return
        except Exception as e:
            logger.error(f"Error in callback {func.__name__}: {e}", exc_info=True)
            try:
                await query.answer("❌ An error occurred. Please try again.", show_alert=True)
            except Exception:
                pass
    return wrapper


@app.on_callback_query(filters.regex("^start$") & ~app.bl_users)
@lang.language()
@safe_callback
async def _start_callback(_, query: types.CallbackQuery):
    """Handle start callback query and return to the main menu."""
    await query.answer()

    _text = query.lang["start_pm"].format(query.from_user.first_name, app.name)
    key = buttons.start_key(query.lang, True)

    try:
        await query.edit_message_caption(
            caption=_text,
            reply_markup=key,
            parse_mode=enums.ParseMode.HTML,
        )
    except Exception:
        try:
            await query.edit_message_text(
                text=_text,
                reply_markup=key,
                parse_mode=enums.ParseMode.HTML,
            )
        except Exception:
            pass


@app.on_callback_query(filters.regex("cancel_dl") & ~app.bl_users)
@lang.language()
@safe_callback
async def cancel_dl(_, query: types.CallbackQuery):
    """Cancel ongoing download process."""
    await query.answer()
    await tg.cancel(query)


@app.on_callback_query(filters.regex(r"^cb_progress") & ~app.bl_users)
@safe_callback
async def cb_progress_handler(_, query: CallbackQuery):
    """Handle live progress bar callback interaction."""
    await query.answer("⏱ Live Progress Bar", show_alert=False)


@app.on_callback_query(filters.regex(r"^toggle_autoplay$") & ~app.bl_users)
@lang.language()
@admin_check
@safe_callback
async def toggle_autoplay_callback(_, query: CallbackQuery):
    """Toggle autoplay settings and dynamically update button text & style colors for all buttons."""
    await query.answer()
    chat_id = query.message.chat.id
    new_state = await toggle_autoplay(chat_id)

    if query.message.reply_markup:
        updated_markup = query.message.reply_markup
        for row in updated_markup.inline_keyboard:
            for button in row:
                cb_data = getattr(button, "callback_data", "") or ""

                # Dynamic style assignment based on button functionality
                if cb_data == "toggle_autoplay":
                    button.text = (
                        "🔄 Autoplay: 🟢 ON"
                        if new_state
                        else "🔄 Autoplay: 🔴 OFF"
                    )
                    button.style = "success" if new_state else "danger"
                elif "close" in cb_data or "stop" in cb_data:
                    button.style = "danger"
                elif "play" in cb_data or "resume" in cb_data:
                    button.style = "success"
                else:
                    button.style = "primary"

        try:
            await query.message.edit_reply_markup(reply_markup=updated_markup)
        except Exception:
            pass

    try:
        await query.message.reply_text(
            query.lang["autoplay_enabled"] if new_state else query.lang["autoplay_disabled"],
            quote=False,
            parse_mode=enums.ParseMode.HTML,
        )
    except Exception:
        pass


@app.on_callback_query(filters.regex(r"^toggle_studio$") & ~app.bl_users)
@lang.language()
@admin_check
@safe_callback
async def toggle_studio_callback(_, query: CallbackQuery):
    """Handle studio mode toggle callback."""
    await query.answer()
    try:
        studio_text = getattr(CustomFonts, "STUDIO_ACTIVATED", "<b>Studio</b>\n\n🎧 <i>Studio mode activated with premium audio styling!</i>")
        await query.message.reply_text(studio_text, quote=False, parse_mode=enums.ParseMode.HTML)
    except Exception:
        await query.message.reply_text("🎧 Studio mode is not available.", quote=False)


@app.on_callback_query(filters.regex(r"^close") & ~app.bl_users)
@safe_callback
async def close_handler(_, query: CallbackQuery):
    """Delete message upon close button interaction."""
    try:
        await query.message.delete()
    except Exception:
        pass


@app.on_callback_query(filters.regex(r"^ADMIN_(PAUSE|RESUME|SKIP|STOP|REPLAY)") & ~app.bl_users)
@safe_callback
async def admin_controls(_, query: CallbackQuery):
    """Handle quick admin playback control buttons."""
    data = query.data.split("|")
    action = data[0]
    chat_id = int(data[1]) if (len(data) > 1 and data[1] != "0") else query.message.chat.id

    try:
        if action == "ADMIN_PAUSE":
            await tune.pause(chat_id)
            await query.answer("Music Paused ⏸", show_alert=True)

        elif action == "ADMIN_RESUME":
            await tune.resume(chat_id)
            await query.answer("Music Resumed ▶️", show_alert=True)

        elif action == "ADMIN_SKIP":
            await tune.play_next(chat_id)
            await query.answer("Skipped Song >>", show_alert=True)

        elif action == "ADMIN_STOP":
            await tune.stop(chat_id)
            await query.answer("Stream Stopped ⏹", show_alert=True)

        elif action == "ADMIN_REPLAY":
            await tune.seek_stream(chat_id, 0)
            await query.answer("Replaying Song ↺", show_alert=True)

    except Exception as err:
        await query.answer(f"Error: {err}", show_alert=True)


@app.on_callback_query(filters.regex("controls") & ~app.bl_users)
@lang.language()
@safe_callback
async def _controls(_, query: types.CallbackQuery):
    """Handle general playback controls and menu navigation."""
    args = query.data.split()
    action, chat_id = args[1], int(args[2])
    qaction = len(args) == 4
    user = query.from_user.mention

    if action == "close":
        await query.answer()
        try:
            await query.message.delete()
        except Exception:
            pass
        return

    user_id = query.from_user.id
    has_permission = False

    if user_id in app.sudoers:
        has_permission = True
    elif await db.is_auth(chat_id, user_id):
        has_permission = True
    else:
        admins = await db.get_admins(chat_id)
        if user_id in admins:
            has_permission = True

    if not has_permission:
        return await query.answer("⚠️ ʏᴏᴜ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ᴘᴇʀᴍɪssɪᴏɴ ᴛᴏ ᴜsᴇ ᴛʜɪs.", show_alert=True)

    if not await db.get_call(chat_id):
        return await query.answer(query.lang["not_playing"], show_alert=True)

    if action == "status":
        return await query.answer()

    if action.startswith("seek_"):
        return await handle_seek(query, chat_id, action, user)

    if action == "loop":
        return await handle_loop(query, chat_id, user)

    await query.answer(query.lang["processing"], show_alert=True)

    if action == "pause":
        if not await db.playing(chat_id):
            return await query.answer(
                query.lang["play_already_paused"], show_alert=True
            )
        if not await tune.pause(chat_id):
            return await query.answer(query.lang["not_playing"], show_alert=True)
        if qaction:
            return await query.edit_message_reply_markup(
                reply_markup=buttons.queue_markup(
                    chat_id, query.lang["paused"], False)
            )
        status = query.lang["paused"]
        reply = query.lang["play_paused"].format(user)

    elif action == "resume":
        status = query.lang["playing"]
        if await db.playing(chat_id):
            return await query.answer(query.lang["play_not_paused"], show_alert=True)
        if not await tune.resume(chat_id):
            return await query.answer(query.lang["not_playing"], show_alert=True)
        if qaction:
            return await query.edit_message_reply_markup(
                reply_markup=buttons.queue_markup(
                    chat_id, query.lang["playing"], True)
            )
        reply = query.lang["play_resumed"].format(user)

    elif action == "skip":
        await tune.play_next(chat_id)
        status = query.lang["skipped"]
        reply = query.lang["play_skipped"].format(user)

    elif action == "force":
        pos, media = queue.check_item(chat_id, args[3])
        if not media or pos == -1:
            return await query.edit_message_text(query.lang["play_expired"])

        current = queue.get_current(chat_id)
        m_id = current.message_id if current else None
        queue.force_add(chat_id, media, remove=pos)
        try:
            await app.delete_messages(
                chat_id=chat_id, message_ids=[
                    m_id, media.message_id], revoke=True
            )
            media.message_id = None
        except:
            pass

        msg = await app.send_message(chat_id=chat_id, text=query.lang["play_next"])
        if not media.file_path:
            media.file_path = await yt.download(
                media.id,
                video=getattr(media, "video", False),
            )
        media.message_id = msg.id
        return await tune.play_media(chat_id, msg, media)

    elif action == "replay":
        media = queue.get_current(chat_id)
        media.user = user
        await tune.replay(chat_id)
        status = query.lang["replayed"]
        reply = query.lang["play_replayed"].format(user)

    elif action == "stop":
        await tune.stop(chat_id)
        status = query.lang["stopped"]
        reply = query.lang["play_stopped"].format(user)

    try:
        if action in ["skip", "replay", "stop"]:
            try:
                sent = await query.message.reply_text(reply, quote=False)
                register_msg_to_delete(chat_id, sent.id)
            except FloodWait as e:
                await asyncio.sleep(e.value)
                try:
                    sent = await query.message.reply_text(reply, quote=False)
                    register_msg_to_delete(chat_id, sent.id)
                except Exception:
                    pass
            except Exception:
                pass
        else:
            mtext = re.sub(
                r"\n\n<blockquote>.*?</blockquote>",
                "",
                query.message.caption.html or query.message.text.html,
                flags=re.DOTALL,
            )
            keyboard = buttons.controls(
                chat_id, status=status if action != "resume" else None
            )
            await query.edit_message_text(
                f"{mtext}\n\n<blockquote>{reply}</blockquote>",
                reply_markup=keyboard,
                parse_mode=enums.ParseMode.HTML
            )
    except FloodWait as e:
        await asyncio.sleep(e.value)
        try:
            await query.edit_message_text(
                f"{mtext}\n\n<blockquote>{reply}</blockquote>",
                reply_markup=keyboard,
                parse_mode=enums.ParseMode.HTML
            )
        except Exception:
            pass
    except Exception:
        pass


async def handle_seek(query: types.CallbackQuery, chat_id: int, action: str, user: str):
    """Handle stream seeking forward and backward."""
    media = queue.get_current(chat_id)
    if not media or media.is_live:
        return await query.answer("⚠️ ᴄᴀɴɴᴏᴛ ꜱᴇᴇᴋ ɪɴ ʟɪᴠᴇ ꜱᴛʀᴇᴀᴍꜱ!", show_alert=True)

    if not media.duration_sec or media.duration_sec == 0:
        return await query.answer("⚠️ ᴄᴀɴɴᴏᴛ ꜱᴇᴇᴋ ɪɴ ᴛʜɪꜱ ᴛʀᴀᴄᴋ!", show_alert=True)

    if action == "seek_back_10":
        seconds = -10
    elif action == "seek_back_30":
        seconds = -30
    elif action == "seek_forward_10":
        seconds = 10
    elif action == "seek_forward_30":
        seconds = 30
    else:
        return await query.answer("⚠️ ɪɴᴠᴀʟɪᴅ ꜱᴇᴇᴋ ᴀᴄᴛɪᴏɴ!", show_alert=True)

    current_time = getattr(media, 'time', 0)
    new_time = max(0, min(current_time + seconds, media.duration_sec - 5))

    if new_time == 0 and seconds < 0:
        return await query.answer(f"⏮️ ᴀʟʀᴇᴀᴅʏ ᴀᴛ ᴛʜᴇ ʙᴇɢɪɴɴɪɴɢ!", show_alert=True)
    if new_time >= media.duration_sec - 5 and seconds > 0:
        return await query.answer(f"⏭️ ᴛᴏᴏ ᴄʟᴏꜱᴇ ᴛᴏ ᴛʜᴇ ᴇɴᴅ!", show_alert=True)

    success = await tune.seek_stream(chat_id, int(new_time))
    if success:
        import time as time_module
        if media.duration_sec >= 3600:
            time_str = time_module.strftime('%H:%M:%S', time_module.gmtime(new_time))
        else:
            time_str = time_module.strftime('%M:%S', time_module.gmtime(new_time))

        await query.answer(f"✅ ꜱᴇᴇᴋᴇᴅ ᴛᴏ {time_str}", show_alert=True)
        try:
            await query.message.reply_text(
                f"✅ ꜱᴇᴇᴋᴇᴅ ᴛᴏ {time_str}\n\n<blockquote>ʙʏ {user}</blockquote>",
                quote=False,
                parse_mode=enums.ParseMode.HTML
            )
        except FloodWait:
            pass
        except Exception:
            pass


async def handle_loop(query: types.CallbackQuery, chat_id: int, user: str):
    """Handle loop mode toggling."""
    current_loop = await db.get_loop(chat_id)

    if current_loop == 0:
        new_loop = 1
        text = "🔂 ʟᴏᴏᴘ: ꜱɪɴɢʟᴇ ᴛʀᴀᴄᴋ"
        message = f"🔂 ʟᴏᴏᴘ ᴍᴏᴅᴇ ꜱᴇᴛ ᴛᴏ <b>ꜱɪɴɢʟᴇ ᴛʀᴀᴄᴋ</b>"
    elif current_loop == 1:
        new_loop = 10
        text = "🔁 ʟᴏᴏᴘ: ǫᴜᴇᴜᴇ"
        message = f"🔁 ʟᴏᴏᴘ ᴍᴏᴅᴇ ꜱᴇᴛ ᴛᴏ <b>ǫᴜᴇᴜᴇ</b>"
    else:
        new_loop = 0
        text = "➡️ ʟᴏᴏᴘ: ᴏꜰꜰ"
        message = f"➡️ ʟᴏᴏᴘ ᴍᴏᴅᴇ <b>ᴅɪꜱᴀʙʟᴇᴅ</b>"

    await db.set_loop(chat_id, new_loop)
    await query.answer(text, show_alert=False)
    await query.message.reply_text(message, quote=False, parse_mode=enums.ParseMode.HTML)


@app.on_callback_query(filters.regex(r"^(?:help|autoplay_help)") & ~app.bl_users)
@lang.language()
@safe_callback
async def _help(_, query: types.CallbackQuery):
    """Handle help menu navigation callbacks."""
    await query.answer()

    if query.data in ("help", "help_main"):
        try:
            await query.edit_message_caption(
                caption=query.lang["help_menu"],
                reply_markup=buttons.help_markup(query.lang),
                parse_mode=enums.ParseMode.HTML,
            )
        except Exception:
            try:
                await query.edit_message_text(
                    text=query.lang["help_menu"],
                    reply_markup=buttons.help_markup(query.lang),
                    parse_mode=enums.ParseMode.HTML,
                )
            except Exception:
                pass
        return

    category = (
        "autoplay"
        if query.data == "autoplay_help"
        else query.data.replace("help_", "")
    )

    if category == "main":
        try:
            help_text = (
                f"{query.lang['help_menu']}\n\n"
                "<b>📚 ᴄᴏᴍᴍᴀɴᴅs:</b>\n"
                "• /play, /pause, /resume, /skip, /stop\n"
                "• /queue, /loop, /seek, /seekback, /seekforward\n"
                "• /auth, /unauth, /authlist\n"
                "• /assistantjoin, /joinassistant\n"
                "• /ping, /stats, /help\n"
                "• /delete or /del"
            )
            await query.edit_message_caption(
                caption=help_text,
                reply_markup=buttons.help_markup(query.lang),
                parse_mode=enums.ParseMode.HTML,
            )
        except Exception:
            try:
                await query.edit_message_text(
                    text=help_text,
                    reply_markup=buttons.help_markup(query.lang),
                    parse_mode=enums.ParseMode.HTML,
                )
            except Exception:
                pass
        return

    help_texts = {
        "admins": query.lang["help_admins"],
        "auth": query.lang["help_auth"],
        "broadcast": query.lang["help_sudo"],
        "blchat": query.lang["help_blchat"],
        "bluser": query.lang["help_bluser"],
        "loop": query.lang["help_loop"],
        "delete": (
            "❖ <b>SMART AUTO-CLEAN</b> ❖\n\n"
            "To keep your group clean and spam-free, we have added the <b>Auto-Clean Feature</b> to our bot!\n\n"
            "❍ <b>How does it work?</b>\n"
            "As soon as a song ends, old \"Now Playing\", \"Paused\", or \"Skipped\" messages will be automatically deleted. You don't need to delete anything manually! 🎧✨"
        ),
        "autoplay": query.lang.get(
            "help_autoplay",
            "<u><b>ᴀᴜᴛᴏᴘʟᴀʏ:</b></u>\n\n<blockquote>Toggle autoplay to automatically enqueue related tracks when the queue ends. Use the settings menu to enable or disable per-chat.</blockquote>",
        ),
        "autoclean_module": (
            "<u><b>ᴀᴜᴛᴏ-ᴄʟᴇᴀɴᴇʀ:</b></u>\n\n"
            "Removes service messages, bot welcome spam, promotional keyboards, "
            "and Telegram links from groups.\n\n"
            "<b>Commands:</b> <code>/autoclean on</code> or <code>/autoclean off</code>"
        ),
        "play": query.lang["help_play"],
        "queue": query.lang["help_queue"],
        "seek": query.lang["help_seek"],
        "assistant": query.lang["help_assistant"],
        "ping": query.lang["help_ping"],
        "stats": query.lang["help_stats"],
        "sudo": query.lang["help_sudo"],
    }

    help_text = help_texts.get(category, query.lang["help_admins"])

    try:
        await query.edit_message_caption(
            caption=help_text,
            reply_markup=buttons.help_markup(query.lang, True),
            parse_mode=enums.ParseMode.HTML,
        )
    except Exception:
        try:
            await query.edit_message_text(
                text=help_text,
                reply_markup=buttons.help_markup(query.lang, True),
                parse_mode=enums.ParseMode.HTML,
            )
        except Exception:
            pass


@app.on_callback_query(filters.regex(r"^playmode$") & ~app.bl_users)
@lang.language()
@admin_check
async def _playmode(_, query: types.CallbackQuery):
    """Handle play mode toggling and update settings markup."""
    await query.answer(query.lang["processing"], show_alert=True)
    chat_id = query.message.chat.id
    admin_only = await db.get_play_mode(chat_id)
    await db.set_play_mode(chat_id, admin_only)
    await query.edit_message_reply_markup(
        reply_markup=buttons.settings_markup(
            query.lang,
            not admin_only,
            await db.get_autoplay(chat_id),
            chat_id,
        )
    )
