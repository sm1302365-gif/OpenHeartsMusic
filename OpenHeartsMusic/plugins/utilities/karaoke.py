# ==============================================================================
# karaoke.py - Karaoke Mode Controls
# ==============================================================================
# Simple karaoke mode toggles for active playback sessions.
# ==============================================================================

from hydrogram import filters, types

from OpenHeartsMusic import app, db, lang, tune
from OpenHeartsMusic.helpers import admin_check

VALID_MODES = {
    "off": "off",
    "standard": "standard",
    "reverb": "reverb",
    "high_pitch": "high_pitch",
    "deep_bass": "deep_bass",
    "studio": "studio",
}


@app.on_message(filters.command(["karaoke", "karaokeon", "karaokeoff", "karaokestudio"]) & filters.group & ~app.bl_users)
@lang.language()
@admin_check
async def karaoke_command(_, message: types.Message):
    chat_id = message.chat.id
    command = message.command[0].lower()

    if not await db.get_call(chat_id):
        return await message.reply_text(
            message.lang["error_no_call"] if "error_no_call" in message.lang else (
                "❌ No active playback in this chat."
            ),
            quote=True,
        )

    requested_mode = message.command[1].lower() if len(message.command) > 1 else "standard"
    if command == "karaokeoff":
        target = "off"
    elif command == "karaokestudio":
        target = "studio"
    elif command == "karaokeon":
        target = "standard"
    else:
        target = VALID_MODES.get(requested_mode)
        if target is None:
            modes = ", ".join(VALID_MODES)
            return await message.reply_text(
                f"❌ Invalid karaoke mode. Choose: {modes}",
                quote=True,
            )

    if not await tune.set_karaoke_mode(chat_id, target):
        return await message.reply_text("❌ Failed to change karaoke mode.", quote=True)

    await message.reply_text(f"✅ Karaoke mode set to: {target}", quote=True)


@app.on_message(filters.command(["normalmode", "normal"]) & filters.group & ~app.bl_users)
@lang.language()
@admin_check
async def normal_mode_command(_, message: types.Message):
    chat_id = message.chat.id
    if not await db.get_call(chat_id):
        return await message.reply_text(
            message.lang["error_no_call"] if "error_no_call" in message.lang else (
                "❌ No active playback in this chat."
            ),
            quote=True,
        )

    if not await tune.set_karaoke_mode(chat_id, "off"):
        return await message.reply_text("❌ Failed to reset karaoke mode.", quote=True)

    await message.reply_text("✅ Normal mode enabled.", quote=True)
