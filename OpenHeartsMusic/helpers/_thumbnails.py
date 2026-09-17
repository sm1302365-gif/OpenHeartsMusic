# ==============================================================================
# thumbnails.py File: OpenHeartsMusic/helpers/
# Description: Custom Thumbnail Generator, Caption Builder & WebApp Button Builder
# ==============================================================================

import os
import re
import random
import asyncio
import html
from io import BytesIO
from pathlib import Path
import aiohttp
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps
from hydrogram.types import InlineKeyboardMarkup

from OpenHeartsMusic import config, db
from OpenHeartsMusic.helpers._inline import ButtonStyle, InlineKeyboardButton

# Paths & Directories
ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "cache"
HELPERS_DIR = ROOT / "helpers"

# Canvas & Card Dimensions
CANVAS_W, CANVAS_H = 1280, 720
CARD_W, CARD_H = 1120, 600
CARD_X = (CANVAS_W - CARD_W) // 2
CARD_Y = (CANVAS_H - CARD_H) // 2

# Brand Colors (RGBA)
CYAN_BORDER = (0, 210, 255, 255)
PINK_BRAND = (255, 0, 128, 255)
CYAN_BRAND = (0, 210, 255, 255)
CARD_BG = (10, 14, 23, 230)

MAX_TITLE_WIDTH = 550
THUMBNAIL_VERSION = "v3"


# ==============================================================================
# BUTTON BUILDERS (Redesigned for Mini App / Colored UI)
# ==============================================================================

def build_start_buttons(bot_username: str) -> InlineKeyboardMarkup:
    """Build the main start-menu keyboard with colorful styling."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    text="➕ Add Me to Your Group",
                    url=f"https://t.me/{bot_username}?startgroup=true",
                    style=ButtonStyle.SUCCESS, # Neon Green style
                )
            ],
            [
                InlineKeyboardButton(
                    text="❓ Help & Commands",
                    callback_data="help_main",
                    style=ButtonStyle.PRIMARY, # Cyber Blue style
                ),
                InlineKeyboardButton(
                    text="⚙️ Settings",
                    callback_data="settings_main",
                    style=ButtonStyle.PRIMARY,
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📢 Support Channel",
                    url="https://t.me/Telegram",
                    style=ButtonStyle.PRIMARY,
                ),
                InlineKeyboardButton(
                    text="🗑️ Close",
                    callback_data="close_menu",
                    style=ButtonStyle.DANGER, # Red/Pink style
                ),
            ],
        ]
    )


def build_help_buttons() -> InlineKeyboardMarkup:
    """Build the help-menu category keyboard with distinct colors."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🎵 Playback", callback_data="help_play", style=ButtonStyle.PRIMARY),
                InlineKeyboardButton("👑 Admin", callback_data="help_admin", style=ButtonStyle.DANGER),
                InlineKeyboardButton("🔐 Auth", callback_data="help_auth", style=ButtonStyle.PRIMARY),
            ],
            [
                InlineKeyboardButton("️ Extras", callback_data="help_extras", style=ButtonStyle.SUCCESS),
            ],
            [
                InlineKeyboardButton("🔙 Back", callback_data="start_menu", style=ButtonStyle.PRIMARY),
                InlineKeyboardButton("🛑 Close", callback_data="close_menu", style=ButtonStyle.DANGER),
            ],
        ]
    )


async def get_now_playing_markup(
    chat_id: int,
    bot_username: str = "@OpenHearts_singing_Bot",
    current_time: str = "00:00",
    total_time: str = "00:00",
) -> InlineKeyboardMarkup:
    """Async wrapper to get playback buttons based on autoplay state."""
    autoplay_enabled = await db.get_autoplay(chat_id)
    return build_now_playing_buttons(
        bot_username=bot_username,
        chat_id=chat_id,
        current_time=current_time,
        total_time=total_time,
        autoplay_enabled=autoplay_enabled,
    )


