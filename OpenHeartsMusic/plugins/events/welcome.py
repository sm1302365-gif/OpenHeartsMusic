# =================================================
# Welcome.py
# =================================================

"""Welcome cards for new group members."""

from io import BytesIO
from pathlib import Path
import unicodedata

import aiohttp
import requests
from hydrogram import filters
from hydrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from PIL import Image, ImageDraw, ImageFont, ImageOps

from OpenHeartsMusic import app, config, lang, logger

try:
    from pilmoji import Pilmoji
except ImportError:
    class Pilmoji:
        def __init__(self, image):
            self._draw = ImageDraw.Draw(image)

        def __enter__(self):
            return self._draw

        def __exit__(self, exc_type, exc_value, traceback):
            return False

# Path configuration
CURRENT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[2]

TEMPLATE_FILENAME = "Green and Black Modern Futuristic.jpg"

PROFILE_BOX = (155, 495, 625, 965)


def _find_template_path() -> Path:
    """Find the template file in current directory, root, or working directory."""
    candidates = [
        CURRENT_DIR / TEMPLATE_FILENAME,
        ROOT / TEMPLATE_FILENAME,
        Path.cwd() / TEMPLATE_FILENAME,
    ]
    for path in candidates:
        if path.exists():
            return path
    return CURRENT_DIR / TEMPLATE_FILENAME


def _clean_text(text: str) -> str:
    """Convert decorative names to ASCII plain text for reliable rendering."""
    if not text:
        return "User"
    normalized = unicodedata.normalize("NFKD", str(text))
    clean = normalized.encode("ascii", "ignore").decode("ascii")
    clean = " ".join(clean.split())
    return clean if clean else "User"


def _font(size: int):
    for filename in ("PlaywriteDELAGuides-Regular.ttf", "arial.ttf"):
        font_path = ROOT / "helpers" / filename
        try:
            return ImageFont.truetype(str(font_path), size)
        except (OSError, ValueError):
            continue
    return ImageFont.load_default()


def _name_font(size: int):
    try:
        return ImageFont.truetype(str(CURRENT_DIR / "Inter-Light.ttf"), size)
    except (OSError, ValueError):
        return ImageFont.load_default()


def _fit_text_font(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_width: int,
    size: int = 34,
    font_loader=_font,
):
    """Keep dynamic member values inside the template's value columns."""
    while size > 10:
        font = font_loader(size)
        if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
            return font
        size -= 1
    font = font_loader(10)
    while draw.textbbox((0, 0), text, font=font)[2] > max_width and size > 6:
        size -= 1
        font = font_loader(size)
    return font


def _load_base_image(base_image_source=None) -> Image.Image:
    """Load base template image, prioritizing local Canva template."""
    template_path = _find_template_path()
    if template_path.exists():
        try:
            return Image.open(template_path).convert("RGBA")
        except (OSError, ValueError):
            pass

    if base_image_source:
        try:
            if isinstance(base_image_source, str) and base_image_source.startswith(("http://", "https://")):
                response = requests.get(
                    base_image_source,
                    timeout=15,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36 Edg/151.0.0.0"},
                )
                response.raise_for_status()
                return Image.open(BytesIO(response.content)).convert("RGBA")

            if isinstance(base_image_source, bytes):
                return Image.open(BytesIO(base_image_source)).convert("RGBA")

            if isinstance(base_image_source, (str, Path)):
                base_path = Path(base_image_source)
                if base_path.exists():
                    return Image.open(base_path).convert("RGBA")
        except (OSError, ValueError):
            pass

    return Image.new("RGBA", (1920, 1080), (12, 15, 24, 255))


