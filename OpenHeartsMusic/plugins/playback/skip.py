# ==============================================================================
# skip.py - Skip Track
# ==============================================================================
# Skips the current track and automatically starts the next one in queue.
# ==============================================================================

import asyncio
import logging
from hydrogram import filters, types
from hydrogram.errors import ChatWriteForbidden

from OpenHeartsMusic import tune, app, db, lang
from OpenHeartsMusic.helpers import can_manage_vc
from OpenHeartsMusic.helpers._message_cleanup import register_msg_to_delete

logger = logging.getLogger(__name__)


@app.on_message(filters.command(["skip", "next"]) & filters.group & ~app.bl_users)
@lang.language()
@can_manage_vc
async def _skip(_, m: types.Message):
    try:
        await m.delete()
    except Exception:
        pass

    if not await db.get_call(m.chat.id):
        try:
            sent = await m.reply_text(m.lang["not_playing"])
            register_msg_to_delete(m.chat.id, sent.id)
            return sent
        except ChatWriteForbidden:
            return

    await tune.play_next(m.chat.id)
    try:
        sent = await m.reply_text(m.lang["play_skipped"].format(m.from_user.mention))
        register_msg_to_delete(m.chat.id, sent.id)
    except ChatWriteForbidden:
        logger.warning("Cannot send plain text in media-only chat")
        return
