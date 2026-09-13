# ==============================================================================
# assistant_join.py - Assistant Join Command
# ==============================================================================
# Adds a group command to invite the configured assistant/userbot into the chat
# when they are not already present.
# ==============================================================================

from hydrogram import filters
from hydrogram.types import Message

from OpenHeartsMusic import app, db, lang, logger
from OpenHeartsMusic.helpers._assistant_invite import ensure_assistant_in_chat


@app.on_message(filters.command(["assistantjoin", "joinassistant"]) & filters.group & ~app.bl_users)
@lang.language()
async def assistant_join(_, m: Message):
    try:
        await m.delete()
    except Exception:
        pass

    if not m.from_user:
        return

    try:
        adminlist = await db.get_admins(m.chat.id)
        if (
            m.from_user.id not in adminlist
            and not await db.is_auth(m.chat.id, m.from_user.id)
            and m.from_user.id not in app.sudoers
        ):
            await m.reply_text(m.lang["user_not_admin"])
            return
    except Exception:
        # If admin check fails, allow the command to continue and try to invite.
        pass

    sent = await m.reply_text(m.lang["assistant_joining"])

    try:
        client = await db.get_client(m.chat.id)
        if not client:
            await sent.edit_text(m.lang["assistant_no_session"])
            return

        joined = await ensure_assistant_in_chat(app, client, m.chat.id, logger)
        if joined:
            await sent.edit_text(m.lang["assistant_join_success"])
        else:
            await sent.edit_text(m.lang["assistant_join_failed"])
    except Exception as e:
        logger.error(f"Assistant join command failed: {e}")
        try:
            await sent.edit_text(m.lang["assistant_join_failed"])
        except Exception:
            pass