def generate_welcome_image(
    profile_pic_source,
    member_id: int,
    username: str,
    status: str = "MEMBER",
    base_image_source=None,
    full_name: str = "User",
) -> BytesIO:
    """Generates a custom welcome thumbnail overlay for new group members."""
    img = _load_base_image(base_image_source)

    target_size = (1920, 1080)
    if img.size != target_size:
        img = ImageOps.fit(img, target_size)

    # Process profile picture positioning
    if profile_pic_source:
        try:
            if isinstance(profile_pic_source, str) and profile_pic_source.startswith("http"):
                response = requests.get(
                    profile_pic_source,
                    timeout=15,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36 Edg/151.0.0.0"},
                )
                response.raise_for_status()
                profile_img = Image.open(BytesIO(response.content)).convert("RGBA")
            else:
                profile_img = Image.open(profile_pic_source).convert("RGBA")

            left, top, right, bottom = PROFILE_BOX
            profile_size = right - left
            profile_img = ImageOps.fit(profile_img, (profile_size, profile_size))

            mask = Image.new("L", (profile_size, profile_size), 0)
            draw_mask = ImageDraw.Draw(mask)
            draw_mask.ellipse((0, 0, profile_size - 1, profile_size - 1), fill=255)

            img.paste(profile_img, (left, top), mask)
        except (OSError, ValueError) as err:
            logger.debug(f"Failed to process profile picture: {err}")

    text_color = "#88FF44"
    full_name = _clean_text(full_name)
    username_text = f"{username}" if username and username != "N/A" else "N/A"
    draw = ImageDraw.Draw(img)
    name_font = _fit_text_font(draw, full_name, 390, font_loader=_name_font)
    username_font = _fit_text_font(
        draw, username_text, 310, font_loader=_name_font
    )
    member_id_font = _fit_text_font(
        draw, str(member_id), 310, font_loader=_name_font
    )

    with Pilmoji(img) as pilmoji:
        pilmoji.text((1295, 575), full_name, font=name_font, fill=text_color)
        pilmoji.text((1395, 665), username_text, font=username_font, fill=text_color)
        pilmoji.text((1386, 755), str(member_id), font=member_id_font, fill=text_color)

    bg = Image.new("RGB", img.size, (12, 15, 24))
    bg.paste(img, (0, 0), img)

    final_buffer = BytesIO()
    bg.save(final_buffer, format="JPEG", quality=95)
    final_buffer.seek(0)
    final_buffer.name = "welcome.jpg"

    return final_buffer


def _member_name(member) -> str:
    return " ".join(
        part for part in (getattr(member, "first_name", ""), getattr(member, "last_name", "")) if part
    ) or "User"


@app.on_message(filters.new_chat_members & filters.group, group=8)
@lang.language()
async def welcome_new_member(client, message):
    if not getattr(config, "WELCOME_ENABLED", True):
        return

    members = [
        member for member in message.new_chat_members
        if member.id != app.id and not getattr(member, "is_bot", False)
    ]
    if not members:
        return

    total_members = await client.get_chat_members_count(message.chat.id)

    for member in members:
        user_id = member.id
        username = getattr(member, "username", None) or "N/A"
        profile_buffer = None
        try:
            photo = getattr(member, "photo", None)
            file_id = getattr(photo, "big_file_id", None) or getattr(photo, "small_file_id", None)
            if file_id:
                profile_buffer = await client.download_media(file_id, in_memory=True)

            welcome_image = generate_welcome_image(
                profile_pic_source=profile_buffer,
                member_id=user_id,
                username=username,
                full_name=_member_name(member),
            )
            caption = (
                "⎊─────☵ ᴡᴇʟᴄᴏᴍᴇ ☵─────⎊\n\n"
                f"☉ ɴᴀᴍᴇ ⧽ ⌯ {_member_name(member)} ꭙ ᴍᴜꜱɪᴄ ♪ [ ɪꨄ︎ʀ ]\n"
                f"☉ ɪᴅ ⧽ {user_id}\n"
                f"☉ ᴛᴏᴛᴀʟ ᴍᴇᴍʙᴇʀs ⧽ {total_members}\n\n"
                "──── OpenHearts Music ────"
            )
            markup = InlineKeyboardMarkup(
                [[InlineKeyboardButton("View Member", url=f"tg://user?id={user_id}")]]
            )
            await message.reply_photo(
                photo=welcome_image,
                caption=caption,
                reply_markup=markup,
            )
        except Exception as error:
            logger.debug(f"Welcome card failed for {user_id}: {error}")
            try:
                await message.reply_text(f"Welcome {_member_name(member)}!")
            except Exception:
                pass
