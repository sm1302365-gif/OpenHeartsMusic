# ==============================================================================
# _utilities.py - Utils
# ==============================================================================
# Grab bag of helper functions: time formatting, user extraction, safe sending.
# ==============================================================================

import re
from hydrogram import enums, errors, types
from OpenHeartsMusic import app, config


class Utilities:
    def __init__(self):
        pass

    def format_eta(self, seconds: int) -> str:
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            return f"{seconds // 60}:{seconds % 60:02d} min"
        else:
            h = seconds // 3600
            m = (seconds % 3600) // 60
            s = seconds % 60
            return f"{h}:{m:02d}:{s:02d} h"

    def format_size(self, bytes: int) -> str:
        if bytes >= 1024**3:
            return f"{bytes / 1024 ** 3:.2f} GB"
        elif bytes >= 1024**2:
            return f"{bytes / 1024 ** 2:.2f} MB"
        else:
            return f"{bytes / 1024:.2f} KB"

    def format_duration(self, seconds: int) -> str:
        if seconds >= 3600:  # 1 hour or more
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            secs = seconds % 60
            return f"{hours}:{minutes:02d}:{secs:02d}"
        else:  # Less than 1 hour
            minutes = seconds // 60
            secs = seconds % 60
            return f"{minutes:02d}:{secs:02d}"

    def to_seconds(self, time: str) -> int:
        parts = [int(p) for p in time.strip().split(":")]
        return sum(value * 60**i for i, value in enumerate(reversed(parts)))

    async def extract_user(self, msg: types.Message) -> types.User | None:
        if msg.reply_to_message:
            return msg.reply_to_message.from_user

        if msg.entities:
            for e in msg.entities:
                if e.type == enums.MessageEntityType.TEXT_MENTION:
                    return e.user

        if msg.text:
            try:
                if m := re.search(r"@(\w{5,32})", msg.text):
                    return await app.get_users(m.group(0))
                if m := re.search(r"\b\d{6,15}\b", msg.text):
                    return await app.get_users(int(m.group(0)))
            except:
                pass

        return None

    async def play_log(
        self,
        m: types.Message,
        title: str,
        duration: str,
    ) -> None:
        if m.chat.id == app.logger:
            return

        template = m.lang.get("play_log") if hasattr(m, "lang") and isinstance(m.lang, dict) else None
        if not template:
            template = (
                "<blockquote><u><b>🎵 Playing in {0}</b></u>\n\n"
                "<b>Chat:</b> {1} | {2}\n"
                "<b>User:</b> {4} | {3}\n"
                "<b>Title:</b> {6}\n"
                "<b>Duration:</b> {7}\n"
                "<b>Link:</b> <a href='{5}'>Open</a></blockquote>"
            )

        user_id = m.from_user.id if m.from_user else 0
        user_mention = m.from_user.mention if m.from_user else "Unknown"

        kwargs = {
            "app_name": app.name,
            "chat_id": m.chat.id,
            "chat_title": m.chat.title,
            "user_id": user_id,
            "user_mention": user_mention,
            "requester_name": user_mention,
            "link": m.link,
            "song_title": title,
            "song_dur": duration,
        }

        try:
            _text = template.format(**kwargs)
        except (IndexError, KeyError, ValueError):
            _text = template.format(
                app.name,
                m.chat.id,
                m.chat.title,
                user_id,
                user_mention,
                m.link,
                title,
                duration,
            )
        await app.send_message(chat_id=app.logger, text=_text)

    async def send_log(self, m: types.Message) -> None:
        # Avoid attempting to resolve phone-number-like logger IDs (causes contacts.ResolvePhone errors)
        try:
            logger_id = app.logger
            if isinstance(logger_id, str) and re.fullmatch(r"\+?\d+", logger_id):
                # Skip sending log to a phone number — bots cannot resolve phones.
                return
            await app.send_message(
                chat_id=logger_id,
                text=m.lang["log_user"].format(
                    m.from_user.id,
                    f"@{m.from_user.username}",
                    m.from_user.mention,
                ),
            )
        except Exception:
            # Swallow any errors sending logs to avoid interrupting main flow
            return

    async def chat_log(self, m: types.Message) -> None:
        try:
            logger_id = app.logger
            if isinstance(logger_id, str) and re.fullmatch(r"\+?\d+", logger_id):
                return
            if m.chat.id == app.logger:
                return

            user_id = m.from_user.id if m.from_user else 0
            user_mention = m.from_user.mention if m.from_user else "Unknown"
            await app.send_message(
                chat_id=logger_id,
                text=m.lang["log_chat"].format(
                    m.chat.id,
                    m.chat.title or "Unknown chat",
                    user_id,
                    user_mention,
                ),
            )
        except Exception:
            return

    async def safe_text(
        self,
        message: types.Message,
        text: str,
        *,
        reply_markup=None,
        quote: bool | None = True,
    ) -> types.Message | None:
        if not message:
            return None
        try:
            return await message.reply_text(
                text=text,
                reply_markup=reply_markup,
                quote=quote,
            )
        except errors.ChatWriteForbidden:
            fallback_photo = getattr(config, "START_IMG", None)
            if not fallback_photo:
                return None
            try:
                return await message.reply_photo(
                    photo=fallback_photo,
                    caption=text,
                    reply_markup=reply_markup,
                    quote=quote,
                )
            except errors.RPCError:
                return None
        except errors.RPCError:
            return None

    async def safe_edit(
        self,
        message: types.Message | None,
        text: str,
        *,
        reply_markup=None,
    ) -> bool:
        if not message:
            return False
        try:
            if message.text is not None:
                await message.edit_text(text=text, reply_markup=reply_markup)
            else:
                await message.edit_caption(caption=text, reply_markup=reply_markup)
            return True
        except errors.RPCError:
            return False
