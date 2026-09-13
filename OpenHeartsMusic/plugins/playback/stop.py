# ==============================================================================
# stop.py - Stop Playback
# ==============================================================================
# Stops the stream and clears the entire active queue.
# ==============================================================================

import asyncio
import logging
from hydrogram import filters, types
from hydrogram.errors import ChatWriteForbidden

from OpenHeartsMusic import tune, app, db, lang
from OpenHeartsMusic.helpers import can_manage_vc

logger = logging.getLogger(__name__)


@app.on_message(filters.command(["end", "stop"]) & filters.group & ~app.bl_users)
@lang.language()
@can_manage_vc
async def _stop(_, m: types.Message):
    if len(m.command) > 1:
        return
    try:
        await m.delete()
    except Exception:
        pass
    if not await db.get_call(m.chat.id):
        try:
            return await m.reply_text(m.lang["not_playing"])
        except ChatWriteForbidden:
            logger.warning("Cannot send text in this chat, skipping reply.")
            return
        except Exception as e:
            logger.error(f"Failed to send reply: {e}")
            return

    await tune.stop(m.chat.id)
    try:
        await m.reply_text(m.lang["play_stopped"].format(m.from_user.mention))
    except ChatWriteForbidden:
        logger.warning("Cannot send text in this chat, stream stopped silently.")
        return
    except Exception as e:
        logger.error(f"Failed to send stop confirmation: {e}")
        return
