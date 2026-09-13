# ==============================================================================
# fx.py - Audio Effect Controls
# ==============================================================================
# Provides quick audio-effect toggles for active playback in the current chat.
# ==============================================================================

from hydrogram import filters, types

from OpenHeartsMusic import app, db, lang, tune
from OpenHeartsMusic.helpers import admin_check

VALID_EFFECTS = {
    "none": "none",
    "bassboost": "bassboost",
    "deepbass": "deep_bass",
    "deep_bass": "deep_bass",
    "8d": "8d",
    "nightcore": "nightcore",
    "lofi": "lofi",
    "studio": "studio",
    "karaoke": "karaoke",
}


@app.on_message(filters.command(["fx", "effect"]) & filters.group & ~app.bl_users)
@lang.language()
@admin_check
async def fx_command(_, message: types.Message):
    if len(message.command) < 2:
        return await message.reply_text(
            message.lang["fx_usage"] if "fx_usage" in message.lang else (
                "Usage: /fx <none|bassboost|deepbass|8d|nightcore|lofi|karaoke|studio>"
            ),
            quote=True,
        )

    effect_name = message.command[1].lower()
    effect_key = VALID_EFFECTS.get(effect_name)
    if effect_key is None:
        return await message.reply_text(
            message.lang["fx_invalid"] if "fx_invalid" in message.lang else (
                "❌ Invalid effect. Choose: none, bassboost, deepbass, 8d, nightcore, lofi, karaoke, studio"
            ),
            quote=True,
        )

    chat_id = message.chat.id
    if not await db.get_call(chat_id):
        return await message.reply_text(
            message.lang["error_no_call"] if "error_no_call" in message.lang else (
                "❌ No active playback in this chat."
            ),
            quote=True,
        )

    if effect_name == "none":
        tune._audio_fx.pop(chat_id, None)
        await tune.set_audio_fx(chat_id, "none")
        return await message.reply_text("✅ Audio effect cleared.", quote=True)

    if not await tune.set_audio_fx(chat_id, effect_key):
        return await message.reply_text("❌ Failed to apply effect.", quote=True)

    await message.reply_text(f"✅ Applied audio effect: {effect_name}", quote=True)
