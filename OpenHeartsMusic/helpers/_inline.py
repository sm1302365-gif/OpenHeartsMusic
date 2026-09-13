# ==============================================================================
# _inline.py - Advanced Keyboard Markup Generator
# ==============================================================================
# A highly optimized, strongly-typed helper class to generate inline keyboards
# for Hydrogram bots. Features automatic style resolution and dynamic type checking.
# ==============================================================================

import inspect
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from hydrogram.types import (
    InlineKeyboardButton as HydrogramInlineKeyboardButton,
    InlineKeyboardMarkup,
)

from OpenHeartsMusic import app, config


def _normalize_button_style(style: Optional[str]) -> Optional[str]:
    if not style:
        return None

    style_value = getattr(style, "value", style)
    aliases = {
        "red": ButtonStyle.DANGER.value,
        "bg_danger": ButtonStyle.DANGER.value,
        "green": ButtonStyle.SUCCESS.value,
        "bg_success": ButtonStyle.SUCCESS.value,
        "blue": ButtonStyle.PRIMARY.value,
        "bg_primary": ButtonStyle.PRIMARY.value,
    }
    normalized_style = aliases.get(str(style_value).strip().lower(), str(style_value).strip().lower())
    if normalized_style not in {item.value for item in ButtonStyle}:
        raise ValueError("Button style must be one of: danger, success, primary")
    return normalized_style


class ButtonStyle(str, Enum):
    """Enumeration for standardized Telegram inline button styles."""
    PRIMARY = "primary"
    SUCCESS = "success"
    DANGER = "danger"


