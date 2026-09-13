"""
autoplay.py - Autoplay settings
Adds a dedicated autoplay toggle button and handler for chat settings.
"""

from hydrogram import filters, types

from OpenHeartsMusic import app, db, lang
from OpenHeartsMusic.helpers import admin_check, buttons
from OpenHeartsMusic.helpers._autoplay import toggle_autoplay
from OpenHeartsMusic.helpers._message_cleanup import register_msg_to_delete


@app.on_callback_query(filters.regex(r"^autoplay$") & ~app.bl_users)
@lang.language()
@admin_check
async def autoplay_toggle(_, query: types.CallbackQuery):
    await query.answer()
    chat_id = query.message.chat.id
    new_state = await toggle_autoplay(chat_id)

    await query.edit_message_reply_markup(
        reply_markup=buttons.settings_markup(
            query.lang,
            await db.get_play_mode(chat_id),
            new_state,
            chat_id,
        )
    )

    try:
        sent = await query.message.reply_text(
            query.lang["autoplay_enabled"] if new_state else query.lang["autoplay_disabled"],
            quote=False,
        )
        register_msg_to_delete(chat_id, sent.id)
    except Exception:
        pass


@app.on_message(filters.command(["autoplay", "autostream"]) & filters.group & ~app.bl_users)
@lang.language()
@admin_check
async def autoplay_command(_, message: types.Message):
    try:
        await message.delete()
    except Exception:
        pass

    if len(message.command) < 2:
        sent = await message.reply_text(message.lang["autoplay_usage"], quote=True)
        register_msg_to_delete(message.chat.id, sent.id)
        return sent

    action = message.command[1].lower()
    chat_id = message.chat.id

    if action in ["enable", "on"]:
        await db.set_autoplay(chat_id, True)
        sent = await message.reply_text(message.lang["autoplay_enabled"], quote=True)
        register_msg_to_delete(chat_id, sent.id)
        return sent

    if action in ["disable", "off"]:
        await db.set_autoplay(chat_id, False)
        sent = await message.reply_text(message.lang["autoplay_disabled"], quote=True)
        register_msg_to_delete(chat_id, sent.id)
        return sent

    sent = await message.reply_text(message.lang["autoplay_usage"], quote=True)
    register_msg_to_delete(chat_id, sent.id)
    return sent
