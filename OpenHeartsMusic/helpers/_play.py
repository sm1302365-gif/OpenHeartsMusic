# ==============================================================================
# _play.py - Play Command Validator
# ==============================================================================
# Provides the @checkUB decorator to make sure everything is valid before
# attempting to play a song (checks permissions, queue limits, chat type, etc).
# ==============================================================================

import asyncio

from hydrogram import enums, errors, types

from OpenHeartsMusic import app, config, db, logger, queue, yt
from OpenHeartsMusic.helpers._assistant_invite import ensure_assistant_in_chat

PLAY_USAGE_IMAGE = (
    "https://res.cloudinary.com/dtz0urit6/image/upload/"
    "q_auto:best,f_jpg/cloudinary-tools-uploads/elw78btenpzcwxccjgzv"
)


def is_supported_chat(chat_type: enums.ChatType) -> bool:
    return chat_type in {enums.ChatType.GROUP, enums.ChatType.SUPERGROUP}


def checkUB(play):
    async def wrapper(_, m: types.Message):
        async def safe_reply(text, photo=None):
            # Fallback to prevent crashing if the bot doesn't have message permissions
            try:
                if photo:
                    return await m.reply_photo(photo=photo, caption=text)
                return await m.reply_text(text)
            except errors.ChatWriteForbidden:
                # Chat doesn't allow text messages - silently return
                return None
            except Exception:
                return None

        if not m.from_user:
            await safe_reply(m.lang["play_user_invalid"])
            return

        if not is_supported_chat(m.chat.type):
            await safe_reply(m.lang["play_chat_invalid"])
            return await app.leave_chat(m.chat.id)

        if not m.reply_to_message and (
            len(m.command) < 2 or (len(m.command)
                                   == 2 and m.command[1] == "-f")
        ):
            await safe_reply(m.lang["play_usage"], photo=PLAY_USAGE_IMAGE)
            return

        if len(queue.get_queue(m.chat.id)) >= config.QUEUE_LIMIT:
            await safe_reply(m.lang["play_queue_full"].format(config.QUEUE_LIMIT))
            return

        command = m.command[0].lower()
        force = command.endswith("force") or (
            len(m.command) > 1 and "-f" in m.command[1]
        )

        video_requested = command.startswith("v")
        if video_requested and not await db.get_vplay_enabled():
            await safe_reply(m.lang["play_video_disabled"])
            return
        video = video_requested

        url = yt.url(m)
        # Only validate URL if not replying to media (Telegram files have t.me URLs)
        if url and not m.reply_to_message and not (
            yt.valid(url) or yt.is_external_url(url)
        ):
            return await m.reply_text(m.lang["play_unsupported"])

        play_mode = await db.get_play_mode(m.chat.id)
        if play_mode or force:
            adminlist = await db.get_admins(m.chat.id)
            if (
                m.from_user.id not in adminlist
                and not await db.is_auth(m.chat.id, m.from_user.id)
                and not m.from_user.id in app.sudoers
            ):
                await safe_reply(m.lang["play_admin"])
                return

        if m.chat.id not in db.active_calls:
            try:
                client = await db.get_client(m.chat.id)
            except RuntimeError as error:
                if str(error) != "No assistant sessions are available.":
                    raise
                await safe_reply(
                    "❌ No assistant session is available to play music. "
                    "Configure STRING_SESSION1 and restart the bot."
                )
                return
            if not client:
                await safe_reply(
                    "❌ No assistant session is available to join this chat. Please check your SESSION strings and restart the bot."
                )
                return
            try:
                member = await client.get_chat_member(m.chat.id, client.id)
                if member.status in [
                    enums.ChatMemberStatus.BANNED,
                    enums.ChatMemberStatus.RESTRICTED,
                ]:
                    try:
                        await client.unban_chat_member(
                            chat_id=m.chat.id, user_id=client.id
                        )
                    except:
                        await safe_reply(
                            m.lang["play_banned"].format(
                                app.name,
                                client.id,
                                client.mention,
                                f"@{client.username}" if client.username else None,
                            )
                        )
                        return
            except errors.ChatAdminRequired:
                await safe_reply(
                    f"<blockquote><b>🔐 Bot Admin Required</b></blockquote>\n\n"
                    f"<blockquote>To play music in this chat, I need to be an <b>administrator</b>.\n\n"
                    f"<b>Required permissions:</b>\n"
                    f"• Manage Voice Chats\n"
                    f"• Invite Users via Link\n"
                    f"• Delete Messages\n\n"
                    f"Please promote me as admin with the required permissions.</blockquote>"
                )
                return
            except (
                errors.UserNotParticipant,
                errors.PeerIdInvalid,
                errors.ChannelInvalid,
                errors.ChannelPrivate,
            ):
                umm = await safe_reply(m.lang["play_invite"].format(app.name))
                if umm:
                    await asyncio.sleep(2)

                joined = await ensure_assistant_in_chat(_, client, m.chat.id, logger)
                if not joined:
                    if umm:
                        try:
                            await umm.edit_text(m.lang["play_invite_error"].format("assistant_join_failed"))
                        except Exception:
                            pass
                    return

                if umm:
                    try:
                        await umm.delete()
                    except Exception:
                        pass

                try:
                    await client.resolve_peer(m.chat.id)
                except (
                    errors.ChannelInvalid,
                    errors.PeerIdInvalid,
                    errors.UserNotParticipant,
                    errors.ChannelPrivate,
                ):
                    try:
                        await client.get_chat(m.chat.id)
                    except (
                        errors.ChannelInvalid,
                        errors.PeerIdInvalid,
                        errors.UserNotParticipant,
                        errors.ChannelPrivate,
                    ):
                        pass
                except Exception:
                    pass

        return await play(_, m, force, url, video)

    return wrapper
