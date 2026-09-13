import re

from hydrogram import filters
from hydrogram.enums import ChatMemberStatus
from hydrogram.types import Message

from OpenHeartsMusic import app, db


WELCOME_KEYWORDS = (
    "welcome",
    "joined the chat",
    "welcome to",
    "nice to meet you",
    "glad to have you",
    "joined group",
)
TELEGRAM_LINK_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.)?(?:t|telegram)\.(?:me|dog)/[a-zA-Z0-9_]+",
    re.IGNORECASE,
)


async def _is_group_admin(client, chat_id: int, user_id: int) -> bool:
    member = await client.get_chat_member(chat_id, user_id)
    return member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)


@app.on_message(filters.command(["autoclean", "botcleaner"]) & filters.group)
async def toggle_autoclean(client, message: Message):
    if not message.from_user or not await _is_group_admin(
        client, message.chat.id, message.from_user.id
    ):
        return await message.reply_text(
            "<b>Access denied:</b> only group administrators can use this command."
        )

    if len(message.command) < 2 or message.command[1].lower() not in ("on", "off"):
        return await message.reply_text(
            "<b>Usage:</b> <code>/autoclean on</code> or <code>/autoclean off</code>"
        )

    enabled = message.command[1].lower() == "on"
    await db.set_cleaner_status(message.chat.id, enabled)
    status = "enabled" if enabled else "disabled"
    await message.reply_text(f"Auto-cleaner <b>{status}</b>.")


@app.on_message(filters.group, group=1)
async def auto_delete_handler(client, message: Message):
    if not await db.is_cleaner_enabled(message.chat.id):
        return

    try:
        if message.service:
            await message.delete()
            return

        text = (message.text or message.caption or "").lower()
        has_telegram_link = bool(TELEGRAM_LINK_PATTERN.search(text))
        sender = message.from_user

        if sender and sender.is_bot and sender.id != client.id:
            if (
                any(keyword in text for keyword in WELCOME_KEYWORDS)
                or has_telegram_link
                or bool(message.reply_markup)
            ):
                await message.delete()
            return

        if sender and not sender.is_bot and has_telegram_link:
            if not await _is_group_admin(client, message.chat.id, sender.id):
                await message.delete()
    except Exception:
        return


