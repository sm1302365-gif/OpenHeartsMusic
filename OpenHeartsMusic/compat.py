import asyncio
import logging
import os
import shutil
import sqlite3
from pathlib import Path
from typing import Any

logger = logging.getLogger("OpenHeartsMusic")


def install_hydrogram_error_aliases() -> None:
    """Bridge Hydrogram's legacy RPC error names to its current classes."""
    try:
        import hydrogram.errors as hydrogram_errors
        from hydrogram.errors import BadRequest
    except Exception:
        return

    if not hasattr(hydrogram_errors, "GroupcallInvalid") and hasattr(hydrogram_errors, "GroupCallInvalid"):
        hydrogram_errors.GroupcallInvalid = hydrogram_errors.GroupCallInvalid

    if not hasattr(hydrogram_errors, "GroupcallForbidden"):
        groupcall_forbidden = type(
            "GroupcallForbidden",
            (BadRequest,),
            {
                "ID": "GROUPCALL_FORBIDDEN",
                "MESSAGE": "The group call is forbidden",
                "__module__": "hydrogram.errors",
            },
        )
        setattr(hydrogram_errors, "GroupcallForbidden", groupcall_forbidden)


def install_hydrogram_channel_compat_patch() -> None:
    """Avoid crashes when Telegram sends channel metadata for inaccessible or forbidden channels."""
    try:
        import hydrogram.types.user_and_chats.chat as chat_module
        from hydrogram import enums, types
        from hydrogram.types.user_and_chats import chat as chat_types
        from hydrogram import utils
    except Exception:
        return

    if getattr(chat_module.Chat._parse_channel_chat, "__name__", "") == "_parse_channel_chat_compat":
        return

    original = chat_module.Chat._parse_channel_chat

    def _parse_channel_chat_compat(client, channel):
        peer_id = getattr(channel, "id", None)
        if peer_id is None:
            return None

        try:
            return original(client, channel)
        except AttributeError:
            pass

        access_hash = getattr(channel, "access_hash", 0)
        peer_id = utils.get_channel_id(peer_id)

        return chat_types.Chat(
            id=peer_id,
            type=enums.ChatType.SUPERGROUP if getattr(channel, "megagroup", False) else enums.ChatType.CHANNEL,
            is_verified=getattr(channel, "verified", None),
            is_restricted=getattr(channel, "restricted", None),
            is_creator=getattr(channel, "creator", None),
            is_scam=getattr(channel, "scam", None),
            is_fake=getattr(channel, "fake", None),
            is_forum=getattr(channel, "forum", None),
            title=getattr(channel, "title", None),
            username=getattr(channel, "username", None),
            photo=types.ChatPhoto._parse(client, getattr(channel, "photo", None), peer_id, access_hash),
            restrictions=types.List([
                types.Restriction._parse(r) for r in getattr(channel, "restriction_reason", [])
            ]) or None,
            permissions=types.ChatPermissions._parse(getattr(channel, "default_banned_rights", None)),
            members_count=getattr(channel, "participants_count", None),
            dc_id=getattr(getattr(channel, "photo", None), "dc_id", None),
            has_protected_content=getattr(channel, "noforwards", None),
            usernames=types.List([
                types.Username._parse(r) for r in getattr(channel, "usernames", [])
            ]) or None,
            client=client,
        )

    chat_module.Chat._parse_channel_chat = staticmethod(_parse_channel_chat_compat)


def _get_channel_invalid():
    try:
        from hydrogram.errors import ChannelInvalid
        return ChannelInvalid
    except Exception:
        return None


def is_session_lock_error(exc: BaseException | None) -> bool:
    if exc is None:
        return False

    message = str(exc).lower()
    return (
        "database is locked" in message
        or "database is busy" in message
        or "locked" in message and "sqlite" in message
        or "operationalerror" in message and "locked" in message
    )


def should_ignore_asyncio_exception(exc: BaseException) -> bool:
    if exc is None:
        return False

    ChannelInvalid = _get_channel_invalid()
    if ChannelInvalid is not None and isinstance(exc, ChannelInvalid):
        return True

    message = str(exc)
    return (
        "Peer id invalid" in message
        or "ID not found" in message
        or "Cannot parse input peer" in message
        or is_session_lock_error(exc)
    )


def install_asyncio_exception_handler() -> None:
    def _handler(loop: asyncio.AbstractEventLoop, context: dict[str, Any]) -> None:
        exc = context.get("exception")
        if should_ignore_asyncio_exception(exc):
            logger.warning("Ignoring transient Telegram peer update error: %s", exc)
            return
        loop.default_exception_handler(context)

    asyncio.get_event_loop().set_exception_handler(_handler)


def recover_hydrogram_session(session_dir: str | os.PathLike[str] | None = None) -> bool:
    if session_dir is None:
        session_dir = Path.cwd()

    session_path = Path(session_dir)
    if not session_path.exists():
        return False

    candidates = [
        session_path / "OpenHeartsMusic.session",
        session_path / "OpenHeartsMusic.session-journal",
        session_path / "OpenHeartsMusic.session-shm",
        session_path / "OpenHeartsMusic.session-wal",
    ]

    removed = []
    for candidate in candidates:
        if candidate.exists():
            try:
                if candidate.is_dir():
                    shutil.rmtree(candidate)
                else:
                    candidate.unlink()
                removed.append(str(candidate))
            except Exception as exc:
                logger.warning("Could not remove stale Hydrogram session file %s: %s", candidate, exc)

    if removed:
        logger.warning("Removed stale Hydrogram session files: %s", ", ".join(removed))
        return True

    return False
