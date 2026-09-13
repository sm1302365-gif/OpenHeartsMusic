# ==============================================================================
# mongo.py - MongoDB Database Manager
# ==============================================================================
# This file handles all database operations using MongoDB.
# Collections:
# - users: User data (sudo users)
# - chats: Group/chat data (language, channel play mode, authorized users)
# - blacklist: Blacklisted users/chats
# - calls: Active voice call sessions
# - cache: Admin list cache
#
# Features:
# - Async MongoDB operations for better performance
# - Connection pooling for efficiency
# - Admin list caching to reduce database queries
# - Random assistant selection for load balancing
# ==============================================================================

from random import randint
from time import time
import asyncio
import logging

try:
    from motor.motor_asyncio import AsyncIOMotorClient as AsyncMongoClient
except Exception as e:
    raise RuntimeError(
        "Missing dependency 'motor'. Install it with: pip install motor"
    ) from e

from OpenHeartsMusic import config, logger, userbot


# Suppress non-critical MongoDB background task errors
class MongoBackgroundFilter(logging.Filter):
    def filter(self, record):
        # Suppress AutoReconnect and _OperationCancelled background errors (these are handled internally)
        msg = record.getMessage()
        return not (
            'MongoClient background task encountered an error' in msg or
            ('AutoReconnect' in msg and 'background task' in msg) or
            ('_OperationCancelled' in msg and 'background task' in msg)
        )

logging.getLogger('pymongo.client').addFilter(MongoBackgroundFilter())