class InlineKeyboardButton(HydrogramInlineKeyboardButton):
    """Hydrogram button with Telegram background-style metadata."""

    def __init__(
        self,
        text: str,
        style: Optional[str] = None,
        background_color: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(text=text, **kwargs)
        selected_style = style or background_color
        self.style = _normalize_button_style(selected_style)
        self.background_color = self.style

    def write(self, client: Any = None) -> Any:
        """Serialize locally, or delegate to Hydrogram for Telegram requests."""
        if client is not None:
            return super().write(client)

        data = {
            "text": self.text,
            "callback_data": getattr(self, "callback_data", None),
            "url": getattr(self, "url", None),
            "web_app": getattr(self, "web_app", None),
            "login_url": getattr(self, "login_url", None),
            "switch_inline_query": getattr(self, "switch_inline_query", None),
            "switch_inline_query_current_chat": getattr(
                self, "switch_inline_query_current_chat", None
            ),
            "callback_game": getattr(self, "callback_game", None),
            "pay": getattr(self, "pay", None),
        }
        if self.style:
            data["style"] = self.style
        return data


class Inline:
    """
    Advanced generator for Inline Keyboards with automated style injection
    and strict type hinting for optimized performance.
    """

    # Cache the parameter inspection at the class level to reduce overhead
    _sig_params = inspect.signature(InlineKeyboardButton).parameters
    _SUPPORTS_STYLE: bool = "style" in _sig_params or any(
        p.kind == inspect.Parameter.VAR_KEYWORD for p in _sig_params.values()
    )

    def __init__(self) -> None:
        self.ikm = InlineKeyboardMarkup
        self.ikb = self._make_button

    def _make_button(
        self,
        text: str,
        callback_data: Optional[str] = None,
        url: Optional[str] = None,
        style: Optional[str] = None,
        background_color: Optional[str] = None,
        **kwargs: Any
    ) -> InlineKeyboardButton:
        """
        Dynamically constructs an InlineKeyboardButton with safe parameter unpacking.
        """
        # Resolve target style fallback
        target_style = style or background_color or getattr(config, "BUTTON_BG_COLOR", None)
        try:
            normalized_style = self._normalize_style(target_style)
        except ValueError:
            if style is not None or background_color is not None:
                raise
            normalized_style = None

        # Base button payload
        payload: Dict[str, Any] = {**kwargs}

        if callback_data:
            payload["callback_data"] = callback_data
        if url:
            payload["url"] = url

        # Inject style parameter securely if supported by the Hydrogram version
        if self._SUPPORTS_STYLE and normalized_style:
            payload["style"] = normalized_style

        return InlineKeyboardButton(text=text, **payload)

    @staticmethod
    def _normalize_style(style: Optional[str]) -> Optional[str]:
        """Normalize a requested style to the supported button variants."""
        return _normalize_button_style(style)

    def color_button(
        self,
        text: str,
        callback_data: Optional[str] = None,
        url: Optional[str] = None,
        style: Optional[str] = None,
        background_color: Optional[str] = None,
        **kwargs: Any
    ) -> InlineKeyboardButton:
        """Alias for creating standard colored buttons."""
        return self._make_button(
            text,
            callback_data,
            url,
            style,
            background_color,
            **kwargs,
        )

    def cancel_dl(self, text: str) -> InlineKeyboardMarkup:
        """Generates a cancellation button markup."""
        return self.ikm([[self.ikb(text=text, callback_data="cancel_dl", style=ButtonStyle.DANGER)]])

    def controls(
        self,
        chat_id: int,
        status: Optional[str] = None,
        timer: Optional[str] = None,
        remove: bool = False,
    ) -> InlineKeyboardMarkup:
        """Generates dynamic playback control keyboards."""
        keyboard: List[List[InlineKeyboardButton]] = []

        if status or timer:
            display_text = status if status else timer
            keyboard.append(
                [self.ikb(text=display_text, callback_data=f"controls status {chat_id}", style=ButtonStyle.PRIMARY)]
            )

        if not remove:
            keyboard.extend([
                [
                    self.ikb(text="« 30", callback_data=f"controls seek_back_30 {chat_id}", style=ButtonStyle.PRIMARY),
                    self.ikb(text="« 10", callback_data=f"controls seek_back_10 {chat_id}", style=ButtonStyle.PRIMARY),
                    self.ikb(text="10 »", callback_data=f"controls seek_forward_10 {chat_id}", style=ButtonStyle.PRIMARY),
                    self.ikb(text="30 »", callback_data=f"controls seek_forward_30 {chat_id}", style=ButtonStyle.PRIMARY),
                ],
                [
                    self.ikb(text="▷", callback_data=f"controls resume {chat_id}", style=ButtonStyle.SUCCESS),
                    self.ikb(text="II", callback_data=f"controls pause {chat_id}", style=ButtonStyle.PRIMARY),
                    self.ikb(text="↩", callback_data=f"controls replay {chat_id}", style=ButtonStyle.PRIMARY),
                    self.ikb(text=">>", callback_data=f"controls skip {chat_id}", style=ButtonStyle.PRIMARY),
                    self.ikb(text="▢", callback_data=f"controls stop {chat_id}", style=ButtonStyle.DANGER),
                ],
                [
                    self.ikb(text="ᴅᴇʟᴇᴛᴇ", callback_data=f"controls close {chat_id}", style=ButtonStyle.DANGER),
                ]
            ])

        return self.ikm(keyboard)

    def help_markup(self, _lang: Dict[str, Any], back: bool = False) -> InlineKeyboardMarkup:
        """Generates the main help menu or nested back button."""
        if back:
            return self.ikm([[self.ikb(text="⬅️ ʙᴀᴄᴋ", callback_data="help_main", style=ButtonStyle.PRIMARY)]])

        rows = [
            [
                self.ikb(text="ᴀᴅᴍɪɴꜱ", callback_data="help_admins", style=ButtonStyle.PRIMARY),
                self.ikb(text="ᴀᴄᴄʜ", callback_data="help_auth", style=ButtonStyle.PRIMARY),
            ],
            [
                self.ikb(text="ʟᴏᴏᴘ", callback_data="help_loop", style=ButtonStyle.PRIMARY),
                self.ikb(text="ᴘʟᴀʏ", callback_data="help_play", style=ButtonStyle.PRIMARY),
                self.ikb(text="ǫᴜᴇᴄᴄᴇ", callback_data="help_queue", style=ButtonStyle.PRIMARY),
            ],
            [
                self.ikb(text="Delete", callback_data="help_delete", style=ButtonStyle.DANGER),
            ],
            [
                self.ikb(text="ᴀꜛꜛɪꜛᴛᴀɴᴛ", callback_data="help_assistant", style=ButtonStyle.PRIMARY),
                self.ikb(text="ᴘɪɴɢ", callback_data="help_ping", style=ButtonStyle.PRIMARY),
                self.ikb(text="ꜱᴛᴀᴛꜱ", callback_data="help_stats", style=ButtonStyle.PRIMARY),
                self.ikb(text="ꜱᴜᴅᴏ", callback_data="help_sudo", style=ButtonStyle.PRIMARY),
            ],
            [

                self.ikb(text="ᴀᴜᴛᴏ-ᴄʟᴇᴀɴ", callback_data="help_autoclean_module", style=ButtonStyle.PRIMARY),
                self.ikb(text="🔄 Auto-Play Mode", callback_data="autoplay_help", style=ButtonStyle.PRIMARY),
            ],
            [
                self.ikb(text="⬅️ ʙᴀᴄᴋ", callback_data="start", style=ButtonStyle.DANGER),
            ],
        ]
        return self.ikm(rows)

    def ping_markup(self, text: str) -> InlineKeyboardMarkup:
        """Generates the ping command keyboard markup."""
        return self.ikm([
            [
                self.ikb(text="📢 Channel", url=config.SUPPORT_CHANNEL, style=ButtonStyle.PRIMARY),
                self.ikb(text="🆘 Support", url=config.SUPPORT_CHAT, style=ButtonStyle.PRIMARY),
            ],
            [
                self.ikb(text="➕ Add Me to Your Group", url=f"https://t.me/{app.username}?startgroup=true", style=ButtonStyle.SUCCESS),
            ]
        ])

    def play_queued(
        self, chat_id: int, item_id: str, _text: str
    ) -> InlineKeyboardMarkup:
        """Generates controls for newly queued tracks."""
        return self.ikm([
            [
                self.ikb(text="▷", callback_data=f"controls resume {chat_id}", style=ButtonStyle.SUCCESS),
                self.ikb(text="II", callback_data=f"controls pause {chat_id}", style=ButtonStyle.PRIMARY),
                self.ikb(text=">>", callback_data=f"controls skip {chat_id}", style=ButtonStyle.PRIMARY),
                self.ikb(text="▢", callback_data=f"controls stop {chat_id}", style=ButtonStyle.DANGER),
            ],
            [
                self.ikb(text="ᴅᴇʟᴇᴛᴇ", callback_data=f"controls close {chat_id}", style=ButtonStyle.DANGER),
            ]
        ])

    def queue_markup(
        self, chat_id: int, _text: str, playing: bool
    ) -> InlineKeyboardMarkup:
        """Generates active queue manipulation buttons."""
        _action = "pause" if playing else "resume"
        _style = ButtonStyle.PRIMARY if playing else ButtonStyle.SUCCESS

        return self.ikm(
            [[self.ikb(text=_text, callback_data=f"controls {_action} {chat_id} q", style=_style)]]
        )

    def settings_markup(
        self, lang: Dict[str, str], admin_only: bool, autoplay_enabled: bool, chat_id: int
    ) -> InlineKeyboardMarkup:
        """Generates interactive setting toggle buttons."""
        rows = [
            [
                self.ikb(text=f"{lang.get('play_mode', 'Play Mode')} ➜", callback_data=f"controls status {chat_id}", style=ButtonStyle.PRIMARY),
                self.ikb(text=str(admin_only), callback_data="playmode", style=ButtonStyle.PRIMARY),
            ],
        ]

        autoplay_label = f"{lang.get('autoplay', 'Autoplay')} " + ("✅" if autoplay_enabled else "➖")
        btn_style = ButtonStyle.SUCCESS if autoplay_enabled else ButtonStyle.DANGER

        rows.append([self.ikb(text=autoplay_label, callback_data="autoplay", style=btn_style)])

        return self.ikm(rows)

    def start_key(
        self, lang: Dict[str, str], private: bool = False
    ) -> InlineKeyboardMarkup:
        """Generates the main start keyboard."""
        rows = [
            [
                self.ikb(text=lang.get("add_me", "Add Me"), url=f"https://t.me/{app.username}?startgroup=true", style=ButtonStyle.SUCCESS)
            ],
            [
                self.ikb(text=lang.get("help", "Help"), callback_data="help", style=ButtonStyle.PRIMARY)
            ],
            [
                self.ikb(text=lang.get("support", "Support"), url=config.SUPPORT_CHAT, style=ButtonStyle.PRIMARY),
                self.ikb(text=lang.get("channel", "Channel"), url=config.SUPPORT_CHANNEL, style=ButtonStyle.PRIMARY),
            ],
        ]

        if private:
            dev_username = config.DEVELOPER_USERNAME.strip().removeprefix("https://t.me/").lstrip("@")
            rows.append(
                [self.ikb(text=lang.get("developer", "Developer"), url=f"https://t.me/{dev_username}", style=ButtonStyle.PRIMARY)]
            )

        return self.ikm(rows)

    def yt_key(self, link: str) -> InlineKeyboardMarkup:
        """Generates generic YouTube interaction buttons."""
        return self.ikm([
            [
                self.ikb(text="ᴄᴏᴘʏ ʟɪɴᴋ", copy_text=link, style=ButtonStyle.PRIMARY),
                self.ikb(text="ᴏᴘᴇɴ ɪɴ ʏᴏᴜᴛᴜʙᴇ", url=link, style=ButtonStyle.DANGER),
            ],
        ])
