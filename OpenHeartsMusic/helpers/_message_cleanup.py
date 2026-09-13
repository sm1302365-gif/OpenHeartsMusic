"""Track playback status messages for cleanup when a song ends."""

from __future__ import annotations

from collections import defaultdict
from typing import DefaultDict


AUTO_DELETE_CACHE: DefaultDict[int, list[int]] = defaultdict(list)


def register_msg_to_delete(chat_id: int, message_id: int) -> None:
    """Register a playback/status message for deletion at track end."""
    if not chat_id or not message_id:
        return
    if message_id not in AUTO_DELETE_CACHE[chat_id]:
        AUTO_DELETE_CACHE[chat_id].append(message_id)


async def auto_clean_track_messages(client, chat_id: int) -> None:
    """Delete all registered playback/status messages for a chat."""
    msg_ids = AUTO_DELETE_CACHE.pop(chat_id, [])
    if not msg_ids:
        return

    try:
        await client.delete_messages(
            chat_id=chat_id,
            message_ids=msg_ids,
            revoke=True,
        )
    except Exception:
        pass
