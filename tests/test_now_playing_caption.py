import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from OpenHeartsMusic import app, queue
from OpenHeartsMusic.helpers._thumbnails import (
    build_now_playing_buttons,
    build_now_playing_caption,
    build_welcome_caption,
    make_timeline,
)
from OpenHeartsMusic.helpers._utilities import Utilities


def test_now_playing_caption_is_safe_for_group_messages():
    caption = build_now_playing_caption({"title": "Song & More_1", "duration": "03:05"}, "<a href='tg://user?id=8328437815'>Alice</a>")

    assert "LIVE NOW" in caption.upper()
    assert "TITLE" in caption.upper()
    assert "Alice" in caption
    assert "tg://user?id=" not in caption
    assert "**" not in caption
    assert "<b>" in caption


def test_make_timeline_has_no_square_brackets():
    bar = make_timeline("01:00", "04:00")

    assert "[" not in bar
    assert "]" not in bar


def test_now_playing_caption_removes_raw_tg_user_links():
    caption = build_now_playing_caption({"title": "Song", "duration": "03:05"}, "tg://user?id=8328437815")

    assert "tg://user?id=" not in caption
    assert "User" in caption


def test_now_playing_caption_uses_ascii_safe_group_text():
    caption = build_now_playing_caption({"title": "Song & More_1", "duration": "03:05"}, "Alice")

    assert "LIVE NOW" in caption.upper()
    assert "❖" not in caption
    assert "❍" not in caption
    assert "➥" not in caption
    assert "<b>" in caption
    assert caption == "<b>LIVE NOW</b>\n\n<b>TITLE</b> -> Song &amp; More_1\n<b>TIME</b> -> 03:05\n<b>BY</b> -> Alice"


def test_now_playing_caption_template_is_localized():
    with open("OpenHeartsMusic/locales/en.json", encoding="utf-8") as f:
        locale = json.load(f)

    assert "now_playing_caption" in locale
    assert "{song_title}" in locale["now_playing_caption"]
    assert "{song_dur}" in locale["now_playing_caption"]
    assert "{requester_name}" in locale["now_playing_caption"]


def test_play_started_banner_is_exact_html_string():
    with open("OpenHeartsMusic/locales/en.json", encoding="utf-8") as f:
        locale = json.load(f)

    assert locale["play_started"] == "🎵 <b>Started Streaming</b>"
    assert "<blockquote>" not in locale["play_started"]


def test_now_playing_button_labels_are_ascii_safe():
    button_texts = [button.text for row in build_now_playing_buttons().inline_keyboard for button in row]

    assert "CLOSƐ" not in "".join(button_texts)
    assert "Started Streaming" not in "".join(button_texts)


def test_play_log_uses_named_template_fields():
    msg = SimpleNamespace(
        chat=SimpleNamespace(id=123, title="My Group"),
        from_user=SimpleNamespace(id=456, mention="@alice"),
        link="https://example.com/test",
        lang={
            "play_log": "<b>{song_title}</b> {song_dur} by {requester_name} in {chat_title}"
        },
    )

    with patch.object(app, "logger", 999), patch.object(app, "send_message", new=AsyncMock()) as mock_send:
        asyncio.run(Utilities().play_log(msg, "Example Song", "03:15"))

    assert mock_send.await_count == 1
    sent_text = mock_send.await_args.kwargs["text"]
    assert "Example Song" in sent_text
    assert "03:15" in sent_text
    assert "@alice" in sent_text
    assert "My Group" in sent_text


def test_play_log_ignores_missing_logger():
    msg = SimpleNamespace(
        chat=SimpleNamespace(id=123, title="My Group"),
        from_user=SimpleNamespace(id=456, mention="@alice"),
        link="https://example.com/test",
        lang={},
    )

    with patch.object(app, "logger", ""), patch.object(app, "send_message", new=AsyncMock()) as mock_send:
        asyncio.run(Utilities().play_log(msg, "Example Song", "03:15"))

    mock_send.assert_not_awaited()


def test_welcome_caption_includes_member_identity():
    member = SimpleNamespace(
        id=123456,
        first_name="Alice",
        last_name="Smith",
        username="alice_s",
        mention="<a href='tg://user?id=123456'>Alice</a>",
        photo=None,
    )

    caption = build_welcome_caption(member, "OpenHearts Lounge")

    assert "WELCOME" in caption.upper()
    assert "Alice" in caption
    assert "123456" in caption
    assert "@alice_s" in caption
    assert "OpenHearts Lounge" in caption
