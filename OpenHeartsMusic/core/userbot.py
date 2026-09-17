# ==============================================================================
# userbot.py - Assistant/Userbot Client Manager
# ==============================================================================
# This file manages assistant accounts (userbots) that join voice chats to play music.
# Assistants are user accounts (not bots) that can join and stream audio/video.
# You can configure up to 3 assistants using SESSION1, SESSION2, SESSION3 variables.
# ==============================================================================

from hydrogram import Client

from OpenHeartsMusic import ROOT, config, logger


SESSION_DIR = ROOT.parent


class Userbot(Client):
    def __init__(self):
        """
        Initialize userbot with multiple assistant clients.

        Creates up to 3 assistant clients based on available session strings.
        Each assistant can independently join voice chats and stream music.
        More assistants = ability to serve more groups simultaneously.
        """
        self.clients = []  # List to store all active assistant clients

        # Map of client names to their session string config keys
        clients = {"one": "SESSION1", "two": "SESSION2", "three": "SESSION3"}

        # Create a Hydrogram client for each configured session
        for key, string_key in clients.items():
            # Unique name: HasiiTuneUB1, HasiiTuneUB2, etc.
            name = f"HasiiTuneUB{key[-1]}"
            # Get session string from config
            session = getattr(config, string_key)

            # Create and attach the client as an attribute (self.one, self.two, self.three)
            setattr(
                self,
                key,
                Client(
                    name=name,
                    workdir=str(SESSION_DIR),
                    api_id=config.API_ID,
                    api_hash=config.API_HASH,
                    session_string=session,  # Hydrogram session string
                ),
            )

    async def boot_client(self, num: int, ub: Client):
        """
        Boot a client and perform initial setup.
        Args:
            num (int): The client number to boot (1, 2, or 3).
            ub (Client): The userbot client instance.
        Raises:
            SystemExit: If the client fails to send a message in the log group.
        """
        clients = {
            1: self.one,
            2: self.two,
            3: self.three,
        }
        client = clients[num]
        try:
            await client.start()
        except Exception as e:
            logger.error(f"❌ Assistant {num} failed to start: {e}")
            logger.error(f"   This could be due to:")
            logger.error(f"   • Invalid session string (STRING_SESSION{num})")
            logger.error(f"   • Session logged out from another device")
            logger.error(f"   • Network/connectivity issues")
            return  # Don't raise SystemExit, just skip this assistant

        # Assistant startup logger notifications are disabled to prevent phone-number lookup failures.
        # Previously this could cause Telegram errors like PHONE_NOT_OCCUPIED when LOGGER_ID was invalid.

        client.id = client.me.id if hasattr(
            client, 'me') and client.me else None
        client.name = client.me.first_name if hasattr(
            client, 'me') and client.me else f"Assistant{num}"
        client.username = client.me.username if hasattr(
            client, 'me') and client.me else None
        client.mention = client.me.mention if hasattr(
            client, 'me') and client.me else client.name
        self.clients.append(client)
        logger.info(f"👤 Assistant {num} started as @{client.username}")

    async def boot(self):
        """
        Asynchronously starts the assistants.
        """
        configured = (
            (1, config.SESSION1, self.one),
            (2, config.SESSION2, self.two),
            (3, config.SESSION3, self.three),
        )
        seen_sessions = set()
        for number, session, client in configured:
            session = (session or "").strip()
            if not session:
                continue
            if session in seen_sessions:
                logger.warning(
                    "Skipping assistant %s: its session is already used by another assistant.",
                    number,
                )
                continue
            seen_sessions.add(session)
            await self.boot_client(number, client)

    async def exit(self):
        """
        Asynchronously stops the assistants.
        """
        try:
            if config.SESSION1 and hasattr(self.one, 'is_connected') and self.one.is_connected:
                await self.one.stop()
        except Exception as e:
            logger.warning(f"Error stopping assistant 1: {e}")

        try:
            if config.SESSION2 and hasattr(self.two, 'is_connected') and self.two.is_connected:
                await self.two.stop()
        except Exception as e:
            logger.warning(f"Error stopping assistant 2: {e}")

        try:
            if config.SESSION3 and hasattr(self.three, 'is_connected') and self.three.is_connected:
                await self.three.stop()
        except Exception as e:
            logger.warning(f"Error stopping assistant 3: {e}")

        logger.info("Assistants stopped.")
