# ==============================================================================
# start.py - Basics & Custom Styled Inline Buttons
# ==============================================================================
# Essential user-facing commands: /start, /help, /settings, etc.
# ==============================================================================

from os import getenv

from hydrogram import enums, errors, filters, types
from hydrogram.types import InlineKeyboardMarkup, CallbackQuery

from OpenHeartsMusic import app, config, db, lang
from OpenHeartsMusic.helpers import buttons, utils
from OpenHeartsMusic.helpers._inline import InlineKeyboardButton
from OpenHeartsMusic.helpers._play import is_supported_chat
from config import CustomFonts


@app.on_message(filters.command(["help"]) & filters.private & ~app.bl_users)
@lang.language()
async def _help(_, m: types.Message):
    """Display help menu with custom button styling support."""
    help_text = f"<b>Help</b>\n\n{m.lang['help_menu']}"

    try:
        await m.reply_photo(
            photo=config.START_IMG,
            caption=help_text,
            reply_markup=buttons.help_markup(m.lang),
            quote=False,
            parse_mode=enums.ParseMode.HTML,
        )
    except Exception:
        await m.reply_text(
            text=help_text,
            reply_markup=buttons.help_markup(m.lang),
            quote=True,
            parse_mode=enums.ParseMode.HTML,
        )


@app.on_message(filters.command(["start"]))
@lang.language()
async def start(_, message: types.Message):
    """Handle /start command for both private chats and groups."""
    # Skip if message from channel or anonymous admin
    if not message.from_user:
        return

    # Check if user is blacklisted
    if message.from_user.id in app.bl_users and message.from_user.id not in db.notified:
        return await message.reply_text(message.lang["bl_user_notify"])

    # If /start help, show help menu
    if len(message.command) > 1 and message.command[1] == "help":
        return await _help(_, message)

    # Determine if chat is private or group
    private = message.chat.type == enums.ChatType.PRIVATE

    # Choose appropriate welcome message
    _text = (
        message.lang["start_pm"].format(message.from_user.first_name, app.name)
        if private
        else message.lang["start_gp"].format(app.name)
    )

    key = buttons.start_key(message.lang, private)
    try:
        await message.reply_photo(
            photo=config.START_IMG,
            caption=_text,
            reply_markup=key,
            quote=False,
            parse_mode=enums.ParseMode.HTML,
        )
    except errors.ChatSendPhotosForbidden:
        # If photos are not allowed, send text only
        await message.reply_text(
            text=_text,
            reply_markup=key,
            quote=False,
            parse_mode=enums.ParseMode.HTML,
        )

    # For private chats, add user to database if new
    if private:
        if await db.is_user(message.from_user.id):
            return  # User already exists, no need to add
        # Log new user to logger group
        await utils.send_log(message)
        # Add user to database
        return await db.add_user(message.from_user.id)


@app.on_message(filters.command(["playmode", "settings"]) & filters.group & ~app.bl_users)
@lang.language()
async def settings(_, message: types.Message):
    """Display settings and playmode configurations for groups."""
    admin_only = await db.get_play_mode(message.chat.id)
    autoplay_enabled = await db.get_autoplay(message.chat.id)
    await utils.safe_text(
        message,
        message.lang["start_settings"].format(message.chat.title),
        reply_markup=buttons.settings_markup(
            message.lang, admin_only, autoplay_enabled, message.chat.id
        ),
        quote=True,
    )


@app.on_message(filters.new_chat_members, group=7)
@lang.language()
async def _new_member(_, message: types.Message):
    """Handle new bot addition to group chats."""
    if not is_supported_chat(message.chat.type):
        return

    for member in message.new_chat_members:
        if member.id == app.id:
            if await db.is_chat(message.chat.id):
                return
            await utils.chat_log(message)
            await db.add_chat(message.chat.id)


# ============================================================================
# Mode Selection with CustomFonts & Button Background Styles
# ============================================================================
@app.on_callback_query(filters.regex("^start_modes$"))
@lang.language()
async def start_modes_handler(client, callback_query: CallbackQuery):
    """Display mode selection menu with styled primary buttons."""
    try:
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    text=CustomFonts.START_STUDIO,
                    callback_data="studio_home",
                    style="primary"  # Blue/Primary button background color
                )
            ]
        ])

        await callback_query.message.edit_text(
            text="<b>✨ Welcome! Please select an option from the menu below:</b>",
            reply_markup=keyboard,
            parse_mode=enums.ParseMode.HTML,
        )
        await callback_query.answer()
    except Exception as e:
        await callback_query.answer(f"Error: {str(e)}", show_alert=True)


@app.on_callback_query(filters.regex("^studio_home$"))
@lang.language()
async def studio_mode_handler(client, callback_query: CallbackQuery):
    """Handle studio mode section interactions."""
    try:
        await callback_query.message.edit_text(
            text="<b>Studio</b>\n\n🎧 <i>Studio mode activated! Premium audio experience.</i>",
            parse_mode=enums.ParseMode.HTML,
        )
        await callback_query.answer("Studio mode selected!", show_alert=False)
    except Exception as e:
        await callback_query.answer(f"Error: {str(e)}", show_alert=True)


# ============================================================================
# Help Menu with CustomFonts Styling & Background Colors
# ============================================================================
@app.on_callback_query(filters.regex("^help_menu$"))
@lang.language()
async def help_menu_handler(client, callback_query: CallbackQuery):
    """Display help menu with styled success buttons."""
    try:
        username = callback_query.message.chat.username or callback_query.message.chat.title or "User"
        help_text = f"<b>Help</b>\n\n{username}'s Help Menu\n\nSelect an option below for more information."

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    text=CustomFonts.HELP_BTN,
                    callback_data="help_commands",
                    style="success"  # Green/Success button background color
                )
            ]
        ])

        await callback_query.message.edit_text(
            text=help_text,
            reply_markup=keyboard,
            parse_mode=enums.ParseMode.HTML
        )
        await callback_query.answer("Help menu opened!", show_alert=False)
    except Exception as e:
        await callback_query.answer(f"Error: {str(e)}", show_alert=True)


@app.on_callback_query(filters.regex("^help_commands$"))
@lang.language()
async def help_commands_handler(client, callback_query: CallbackQuery):
    """Display available commands list with styled danger back buttons."""
    try:
        commands_text = f"""
<b>Help</b>

🎵 <b>Music Commands:</b>
• /play - Play a song
• /pause - Pause playback
• /resume - Resume playback
• /skip - Skip to next song
• /stop - Stop playback
• /queue - View song queue

🎧 <b>Studio Mode:</b>
• /studio - Enter studio mode
• /studio effects - View audio effects

⚙️ <b>Settings:</b>
• /settings - Configure bot
• /playmode - Set play mode
"""

        back_button = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "← Back",
                    callback_data="help_menu",
                    style="danger"  # Red/Danger button background color
                )
            ]
        ])

        await callback_query.message.edit_text(
            text=commands_text,
            reply_markup=back_button,
            parse_mode=enums.ParseMode.HTML
        )
        await callback_query.answer()
    except Exception as e:
        await callback_query.answer(f"Error: {str(e)}", show_alert=True)
