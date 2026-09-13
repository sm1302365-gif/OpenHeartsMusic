# ==============================================================================
# queue.py - Now Playing & Queue
# ==============================================================================
# Displays the currently playing track and upcoming queue list.
# ==============================================================================

from hydrogram import filters, types

from OpenHeartsMusic import app, config, db, lang, queue
from OpenHeartsMusic.helpers import Track, buttons, thumb, get_now_playing_markup
from OpenHeartsMusic.helpers._thumbnails import (
    build_now_playing_caption,
)


@app.on_message(filters.command(["queue", "playing"]) & filters.group & ~app.bl_users)
@lang.language()
async def _queue_func(_, m: types.Message):
    if not await db.get_call(m.chat.id):
        return await m.reply_text(m.lang["not_playing"])

    _reply = await m.reply_text(m.lang["queue_fetching"])
    _queue = queue.get_queue(m.chat.id)
    _media = _queue[0]
    _thumb = (
        await thumb.generate(_media)
        if isinstance(_media, Track)
        else config.DEFAULT_THUMB
    )
    caption = build_now_playing_caption(
        _media,
        m.from_user.first_name if m.from_user else "Admin",
    )
    _queue.pop(0)

    if _queue:
        caption += "\n\n🔗 Upcoming Queue:\n"
        for i, media in enumerate(_queue, start=1):
            if i == 8:
                break
            caption += f"{i}. {media.title}\n"

    reply_markup = await get_now_playing_markup(chat_id=m.chat.id)
    await _reply.edit_media(
        media=types.InputMediaPhoto(
            media=_thumb,
            caption=caption,
        ),
        reply_markup=reply_markup,
    )
