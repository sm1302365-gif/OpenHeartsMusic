import asyncio
import html
import re
from urllib.parse import quote

import aiohttp
from hydrogram import filters, types

from OpenHeartsMusic import app, db, logger, queue


_LYRIC_TASKS: dict[int, asyncio.Task] = {}
_LRC_LINE = re.compile(r"^\[(\d+):(\d{2}(?:\.\d{1,3})?)\](.*)$")


async def get_synced_lyrics(artist: str, title: str) -> list[tuple[float, str]]:
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36 Edg/151.0.0.0"}
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(
                "https://lrclib.net/api/get",
                params={"artist_name": artist, "track_name": title},
                timeout=aiohttp.ClientTimeout(total=10),
                headers=headers,
            ) as response:
                if response.status != 200:
                    return []
                payload = await response.json()
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
        logger.debug(f"Failed to fetch synced lyrics: {exc}")
        return []

    synced_lrc = payload.get("syncedLyrics")
    if not synced_lrc:
        return []

    parsed = []
    for line in synced_lrc.splitlines():
        match = _LRC_LINE.match(line.strip())
        if not match:
            continue
        text = match.group(3).strip()
        if text:
            parsed.append((int(match.group(1)) * 60 + float(match.group(2)), text))
    return sorted(parsed)


async def get_unsynced_lyrics(artist: str, title: str) -> list[str]:
    """Fetch fallback lyrics text when synced lyrics are unavailable."""
    query = quote(f"{artist} {title}")
    url = f"https://api.lyrics.ovh/v1/{quote(artist)}/{quote(title)}"

    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36 Edg/151.0.0.0"}
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=10),
                headers=headers,
            ) as response:
                if response.status != 200:
                    return []
                payload = await response.json()
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
        logger.debug(f"Failed to fetch unsynced lyrics: {exc}")
        return []

    text = payload.get("lyrics") or ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[:25]  # Limit to avoid overly long messages


async def fetch_lyrics(song_title: str) -> str:
    """Try to fetch lyrics for a song title, using simple title parsing heuristics."""
    artist = ""
    title = song_title.strip()

    if " - " in song_title:
        artist, title = [part.strip() for part in song_title.split(" - ", 1)]
    elif " by " in song_title.lower():
        parts = song_title.rsplit(" by ", 1)
        if len(parts) == 2:
            title, artist = parts[0].strip(), parts[1].strip()

    if not title:
        return ""

    try:
        lyrics = await get_unsynced_lyrics(artist, title)
        if lyrics:
            return "\n".join(lyrics)
    except Exception as exc:
        logger.debug(f"fetch_lyrics failed for '{song_title}': {exc}")

    return ""


async def send_auto_lyrics(client, chat_id, song_title):
    """Automatically fetches and sends song lyrics when a track starts."""
    try:
        lyrics_text = await fetch_lyrics(song_title)
        if not lyrics_text:
            return

        if len(lyrics_text) > 4000:
            lyrics_text = lyrics_text[:4000] + "\n\n...[Text Truncated due to length]..."

        await client.send_message(
            chat_id,
            f"🎶 **Auto Lyrics for:** `{song_title}`\n\n{lyrics_text}",
        )
    except Exception as exc:
        logger.debug(f"Error in auto lyrics: {exc}")


async def _wait_for_position(chat_id: int, media_id: str, timestamp: float):
    while True:
        if not await db.get_call(chat_id):
            return None
        media = queue.get_current(chat_id)
        if not media or media.id != media_id:
            return None
        if not await db.playing(chat_id):
            await asyncio.sleep(1)
            continue

        remaining = timestamp - getattr(media, "time", 0)
        if remaining <= 0:
            return media
        await asyncio.sleep(min(max(remaining, 0.2), 1))


async def start_lyrics_sync(client, chat_id: int, artist: str, title: str):
    lyrics = await get_synced_lyrics(artist, title)
    if not lyrics:
        # Fallback to unsynced lyrics if synced lyrics are unavailable.
        await client.send_message(
            chat_id,
            f"<b>No synced lyrics found. Showing lyrics instead for</b> <code>{html.escape(title)}</code>",
        )
        await start_unsynced_lyrics(client, chat_id, artist, title)
        return

    media = queue.get_current(chat_id)
    if not media:
        return
    media_id = media.id
    message = await client.send_message(
        chat_id,
        f"<b>Karaoke lyrics:</b> <code>{html.escape(title)}</code>\n\nSyncing...",
    )

    try:
        for index, (timestamp, line_text) in enumerate(lyrics):
            if await _wait_for_position(chat_id, media_id, timestamp) is None:
                return

            previous = lyrics[index - 1][1] if index else ""
            following = lyrics[index + 1][1] if index + 1 < len(lyrics) else ""
            formatted = (
                f"<b>Now playing:</b> <code>{html.escape(title)}</code>\n"
                "━━━━━━━━ 🎙️ ━━━━━━━━\n\n"
                f"<i>{html.escape(previous)}</i>\n"
                f"<b>» {html.escape(line_text)} «</b>\n"
                f"<i>{html.escape(following)}</i>\n\n"
                "━━━━━━━━ 🎙️ ━━━━━━━━"
            )
            try:
                await message.edit_text(formatted)
            except Exception:
                pass
    except asyncio.CancelledError:
        raise


async def start_unsynced_lyrics(client, chat_id: int, artist: str, title: str):
    lyrics = await get_unsynced_lyrics(artist, title)
    if not lyrics:
        await client.send_message(
            chat_id,
            f"<b>No lyrics found for</b> <code>{html.escape(title)}</code>",
        )
        return

    text = (
        f"<b>Lyrics for</b> <code>{html.escape(title)}</code>\n\n"
        + "\n".join(html.escape(line) for line in lyrics)
    )
    await client.send_message(chat_id, text)


def _cancel_lyrics(chat_id: int) -> None:
    task = _LYRIC_TASKS.pop(chat_id, None)
    if task and not task.done():
        task.cancel()


def _parse_lyrics_query(argument: str) -> tuple[str, str]:
    artist, separator, title = argument.partition(" - ")
    if separator:
        return artist.strip(), title.strip()
    artist, separator, title = argument.partition("-")
    return artist.strip(), title.strip()


@app.on_message(filters.command("lyrics") & filters.group & ~app.bl_users)
async def live_lyrics_command(client, message: types.Message):
    if len(message.command) < 2:
        return await message.reply_text(
            "<b>Usage:</b> <code>/lyrics Artist - Song Title</code>"
        )

    argument = message.text.split(None, 1)[1].strip()
    artist, title = _parse_lyrics_query(argument)
    if not title:
        return await message.reply_text(
            "<b>Usage:</b> <code>/lyrics Artist - Song Title</code>"
        )

    chat_id = message.chat.id
    media = queue.get_current(chat_id)

    _cancel_lyrics(chat_id)
    if media:
        task = asyncio.create_task(
            start_lyrics_sync(client, chat_id, artist, title)
        )
    else:
        task = asyncio.create_task(
            start_unsynced_lyrics(client, chat_id, artist, title)
        )

    _LYRIC_TASKS[chat_id] = task
    task.add_done_callback(lambda t: None if t.cancelled() else t.exception())
    task.add_done_callback(lambda _: _LYRIC_TASKS.pop(chat_id, None))


async def stop_lyrics_tasks() -> None:
    tasks = list(_LYRIC_TASKS.values())
    _LYRIC_TASKS.clear()
    for task in tasks:
        if not task.done():
            task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
