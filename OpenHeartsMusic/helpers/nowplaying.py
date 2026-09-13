import os

from hydrogram import Client, enums, filters
from hydrogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from OpenHeartsMusic import app, db, queue
from OpenHeartsMusic.helpers import Thumbnail, build_now_playing_caption, get_now_playing_markup
from OpenHeartsMusic.helpers.style import CustomFonts
from OpenHeartsMusic.helpers._inline import InlineKeyboardButton


thumb_gen = Thumbnail()


def format_time(value: int | float, fallback: str = "00:00") -> str:
    """Format seconds into MM:SS format"""
    if isinstance(value, (int, float)):
        seconds = max(0, int(value))
        minutes, seconds = divmod(seconds, 60)
        return f"{minutes:02d}:{seconds:02d}"
    elif value is None:
        return fallback
    else:
        return str(value)


@app.on_message(
    filters.command(["np", "nowplaying"]) & filters.group & ~app.bl_users
)
async def now_playing_handler(client: Client, message: Message):
    """Handle now playing command"""
    chat = getattr(message, "chat", None)
    chat_id = getattr(message, "chat_id", None) or getattr(chat, "id", None)

    if not chat_id:
        await message.reply_text("❌ This command can only be used in a chat.")
        return

    if not await db.get_call(chat_id):
        await message.reply_text("❌ No active stream playing right now!")
        return

    if not await db.playing(chat_id):
        await message.reply_text("❌ No active stream playing right now!")
        return

    song = queue.get_current(chat_id)

    if not song:
        await message.reply_text("❌ No active stream playing right now!")
        return

    status_message = await message.reply_text("🔍 Fetching details...")

    try:
        photo_path = await thumb_gen.generate(song)

        requester = (
            message.from_user.first_name
            if getattr(message, "from_user", None)
            else "User"
        )

        duration = format_time(getattr(song, "duration", "00:00"))
        current_time = format_time(getattr(song, "time", 0))
        caption = build_now_playing_caption(song, requester)

        bot_info = await client.get_me()

        buttons = await get_now_playing_markup(
            chat_id=chat_id,
            bot_username=bot_info.username or "OpenHeartsMusicBot",
            current_time=current_time,
            total_time=duration,
        )

        if photo_path and os.path.exists(photo_path):
            await message.reply_photo(
                photo_path,
                caption=caption,
                reply_markup=buttons,
                parse_mode=enums.ParseMode.HTML,
            )
        else:
            await message.reply_text(
                caption,
                reply_markup=buttons,
                parse_mode=enums.ParseMode.HTML,
            )

        if status_message:
            await status_message.delete()

    except Exception as error:
        if status_message:
            await status_message.edit_text(f"❌ An error occurred: {error}")


@app.on_message(filters.command(["np", "nowplaying"]) & filters.group & ~app.bl_users)
async def send_playing_panel(
    client: Client, chat_id: int, song_name: str, mode: str = "normal"
):
    """Send now playing panel to chat"""
    mode_map = {"karaoke": "Karaoke", "studio": "Studio"}
    title = mode_map.get(mode.lower(), "Now Playing")

    panel_text = f"<b>🎶 {title}</b>\n\n<b>🎵 Track:</b> <code>{song_name}</code>"

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    text=CustomFonts.PLAYING_STUDIO,
                    callback_data="player_studio",
                    style="primary",
                )
            ]
        ]
    )

    await client.send_message(
        chat_id,
        panel_text,
        reply_markup=keyboard,
        parse_mode=enums.ParseMode.HTML,
    )


@app.on_callback_query(filters.regex("^player_studio$"))
async def player_studio_handler(client: Client, callback_query: CallbackQuery):
    """Handle player studio button callback"""
    if not callback_query or not callback_query.message:
        return

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    text="🔄 Refresh",
                    callback_data="player_studio",
                    style="primary",
                )
            ]
        ]
    )

    await callback_query.message.edit_text(
        "<b>Studio</b>\n\n🎧 <i>Switched to Studio Mode!</i>\n\nEnjoy premium audio quality.",
        reply_markup=keyboard,
        parse_mode=enums.ParseMode.HTML,
    )

    await callback_query.answer(
        "🎧 Studio mode activated!",
        show_alert=False,
    )
