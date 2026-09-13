# ==============================================================================
# active.py - Active Calls
# ==============================================================================
# Quick command to see how many voice chats the bot is currently playing in.
# ==============================================================================

import os
from hydrogram import filters, types
from OpenHeartsMusic import app, db, lang, queue


@app.on_message(filters.command(["ac"]) & app.sudo_filter)
@lang.language()
async def _ac(_, m: types.Message):
    if not db.active_calls:
        return await m.reply_text(m.lang["vc_empty"])

    return await m.reply_text(m.lang["vc_count"].format(len(db.active_calls)))

