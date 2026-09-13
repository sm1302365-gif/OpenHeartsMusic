import asyncio
import unittest
from unittest.mock import AsyncMock

from OpenHeartsMusic.core.calls import (
    AUTO_DELETE_CACHE,
    auto_clean_track_messages,
    register_msg_to_delete,
)
from OpenHeartsMusic.helpers._message_cleanup import (
    AUTO_DELETE_CACHE as HELPER_AUTO_DELETE_CACHE,
)


class DownloadCleanupTests(unittest.TestCase):
    def setUp(self):
        AUTO_DELETE_CACHE.clear()

    def test_register_and_auto_clean_track_messages_removes_cached_ids(self):
        register_msg_to_delete(123, 101)
        register_msg_to_delete(123, 102)

        client = AsyncMock()
        client.delete_messages = AsyncMock()

        asyncio.run(auto_clean_track_messages(client, 123))

        self.assertEqual(AUTO_DELETE_CACHE.get(123, []), [])
        client.delete_messages.assert_awaited_once_with(
            chat_id=123,
            message_ids=[101, 102],
            revoke=True,
        )

    def test_core_exports_use_new_cleanup_registry(self):
        self.assertIs(AUTO_DELETE_CACHE, HELPER_AUTO_DELETE_CACHE)


if __name__ == "__main__":
    unittest.main()
