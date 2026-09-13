# ==============================================================================
# local_karaoke.py - Local MP3 Karaoke Playback
# ==============================================================================
# Streams a local MP3 file directly to the voice chat with karaoke support.
# ==============================================================================

import os

from hydrogram import filters, types

from OpenHeartsMusic import app, lang, tune
from OpenHeartsMusic.helpers import admin_check


@app.on_message(filters.command(["localkaraoke", "local_karaoke"]) & filters.group & ~app.bl_users)
@lang.language()
@admin_check
async def local_karaoke_command(_, message: types.Message):
    if len(message.command) < 2:
        return await message.reply_text(
            "Usage: /localkaraoke <absolute_path> [title]",
            quote=True,
        )

    file_path = message.command[1]
    title = " ".join(message.command[2:]) or os.path.basename(file_path)

    if not os.path.exists(file_path):
        return await message.reply_text(f"❌ File not found: {file_path}", quote=True)

    if not os.path.isfile(file_path):
        return await message.reply_text(f"❌ Not a valid file: {file_path}", quote=True)

    success = await tune.stream_local_mp3(
        chat_id=message.chat.id,
        file_path=file_path,
        title=title,
        requester=getattr(message.from_user, 'first_name', 'User'),
        message=message,
    )

    if not success:
        await message.reply_text("❌ Unable to stream local karaoke file.", quote=True)
