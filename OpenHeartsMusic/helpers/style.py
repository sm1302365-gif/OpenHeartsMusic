# ==============================================================================
# style.py - Dedicated Button Styles & Color Configurations
# ==============================================================================
# This file contains all color parameters, button style constants, and
# visual UI configurations for the bot.
# ==============================================================================

class ButtonStyle:
    """Standard style parameters for inline button background colors."""
    PRIMARY = "primary"       # Blue / Main action buttons (e.g., Start, Studio)
    SUCCESS = "success"       # Green / Positive actions (e.g., Enable, Help, Confirm)
    DANGER = "danger"         # Red / Warning or destructive actions (e.g., Stop, Delete, Back)


class CustomFonts:
    """Custom font styles and decorated text decorations (Lorian Xavien Style)."""
    START_STUDIO = "✨ sᴛᴜᴅɪᴏ ᴍᴏᴅᴇ"
    PLAYING_STUDIO = START_STUDIO
    HELP_BTN = "🛠 ʜᴇʟᴘ ᴍᴇɴᴜ"
    BACK_BTN = "« ʙᴀᴄᴋ"
    CLOSE_BTN = "ᴄʟᴏsᴇ ✕"

    # Status indicators
    ON = "🟢 ᴏɴ"
    OFF = "🔴 ᴏꜰꜰ"