def build_now_playing_buttons(
    bot_username: str = "",
    chat_id: int = 0,
    current_time: str = "00:00",
    total_time: str = "00:00",
    autoplay_enabled: bool = False,
) -> InlineKeyboardMarkup:
    """Builds the Now Playing interface with intuitive coloring for controls."""
    progress_text = make_timeline(current_time, total_time)
    username = bot_username or "OpenHeartsMusicBot"

    # Select the autoplay button state.
    auto_style = ButtonStyle.SUCCESS if autoplay_enabled else ButtonStyle.DANGER
    auto_label = "🔄 Autoplay: 🟢 ON" if autoplay_enabled else "🔄 Autoplay: 🔴 OFF"

    return InlineKeyboardMarkup(
        [
            # Progress Bar (Primary Color)
            [
                InlineKeyboardButton(
                    text=progress_text,
                    callback_data="cb_progress",
                    style=ButtonStyle.PRIMARY,
                )
            ],
            # Media Controls (Mixed Colors for easy identification)
            [
                InlineKeyboardButton("▷", callback_data=f"ADMIN_RESUME|{chat_id}", style=ButtonStyle.SUCCESS),
                InlineKeyboardButton("II", callback_data=f"ADMIN_PAUSE|{chat_id}", style=ButtonStyle.PRIMARY),
                InlineKeyboardButton("↺", callback_data=f"ADMIN_REPLAY|{chat_id}", style=ButtonStyle.PRIMARY),
                InlineKeyboardButton(">>", callback_data=f"ADMIN_SKIP|{chat_id}", style=ButtonStyle.PRIMARY),
                InlineKeyboardButton("▢", callback_data=f"ADMIN_STOP|{chat_id}", style=ButtonStyle.DANGER),
            ],
            # Utilities
            [
                InlineKeyboardButton(
                    text=auto_label,
                    callback_data="toggle_autoplay",
                    style=auto_style,
                ),
                InlineKeyboardButton(
                    text="CLONE-ME",
                    url=f"https://t.me/{username}?startgroup=true",
                    style=ButtonStyle.SUCCESS,
                ),
            ],
            # Close Button
            [
                InlineKeyboardButton("≡ CLOSƐ ≡", callback_data="close", style=ButtonStyle.DANGER),
            ]
        ]
    )


# ==============================================================================
# UTILITY FUNCTIONS
# ==============================================================================

def trim_to_width(text: str, font: ImageFont.FreeTypeFont, max_w: int) -> str:
    """Trims text with ellipsis if it exceeds the max width."""
    ellipsis = "..."
    try:
        if font.getlength(text) <= max_w:
            return text
        for i in range(len(text) - 1, 0, -1):
            if font.getlength(text[:i] + ellipsis) <= max_w:
                return text[:i] + ellipsis
    except Exception:
        return text[:30] + ellipsis
    return ellipsis


def make_timeline(current_time: str, total_time: str) -> str:
    """Generates progress bar string."""
    try:
        def to_sec(t_str: str) -> int:
            t_str = str(t_str)
            parts = list(map(int, t_str.split(":")))
            if len(parts) == 2:
                return parts[0] * 60 + parts[1]
            if len(parts) == 3:
                return parts[0] * 3600 + parts[1] * 60 + parts[2]
            return 0

        c_sec = to_sec(current_time)
        t_sec = to_sec(total_time)
        percentage = min(max(c_sec / t_sec, 0), 1) if t_sec > 0 else 0

        total_bars = 10
        filled_bars = int(total_bars * percentage)
        unfilled_bars = total_bars - filled_bars

        # Keep every progress segment one character wide so the bar stays fixed.
        bar = "▬" * filled_bars + "▱" * unfilled_bars
        return f"{current_time}  {bar}  {total_time}"
    except Exception:
        return f"{current_time} ▱▱▱▱▱▱▱▱▱▱ {total_time}"


def _safe_text(value, fallback: str = "User") -> str:
    """Remove Telegram link payloads and sanitize plain text for HTML captions."""
    text = str(value or fallback)
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"tg://user\?id=\d+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    return text or fallback


