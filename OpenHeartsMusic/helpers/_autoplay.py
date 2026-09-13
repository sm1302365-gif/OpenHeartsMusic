# ==============================================================================
# _autoplay.py - Autoplay helpers
# ==============================================================================
# Shared helpers for reading and toggling autoplay state per chat.
# ==============================================================================

from OpenHeartsMusic import db


async def get_autoplay_state(chat_id: int) -> bool:
    return await db.get_autoplay(chat_id)


async def toggle_autoplay(chat_id: int) -> bool:
    enabled = await db.get_autoplay(chat_id)
    await db.set_autoplay(chat_id, not enabled)
    return not enabled
