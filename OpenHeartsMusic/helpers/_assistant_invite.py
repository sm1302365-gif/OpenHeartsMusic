import asyncio
from typing import Any

from hydrogram import errors


def _unwrap_assistant_client(assistant_client: Any) -> Any:
    """Return the actual Hydrogram client used by a PyTgCalls wrapper."""
    if assistant_client is None:
        return None

    mtproto_client = getattr(assistant_client, "mtproto_client", None)
    if mtproto_client is not None and hasattr(mtproto_client, "get_chat_member"):
        return mtproto_client

    if hasattr(assistant_client, "get_chat_member"):
        return assistant_client

    return None


def _is_channel_private_state(exc: Exception) -> bool:
    """Telegram may respond with CHANNEL_PRIVATE either as a Hydrogram RPCError or a plain exception."""
    code = getattr(exc, "code", None)
    message = str(exc).upper()
    if code in (400, 406) and "CHANNEL_PRIVATE" in message:
        return True
    if "CHANNEL_PRIVATE" in message and "406" in message:
        return True
    return "CHANNEL_PRIVATE" in message and "GETPARTICIPANT" in message


async def ensure_assistant_in_chat(app_client: Any, assistant_client: Any, chat_id: int, logger: Any) -> bool:
    """Ensure an assistant client is in a chat by joining via invite link when needed."""
    real_client = _unwrap_assistant_client(assistant_client)
    if real_client is None:
        logger.warning(f"Assistant client for chat {chat_id} does not expose a Hydrogram client API.")
        return False

    try:
        await real_client.get_chat_member(chat_id, real_client.id)
        return True
    except errors.UserNotParticipant:
        pass
    except (errors.ChannelInvalid, errors.PeerIdInvalid):
        # The assistant may not know this chat yet, or the peer cannot be resolved.
        pass
    except errors.RPCError as exc:
        if _is_channel_private_state(exc):
            pass
        else:
            logger.warning(f"Unable to verify assistant membership: {exc}")
            return False
    except Exception as exc:
        if _is_channel_private_state(exc):
            pass
        else:
            logger.warning(f"Unable to verify assistant membership: {exc}")
            return False

    async def get_invite_link(force_refresh: bool = False) -> str | None:
        try:
            if force_refresh:
                return await app_client.export_chat_invite_link(chat_id)

            chat = await app_client.get_chat(chat_id)
            invite_link = getattr(chat, "invite_link", None)
            if invite_link:
                return invite_link
            return await app_client.export_chat_invite_link(chat_id)
        except errors.ChatAdminRequired:
            logger.warning("Bot lacks admin permission to export an invite link for assistant join")
            return None
        except Exception as exc:
            logger.warning(f"Unable to obtain invite link for assistant join: {exc}")
            return None

    invite_link = await get_invite_link()
    if not invite_link:
        logger.warning("No invite link available to add assistant to chat")
        return False

    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            await real_client.join_chat(invite_link)
            await asyncio.sleep(1)
            try:
                await real_client.get_chat_member(chat_id, real_client.id)
                return True
            except errors.UserNotParticipant:
                pass
            except (errors.ChannelInvalid, errors.PeerIdInvalid):
                pass
            except errors.RPCError as exc:
                if _is_channel_private_state(exc):
                    pass
                else:
                    raise
            except Exception as exc:
                if _is_channel_private_state(exc):
                    pass
                else:
                    raise
            return True
        except errors.UserAlreadyParticipant:
            return True
        except errors.InviteRequestSent:
            return True
        except Exception as exc:
            last_exc = exc
            refreshed_link = await get_invite_link(force_refresh=True)
            if attempt == 0 and refreshed_link and refreshed_link != invite_link:
                invite_link = refreshed_link
                continue
            logger.warning(f"Assistant join failed: {exc}")
            return False

    if last_exc:
        logger.warning(f"Assistant join failed after retry: {last_exc}")
    return False
