# ==============================================================================
# resume.py - Resume Command
# ==============================================================================
# /resume command to unpause playback in the voice chat.
# ==============================================================================

import logging
from hydrogram import filters, types
from hydrogram.errors import ChatWriteForbidden

from OpenHeartsMusic import tune, app, db, lang
from OpenHeartsMusic.helpers import buttons, can_manage_vc
from OpenHeartsMusic.helpers._message_cleanup import register_msg_to_delete

logger = logging.getLogger(__name__)


@app.on_message(filters.command(["resume"]) & filters.group & ~app.bl_users)
@lang.language()
@can_manage_vc
async def _resume(_, m: types.Message):
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

    if await db.playing(m.chat.id):
        try:
            sent = await m.reply_text(m.lang["play_not_paused"])
            register_msg_to_delete(m.chat.id, sent.id)
            return sent
        except ChatWriteForbidden:
            return

    await tune.resume(m.chat.id)
    try:
        sent = await m.reply_text(
            text=m.lang["play_resumed"].format(m.from_user.mention),
            reply_markup=buttons.controls(m.chat.id),
        )
        register_msg_to_delete(m.chat.id, sent.id)
    except ChatWriteForbidden:
        logger.warning("Cannot send text in media-only chat")
