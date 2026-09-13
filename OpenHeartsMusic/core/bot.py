# ==============================================================================
# bot.py - Main Bot Client Manager
# ==============================================================================
# This file manages the main Telegram bot client.
# Features:
# - Extends the Hydrogram client
# - Handles bot login and connection
# - Starts and stops the bot
# - Sets owner, logger, and sudo filters
# - Stores bot details
# ==============================================================================


import hydrogram
from typing import Optional

from OpenHeartsMusic import ROOT, config, logger
import re


SESSION_DIR = ROOT.parent


class Bot(hydrogram.Client):

    # This class sets up the bot and manages its startup and shutdown.


    def __init__(self):
        # Initialize the bot client.
        super().__init__(
            name="OpenHeartsMusic",
            workdir=str(SESSION_DIR),
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            bot_token=config.BOT_TOKEN,
            parse_mode=hydrogram.enums.ParseMode.HTML,
            max_concurrent_transmissions=7,
        )

        self.owner: int = int(config.OWNER_ID)
        self.logger: int | str = config.LOGGER_ID
        self.bl_users: hydrogram.filters.Filter = hydrogram.filters.user()
        self.sudoers: set[int] = {self.owner}  # Store sudo user IDs
        self.sudo_filter: hydrogram.filters.Filter = hydrogram.filters.user()
        self.refresh_sudo_filter()

        # These will be set after boot()
        self.id: Optional[int] = None
        self.name: Optional[str] = None
        self.username: Optional[str] = None
        self.mention: Optional[str] = None

    def refresh_sudo_filter(self) -> None:
        """Rebuild the sudo permission filter from the current sudo user set."""
        user_ids = sorted({int(uid) for uid in self.sudoers if uid is not None})
        # Handlers keep the filter object created during plugin registration.
        # Mutate that object so refreshes are visible to already-registered handlers.
        self.sudo_filter.clear()
        self.sudo_filter.update(user_ids)

    async def boot(self) -> None:

        # Start the bot and complete the setup.
        try:
            await super().start()
        except Exception as exc:
            message = str(exc).lower()
            if "database is locked" in message or "database is busy" in message:
                raise RuntimeError(
                    "Hydrogram session database is locked. Stop any other bot instance "
                    "using OpenHeartsMusic.session, then start the bot again."
                ) from exc
            raise

        # Set bot information
        self.id = self.me.id
        self.name = self.me.first_name
        self.username = self.me.username
        self.mention = self.me.mention

        # Verify logger group access without blocking startup.
        try:
            if not self.logger:
                logger.info("LOGGER_ID is not configured; logger notifications are disabled.")
            else:
                # Avoid resolving phone numbers (bots cannot use contacts.ResolvePhone).
                if isinstance(self.logger, str) and re.fullmatch(r"\+?\d+", self.logger):
                    logger.warning(
                        f"LOGGER_ID appears to be a phone number ({self.logger}); bots cannot message phone numbers. Skipping logger notifications."
                    )
                else:
                    await self.send_message(self.logger, "🤖 ʙᴏᴛ ꜱᴛᴀʀᴛᴇᴅ")
                member = await self.get_chat_member(self.logger, self.id)
                if member.status != hydrogram.enums.ChatMemberStatus.ADMINISTRATOR:
                    logger.warning(
                        f"Logger group {self.logger} is reachable but the bot is not an admin there."
                    )
                else:
                    logger.info(f"Logger group {self.logger} is available.")
        except Exception as ex:
            logger.warning(
                f"Logger group {self.logger} is unavailable or invalid: {ex}. "
                "Continuing without logger notifications."
            )

        logger.info(f"🤖 Bot started successfully as @{self.username}")

    async def exit(self) -> None:

        # Stop the bot.
        await super().stop()
        logger.info("🤖 Bot client stopped.")
