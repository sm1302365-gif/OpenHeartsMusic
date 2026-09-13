# ==============================================================================
# dicegame.py - Simple Dice Game
# ==============================================================================
# Minimal game plugin to restore expected plugin inventory and gameplay commands.
# ==============================================================================

from hydrogram import filters, types

from OpenHeartsMusic import app

DICE_EMOJIS = {
    "dice": "🎲",
    "dart": "🎯",
    "basket": "🏀",
    "ball": "⚽",
    "football": "⚽",
    "jackpot": "🎰",
}


@app.on_message(filters.command(["dice", "dart", "basket", "ball", "football", "jackpot"]) & filters.group & ~app.bl_users)
async def dice_game(_, message: types.Message):
    command = (message.command[0] or "dice").lower()
    emoji = DICE_EMOJIS.get(command, "🎲")
    await app.send_dice(message.chat.id, emoji=emoji)