def build_now_playing_caption(song, requester_name: str = "User") -> str:
    """Builds formatted caption text for Now Playing / Queue modules."""
    if isinstance(song, dict):
        song_title = song.get("title", "Unknown Track")
        song_dur = song.get("duration", "00:00")
    else:
        song_title = getattr(song, "title", "Unknown Track")
        song_dur = getattr(song, "duration", "00:00")

    safe_title = html.escape(_safe_text(song_title, "Unknown Track"), quote=False)
    safe_duration = html.escape(_safe_text(song_dur, "00:00"), quote=False)
    safe_requester = html.escape(_safe_text(requester_name, "User"), quote=False)

    return (
        "<b>❖ LIVE NOW ❖</b>\n\n"
        f"❖*STΔRTƐD STRƐΔMIΠG*❖➔\n\n"
        f"❍ **TITLƐ** ➥ {song_title}\n"
        f"❍ **TIMƐ** ➥ {song_dur} MIΠUTƐS\n"
        f"❍ **BY** ➥ {requester_name}"
    )


def _html_escape(value: str) -> str:
    return (
        str(value or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def build_welcome_caption(member, group_title: str = "Group") -> str:
    """Create a safe, readable welcome caption with the new member identity."""
    if member is None:
        member = {}

    first_name = getattr(member, "first_name", "") or (member.get("first_name") if isinstance(member, dict) else "")
    last_name = getattr(member, "last_name", "") or (member.get("last_name") if isinstance(member, dict) else "")
    username = getattr(member, "username", "") or (member.get("username") if isinstance(member, dict) else "")
    user_id = getattr(member, "id", "") or (member.get("id") if isinstance(member, dict) else "")
    display_name = " ".join(part for part in (first_name, last_name) if part).strip() or "User"
    group_name = str(group_title or "Group")

    username_text = username.strip() if username else "no_username"
    return (
        "<b>WELCOME</b>\n\n"
        f"<b>GROUP</b> -> {_html_escape(group_name)}\n"
        f"<b>NAME</b> -> {_html_escape(display_name)}\n"
        f"<b>ID</b> -> {_html_escape(str(user_id))}\n"
        f"<b>USERNAME</b> -> @{_html_escape(username_text)}"
    )


async def generate_welcome_card(member, group_title: str = "Group") -> str:
    """Generate a welcome image card with the member avatar, ID, name, and username."""
    from OpenHeartsMusic import app, config, logger

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    user_id = getattr(member, "id", "unknown") or "unknown"
    slug = re.sub(r"[^A-Za-z0-9_-]", "_", str(user_id))
    output_path = CACHE_DIR / f"welcome_card_{slug}.png"
    if output_path.exists() and output_path.stat().st_size > 0:
        return str(output_path)

    try:
        banner_url = getattr(config, "WELCOME_IMG", "") or getattr(config, "START_IMG", "")
        base = Image.new("RGBA", (1280, 720), (12, 15, 24, 255))

        if banner_url:
            temp_banner = CACHE_DIR / f"welcome_banner_{slug}.jpg"
            try:
                await Thumbnail().save_thumb(str(temp_banner), str(banner_url))
                if temp_banner.exists():
                    with Image.open(temp_banner) as banner_img:
                        base = ImageOps.fit(banner_img.convert("RGBA"), (1280, 720))
            except Exception:
                pass

        bg = ImageEnhance.Brightness(base.filter(ImageFilter.GaussianBlur(18))).enhance(0.55)
        overlay = Image.new("RGBA", bg.size, (10, 12, 18, 170))
        bg = Image.alpha_composite(bg.convert("RGBA"), overlay)

        draw = ImageDraw.Draw(bg)
        card = (60, 60, 1220, 660)
        draw.rounded_rectangle(card, radius=30, fill=(12, 18, 29, 210), outline=(0, 210, 255, 255), width=4)

        title = "WELCOME"
        title_font = ImageFont.truetype(str(HELPERS_DIR / "Masthina Demo.otf"), 72)
        sub_font = ImageFont.truetype(str(HELPERS_DIR / "Masthina Demo.otf"), 28)
        name_font = ImageFont.truetype(str(HELPERS_DIR / "PlaywriteDELAGuides-Regular.ttf"), 44)
        meta_font = ImageFont.truetype(str(HELPERS_DIR / "PlaywriteDELAGuides-Regular.ttf"), 26)

        draw.text((90, 95), title, fill=(255, 255, 255), font=title_font)
        draw.text((90, 170), f"{group_title}", fill=(0, 210, 255), font=sub_font)

        avatar_size = 220
        avatar_x = 120
        avatar_y = 220
        avatar_circle = (avatar_x, avatar_y, avatar_x + avatar_size, avatar_y + avatar_size)
        draw.ellipse(avatar_circle, fill=(30, 40, 52, 255), outline=(0, 210, 255, 255), width=5)

        try:
            avatar_photo = getattr(member, "photo", None)
            avatar_file_id = None
            if avatar_photo is not None:
                avatar_file_id = getattr(avatar_photo, "big_file_id", None) or getattr(avatar_photo, "small_file_id", None)

            if avatar_file_id:
                avatar_media = await app.download_media(avatar_file_id, in_memory=True)
                if avatar_media:
                    if isinstance(avatar_media, bytes):
                        avatar_img = Image.open(BytesIO(avatar_media)).convert("RGBA")
                    else:
                        avatar_img = Image.open(str(avatar_media)).convert("RGBA")
                    avatar_img = ImageOps.fit(avatar_img, (avatar_size - 18, avatar_size - 18), centering=(0.5, 0.5))
                    mask = Image.new("L", (avatar_size - 18, avatar_size - 18), 0)
                    ImageDraw.Draw(mask).ellipse((0, 0, avatar_size - 18, avatar_size - 18), fill=255)
                    circle = Image.new("RGBA", (avatar_size - 18, avatar_size - 18), (0, 0, 0, 0))
                    circle.paste(avatar_img, (0, 0), mask)
                    bg.paste(circle, (avatar_x + 9, avatar_y + 9), circle)
        except Exception as e:
            logger.debug(f"Welcome avatar download failed: {e}")

        if not output_path.exists():
            first_name = getattr(member, "first_name", "") or "User"
            last_name = getattr(member, "last_name", "") or ""
            display_name = " ".join(part for part in (first_name, last_name) if part).strip() or "User"
            final_name = trim_to_width(display_name, name_font, 700)
            draw.text((390, 260), final_name, fill=(255, 255, 255), font=name_font)

            user_id = getattr(member, "id", "unknown")
            draw.text((390, 330), f"ID: {user_id}", fill=(220, 220, 220), font=meta_font)
            username = getattr(member, "username", None) or "no_username"
            draw.text((390, 370), f"@{username}", fill=(0, 210, 255), font=meta_font)

            badge = "NEW MEMBER"
            badge_size = draw.textbbox((0, 0), badge, font=meta_font)
            draw.rounded_rectangle((390, 420, 390 + badge_size[2] + 24, 420 + badge_size[3] + 18), radius=12, fill=(0, 210, 255, 220))
            draw.text((402, 426), badge, fill=(0, 10, 18), font=meta_font)

        bg.save(output_path)
        return str(output_path)
    except Exception as e:
        logger.debug(f"Welcome card generation failed: {e}")
        return str(config.WELCOME_IMG or config.START_IMG or "")


class Thumbnail:
    def __init__(self):
        self.title_font = self._load_font("PlaywriteDELAGuides-Regular.ttf", 38)
        self.sub_font = self._load_font("PlaywriteDELAGuides-Regular.ttf", 22)
        self.brand_font = self._load_font("Masthina Demo.otf", 24)

    @staticmethod
    def _load_font(filename: str, size: int):
        try:
            return ImageFont.truetype(str(HELPERS_DIR / filename), size)
        except (OSError, ValueError):
            return ImageFont.load_default()

    async def save_thumb(self, output_path: str, url: str) -> str:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        if os.path.exists(output_path):
            os.remove(output_path)

        connector = aiohttp.TCPConnector(
            limit=10, limit_per_host=3, keepalive_timeout=30, ttl_dns_cache=300
        )
        timeout = aiohttp.ClientTimeout(total=20, connect=10, sock_read=10)
        last_error = None
        max_retries = 5

        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession(
                    connector=connector, timeout=timeout, trust_env=True
                ) as session:
                    async with session.get(
                        url,
                        headers={
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36 Edg/151.0.0.0',
                            'Accept': 'image/*',
                        },
                        ssl=False, allow_redirects=True,
                    ) as resp:
                        resp.raise_for_status()
                        data = await resp.read()

                        if data and len(data) > 100:
                            loop = asyncio.get_running_loop()
                            await loop.run_in_executor(None, self._write_file, output_path, data)
                            return output_path
                        else:
                            last_error = "Downloaded image is empty"
                            break
            except Exception as e:
                last_error = str(e)
                if attempt < max_retries - 1:
                    await asyncio.sleep(0.5 * (2 ** attempt))
                    continue
                break

        if os.path.exists(output_path):
            try: os.remove(output_path)
            except: pass

        if last_error:
            from OpenHeartsMusic import logger
            logger.debug(f"Thumbnail download failed: {last_error}")

        return output_path

    def _write_file(self, output_path: str, data: bytes) -> None:
        with open(output_path, "wb") as f:
            f.write(data)

    @staticmethod
    def _song_value(song, key: str, default=""):
        if isinstance(song, dict):
            return song.get(key, default)
        return getattr(song, key, default)

    async def generate(self, song, size=(1280, 720)) -> str:
        try:
            from OpenHeartsMusic import logger
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            song_id = re.sub(r"[^A-Za-z0-9_-]", "_", str(self._song_value(song, "id", "temp_track")))
            temp_path = CACHE_DIR / f"temp_{song_id}.jpg"
            output_path = CACHE_DIR / f"{song_id}_custom_{THUMBNAIL_VERSION}.png"

            if output_path.exists() and output_path.stat().st_size > 0:
                return str(output_path)

            thumbnail_url = self._song_value(song, "thumbnail") or getattr(config, "DEFAULT_THUMB", "")
            if thumbnail_url:
                if temp_path.exists():
                    try: temp_path.unlink()
                    except: pass
                try:
                    await self.save_thumb(str(temp_path), thumbnail_url)
                except Exception as e:
                    logger.debug(f"Failed to download thumbnail: {e}")

            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, self._generate_sync, temp_path, output_path, song, size)

        except Exception as e:
            from OpenHeartsMusic import logger
            logger.debug(f"Thumbnail generation error: {e}")
            return getattr(config, "DEFAULT_THUMB", "")

    def _generate_sync(self, temp_path: Path, output_path: Path, song, size=(1280, 720)) -> str:
        try:
            if temp_path.exists():
                try:
                    with Image.open(temp_path) as temp_img:
                        temp_img.load()
                        base = ImageOps.fit(temp_img.convert("RGBA"), size)
                except Exception:
                    base = Image.new("RGBA", size, (20, 20, 30, 255))
            else:
                base = Image.new("RGBA", size, (20, 20, 30, 255))

            bg = ImageEnhance.Brightness(base.filter(ImageFilter.GaussianBlur(25))).enhance(0.3)
            draw_bg = ImageDraw.Draw(bg)

            # Main Card Panel
            card_box = [CARD_X, CARD_Y, CARD_X + CARD_W, CARD_Y + CARD_H]
            card_surface = Image.new("RGBA", (CARD_W, CARD_H), CARD_BG)
            card_mask = Image.new("L", (CARD_W, CARD_H), 0)
            ImageDraw.Draw(card_mask).rounded_rectangle((0, 0, CARD_W, CARD_H), 35, fill=255)
            bg.paste(card_surface, (CARD_X, CARD_Y), card_mask)
            draw_bg.rounded_rectangle(card_box, radius=35, outline=CYAN_BORDER, width=4)

            # Circular Artwork
            circle_dim = 320
            circle_x, circle_y = CARD_X + 60, CARD_Y + 70
            thumb_crop = ImageOps.fit(base, (circle_dim, circle_dim), centering=(0.5, 0.5))
            circle_mask = Image.new("L", (circle_dim, circle_dim), 0)
            ImageDraw.Draw(circle_mask).ellipse((0, 0, circle_dim, circle_dim), fill=255)
            bg.paste(thumb_crop, (circle_x, circle_y), circle_mask)
            draw_bg.ellipse([circle_x - 8, circle_y - 8, circle_x + circle_dim + 8, circle_y + circle_dim + 8], outline=CYAN_BORDER, width=4)

            # Text Information
            text_x, text_y = circle_x + circle_dim + 50, CARD_Y + 80
            song_title = str(self._song_value(song, "title", "Unknown Track"))
            clean_title = re.sub(r"\W+", " ", song_title).strip().title()
            draw_bg.text((text_x, text_y), trim_to_width(clean_title, self.title_font, MAX_TITLE_WIDTH), fill="white", font=self.title_font)

            artist_name = self._song_value(song, "artist") or self._song_value(song, "channel_name") or self._song_value(song, "channel", "Unknown Artist")
            draw_bg.text((text_x, text_y + 55), f"Artist: {artist_name}", fill=(200, 200, 200), font=self.sub_font)

            views = self._song_value(song, "view_count") or self._song_value(song, "views") or "402 views"
            draw_bg.text((text_x, text_y + 95), f"Views: {views}", fill=(200, 200, 200), font=self.sub_font)

            duration = self._song_value(song, "duration", "04:56")
            draw_bg.text((text_x, text_y + 135), f"Duration: {duration}", fill=(200, 200, 200), font=self.sub_font)

            # Waveform Visualizer
            wave_x, wave_y = text_x, text_y + 200
            bar_width, gap = 4, 3
            bar_step = bar_width + gap
            available_wave_width = max(1, CARD_X + CARD_W - 60 - wave_x)
            num_bars = max(1, available_wave_width // bar_step)

            random.seed(hash(song_title))
            for i in range(num_bars):
                height = random.randint(10, 45)
                bx = wave_x + i * bar_step
                draw_bg.line([(bx, wave_y - height // 2), (bx, wave_y + height // 2)], fill="white", width=bar_width)

            # Progress Bar Image
            bar_start_x, bar_end_x, bar_y_pos = wave_x, wave_x + (num_bars * bar_step) - gap, wave_y + 35
            draw_bg.line([(bar_start_x, bar_y_pos), (bar_end_x, bar_y_pos)], fill="gray", width=2)
            dot_x = bar_start_x + int((bar_end_x - bar_start_x) * 0.45)
            draw_bg.ellipse([(dot_x - 5, bar_y_pos - 5), (dot_x + 5, bar_y_pos + 5)], fill="white")

            draw_bg.text((bar_start_x, bar_y_pos + 10), "00:00", fill="gray", font=self.sub_font)
            duration_text = trim_to_width(str(duration), self.sub_font, 80)
            draw_bg.text((min(bar_end_x - self.sub_font.getlength(duration_text), CARD_X + CARD_W - 60 - self.sub_font.getlength(duration_text)), bar_y_pos + 10), duration_text, fill="gray", font=self.sub_font)

            # Branding
            brand_y = CARD_Y + CARD_H - 45
            draw_bg.text((CARD_X + 40, brand_y), "OPENHEARTS HUB", fill=CYAN_BRAND, font=self.brand_font)
            draw_bg.text((CARD_X + CARD_W - 250, brand_y), "OPENHEARTS MUSIC", fill=PINK_BRAND, font=self.brand_font)

            bg.save(output_path)
            if temp_path.exists():
                os.remove(temp_path)

            return str(output_path)

        except Exception as e:
            print(f"Error generating thumbnail: {e}")
            return getattr(config, "DEFAULT_THUMB", "")