class MongoDB:
    def __init__(self):
        """
        Initialize the MongoDB connection.
        """
        self.mongo = AsyncMongoClient(
            config.MONGO_URL,
            serverSelectionTimeoutMS=12500,
            connectTimeoutMS=20000,
            socketTimeoutMS=20000,
            maxPoolSize=20,  # Reduced from 50 to prevent too many open connections
            minPoolSize=5,   # Reduced from 10 to prevent too many open connections
            maxIdleTimeMS=30000,  # Reduced from 45000 - close idle connections faster
            waitQueueTimeoutMS=10000,
            retryWrites=True,
            retryReads=True
        )
        self.db = self.mongo.OpenHeartsMusic

        self.admin_list = {}  # Cache admin lists
        self.admin_cache_time = {}  # Track cache freshness
        self.active_calls = {}
        self.blacklisted = []
        self.notified = []
        self.cache = self.db.cache
        self.logger = False
        self.vplay_enabled = config.VIDEO_PLAY

        self.assistant = {}
        self.assistantdb = self.db.assistant

        self.auth = {}
        self.authdb = self.db.auth

        self.chats = []
        self.chatsdb = self.db.chats

        self.lang = {}
        self.langdb = self.db.lang

        self.play_mode = []
        self.playmodedb = self.db.play

        self.autoplay = {}

        self.users = []
        self.usersdb = self.db.users

        self.cleanerdb = self.db.cleaner

    async def connect(self) -> None:
        """Check if we can connect to the database with exponential backoff retry logic.

        Raises:
            SystemExit: If the connection to the database fails after retries.
        """
        max_retries = 3
        retry_delay = 5  # Initial delay in seconds

        for attempt in range(1, max_retries + 1):
            try:
                start = time()
                await self.mongo.admin.command("ping")
                logger.info(
                    f"✅ Database connection successful. ({time() - start:.2f}s)")

                # Create indexes for faster queries
                await self.authdb.create_index("_id")
                await self.langdb.create_index("_id")
                await self.cache.create_index("_id")

                await self.load_cache()
                return  # Success, exit the function
            except Exception as e:
                if attempt < max_retries:
                    # Exponential backoff: 5s, 10s, 20s
                    wait_time = retry_delay * (2 ** (attempt - 1))
                    logger.warning(f"Database connection attempt {attempt}/{max_retries} failed: {type(e).__name__}. Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    raise SystemExit(
                        f"Database connection failed after {max_retries} attempts: {type(e).__name__}") from e

    async def close(self) -> None:
        """Close the connection to the database."""
        # motor's AsyncIOMotorClient.close() is a synchronous call that returns None;
        # awaiting it raises TypeError: 'NoneType' object can't be awaited. Call
        # it directly to close connections.
        try:
            self.mongo.close()
        except Exception as e:
            logger.debug(f"Error while closing MongoDB client: {e}")
        logger.info("Database connection closed.")

    # AUTO-CLEANER
    async def is_cleaner_enabled(self, chat_id: int) -> bool:
        document = await self.cleanerdb.find_one({"_id": chat_id})
        return bool(document and document.get("status", False))

    async def set_cleaner_status(self, chat_id: int, status: bool) -> None:
        await self.cleanerdb.update_one(
            {"_id": chat_id},
            {"$set": {"status": status}},
            upsert=True,
        )

    # CACHE
    async def get_call(self, chat_id: int) -> bool:
        return chat_id in self.active_calls

    async def add_call(self, chat_id: int) -> None:
        self.active_calls[chat_id] = 1

    async def remove_call(self, chat_id: int) -> None:
        self.active_calls.pop(chat_id, None)

    async def playing(self, chat_id: int, paused: bool = None) -> bool | None:
        if paused is not None:
            self.active_calls[chat_id] = int(not paused)
        return bool(self.active_calls[chat_id])

    async def get_admins(self, chat_id: int, reload: bool = False) -> list[int]:
        from OpenHeartsMusic.helpers._admins import reload_admins

        # **PERFORMANCE FIX**: Increased cache from 5 to 15 minutes
        # Reduces MongoDB queries during peak load (15-20 concurrent streams)
        current_time = time()
        cache_age = current_time - self.admin_cache_time.get(chat_id, 0)

        if chat_id not in self.admin_list or reload or cache_age > 900:  # 15 minutes
            self.admin_list[chat_id] = await reload_admins(chat_id)
            self.admin_cache_time[chat_id] = current_time
        return self.admin_list[chat_id]

    # AUTH METHODS
    async def _get_auth(self, chat_id: int) -> set[int]:
        if chat_id not in self.auth:
            doc = await self.authdb.find_one({"_id": chat_id}) or {}
            self.auth[chat_id] = set(doc.get("user_ids", []))
        return self.auth[chat_id]

    async def is_auth(self, chat_id: int, user_id: int) -> bool:
        return user_id in await self._get_auth(chat_id)

    async def add_auth(self, chat_id: int, user_id: int) -> None:
        users = await self._get_auth(chat_id)
        if user_id not in users:
            users.add(user_id)
            await self.authdb.update_one(
                {"_id": chat_id}, {"$addToSet": {"user_ids": user_id}}, upsert=True
            )

    async def rm_auth(self, chat_id: int, user_id: int) -> None:
        users = await self._get_auth(chat_id)
        if user_id in users:
            users.discard(user_id)
            await self.authdb.update_one(
                {"_id": chat_id}, {"$pull": {"user_ids": user_id}}
            )

    # ASSISTANT METHODS
    async def set_assistant(self, chat_id: int) -> int:
        from OpenHeartsMusic import tune

        total_clients = len(tune.clients) or len(userbot.clients)
        if total_clients == 0:
            raise RuntimeError("No assistant sessions are available.")

        num = randint(1, total_clients)
        await self.assistantdb.update_one(
            {"_id": chat_id},
            {"$set": {"num": num}},
            upsert=True,
        )
        self.assistant[chat_id] = num
        return num

    async def get_assistant(self, chat_id: int):
        from OpenHeartsMusic import tune

        if chat_id not in self.assistant:
            doc = await self.assistantdb.find_one({"_id": chat_id})
            num = doc["num"] if doc else await self.set_assistant(chat_id)
            self.assistant[chat_id] = num

        total_clients = len(tune.clients) or len(userbot.clients)
        if total_clients == 0:
            raise RuntimeError("No assistant sessions are available.")

        if self.assistant[chat_id] < 1 or self.assistant[chat_id] > total_clients:
            num = await self.set_assistant(chat_id)
            self.assistant[chat_id] = num

        if self.assistant[chat_id] - 1 < len(tune.clients):
            return tune.clients[self.assistant[chat_id] - 1]

        # Fallback to any available PyTgCalls client if the selected one is missing
        if tune.clients:
            num = min(self.assistant[chat_id], len(tune.clients))
            self.assistant[chat_id] = num
            await self.assistantdb.update_one(
                {"_id": chat_id},
                {"$set": {"num": num}},
                upsert=True,
            )
            return tune.clients[num - 1]

        raise RuntimeError("No PyTgCalls assistant client is available.")

    async def get_client(self, chat_id: int):
        if chat_id not in self.assistant:
            await self.get_assistant(chat_id)

        if self.assistant[chat_id] < 1 or self.assistant[chat_id] > len(userbot.clients):
            await self.set_assistant(chat_id)

        # Get available clients dynamically based on what's actually running
        available_clients = {}
        if hasattr(userbot, 'one') and userbot.one in userbot.clients:
            available_clients[1] = userbot.one
        if hasattr(userbot, 'two') and userbot.two in userbot.clients:
            available_clients[2] = userbot.two
        if hasattr(userbot, 'three') and userbot.three in userbot.clients:
            available_clients[3] = userbot.three

        client = available_clients.get(self.assistant[chat_id])
        if client:
            return client

        # Fallback to first available assistant if the assigned one is missing
        if available_clients:
            num, client = next(iter(available_clients.items()))
            self.assistant[chat_id] = num
            await self.assistantdb.update_one(
                {"_id": chat_id},
                {"$set": {"num": num}},
                upsert=True,
            )
            return client

        return None

    # BLACKLIST METHODS
    async def add_blacklist(self, chat_id: int) -> None:
        if str(chat_id).startswith("-"):
            self.blacklisted.append(chat_id)
            return await self.cache.update_one(
                {"_id": "bl_chats"}, {"$addToSet": {"chat_ids": chat_id}}, upsert=True
            )
        await self.cache.update_one(
            {"_id": "bl_users"}, {"$addToSet": {"user_ids": chat_id}}, upsert=True
        )

    async def del_blacklist(self, chat_id: int) -> None:
        if str(chat_id).startswith("-"):
            self.blacklisted.remove(chat_id)
            return await self.cache.update_one(
                {"_id": "bl_chats"},
                {"$pull": {"chat_ids": chat_id}},
            )
        await self.cache.update_one(
            {"_id": "bl_users"},
            {"$pull": {"user_ids": chat_id}},
        )

    async def get_blacklisted(self, chat: bool = False) -> list[int]:
        if chat:
            if not self.blacklisted:
                doc = await self.cache.find_one({"_id": "bl_chats"})
                self.blacklisted.extend(doc.get("chat_ids", []) if doc else [])
            return self.blacklisted
        doc = await self.cache.find_one({"_id": "bl_users"})
        return doc.get("user_ids", []) if doc else []

    # CHAT METHODS
    async def is_chat(self, chat_id: int) -> bool:
        return chat_id in self.chats

    async def add_chat(self, chat_id: int) -> None:
        if not await self.is_chat(chat_id):
            self.chats.append(chat_id)
            await self.chatsdb.insert_one({"_id": chat_id})

    async def rm_chat(self, chat_id: int) -> None:
        if await self.is_chat(chat_id):
            self.chats.remove(chat_id)
            await self.chatsdb.delete_one({"_id": chat_id})

    async def get_chats(self) -> list:
        if not self.chats:
            self.chats.extend([chat["_id"] async for chat in self.chatsdb.find()])
        return self.chats

    # LANGUAGE METHODS
    async def set_lang(self, chat_id: int, lang_code: str):
        await self.langdb.update_one(
            {"_id": chat_id},
            {"$set": {"lang": lang_code}},
            upsert=True,
        )
        self.lang[chat_id] = lang_code

    async def get_lang(self, chat_id: int) -> str:
        if chat_id not in self.lang:
            doc = await self.langdb.find_one({"_id": chat_id})
            self.lang[chat_id] = doc["lang"] if doc else "en"
        return self.lang[chat_id]

    # VPLAY TOGGLE METHODS
    async def get_vplay_enabled(self) -> bool:
        """Check if /vplay commands are enabled."""
        doc = await self.cache.find_one({"_id": "vplay_toggle"})
        if doc is not None:
            self.vplay_enabled = bool(doc.get("enabled", config.VIDEO_PLAY))
        else:
            self.vplay_enabled = config.VIDEO_PLAY
        return self.vplay_enabled

    async def set_vplay_enabled(self, enabled: bool) -> None:
        """Enable or disable /vplay commands globally."""
        self.vplay_enabled = bool(enabled)
        await self.cache.update_one(
            {"_id": "vplay_toggle"},
            {"$set": {"enabled": self.vplay_enabled}},
            upsert=True,
        )



    # LOGGER METHODS
    async def is_logger(self) -> bool:
        return self.logger

    async def get_logger(self) -> bool:
        doc = await self.cache.find_one({"_id": "logger"})
        if doc:
            self.logger = doc["status"]
        return self.logger

    async def set_logger(self, status: bool) -> None:
        self.logger = status
        await self.cache.update_one(
            {"_id": "logger"},
            {"$set": {"status": status}},
            upsert=True,
        )



    # AUTO LEAVE METHODS
    async def get_autoleave(self, chat_id: int) -> bool:
        """Get auto-leave status for a chat. Default is False."""
        doc = await self.cache.find_one({"_id": f"autoleave_{chat_id}"})
        return doc.get("enabled", False) if doc else False

    async def set_autoleave(self, chat_id: int, enabled: bool) -> None:
        """Enable or disable auto-leave for a chat."""
        await self.cache.update_one(
            {"_id": f"autoleave_{chat_id}"},
            {"$set": {"enabled": enabled}},
            upsert=True,
        )

    # LOOP MODE METHODS
    async def get_loop(self, chat_id: int) -> int:
        """Get loop mode for a chat. 0=off, 1=single, 10=queue"""
        doc = await self.cache.find_one({"_id": f"loop_{chat_id}"})
        return doc.get("mode", 0) if doc else 0

    async def set_loop(self, chat_id: int, mode: int) -> None:
        """Set loop mode for a chat."""
        if mode == 0:
            await self.cache.delete_one({"_id": f"loop_{chat_id}"})
        else:
            await self.cache.update_one(
                {"_id": f"loop_{chat_id}"},
                {"$set": {"mode": mode}},
                upsert=True,
            )

    # PLAY MODE METHODS
    async def get_play_mode(self, chat_id: int) -> bool:
        if chat_id not in self.play_mode:
            doc = await self.playmodedb.find_one({"_id": chat_id})
            if doc:
                self.play_mode.append(chat_id)
        return chat_id in self.play_mode

    async def set_play_mode(self, chat_id: int, remove: bool = False) -> None:
        if remove:
            self.play_mode.remove(chat_id)
            await self.playmodedb.delete_one({"_id": chat_id})
        else:
            self.play_mode.append(chat_id)
            await self.playmodedb.insert_one({"_id": chat_id})

    async def get_autoplay(self, chat_id: int) -> bool:
        """Get autoplay state for a chat, defaulting to False when unset."""
        if chat_id not in self.autoplay:
            doc = await self.cache.find_one({"_id": f"autoplay_{chat_id}"})
            self.autoplay[chat_id] = bool(doc.get("enabled", False)) if doc else False
        return self.autoplay[chat_id]

    async def set_autoplay(self, chat_id: int, enabled: bool) -> None:
        self.autoplay[chat_id] = enabled
        if not enabled:
            await self.cache.delete_one({"_id": f"autoplay_{chat_id}"})
        else:
            await self.cache.update_one(
                {"_id": f"autoplay_{chat_id}"},
                {"$set": {"enabled": enabled}},
                upsert=True,
            )

    # SUDO METHODS
    async def add_sudo(self, user_id: int) -> None:
        await self.cache.update_one(
            {"_id": "sudoers"}, {"$addToSet": {"user_ids": user_id}}, upsert=True
        )

    async def del_sudo(self, user_id: int) -> None:
        await self.cache.update_one(
            {"_id": "sudoers"}, {"$pull": {"user_ids": user_id}}
        )

    async def get_sudoers(self) -> list[int]:
        doc = await self.cache.find_one({"_id": "sudoers"})
        return doc.get("user_ids", []) if doc else []

    # USER METHODS
    async def is_user(self, user_id: int) -> bool:
        return user_id in self.users

    async def add_user(self, user_id: int) -> None:
        if not await self.is_user(user_id):
            self.users.append(user_id)
            await self.usersdb.insert_one({"_id": user_id})

    async def rm_user(self, user_id: int) -> None:
        if await self.is_user(user_id):
            self.users.remove(user_id)
            await self.usersdb.delete_one({"_id": user_id})

    async def get_users(self) -> list:
        if not self.users:
            self.users.extend([user["_id"] async for user in self.usersdb.find()])
        return self.users


    async def load_cache(self) -> None:
        """Preload cache data from database for faster access."""


        # Preload all cache data
        logger.info("📦 Loading database cache...")

        # Load chats, users, blacklists, and logger status
        await self.get_chats()
        await self.get_users()
        await self.get_blacklisted(chat=True)  # Load blacklisted chats
        await self.get_logger()
        # Autoplay and vplay states are handled dynamically.

        # Preload sudoers list
        await self.get_sudoers()

        logger.info(f"✅ Cache loaded: {len(self.chats)} chats, {len(self.users)} users, {len(self.blacklisted)} blacklisted.")
