import asyncio
import importlib.util
import pathlib
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from hydrogram.errors import UserNotParticipant


asyncio.set_event_loop(asyncio.new_event_loop())

module_path = pathlib.Path(__file__).resolve().parents[1] / "OpenHeartsMusic" / "helpers" / "_assistant_invite.py"
spec = importlib.util.spec_from_file_location("assistant_invite_helper", module_path)
assistant_invite_helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assistant_invite_helper)
ensure_assistant_in_chat = assistant_invite_helper.ensure_assistant_in_chat


class AssistantInviteTests(unittest.TestCase):
    def test_invites_assistant_using_exported_link_when_not_member(self):
        async def run_test():
            app_client = AsyncMock()
            app_client.get_chat = AsyncMock(return_value=SimpleNamespace(invite_link=None))
            app_client.export_chat_invite_link = AsyncMock(return_value="https://t.me/joinchat/example")

            assistant_client = SimpleNamespace(
                id=123456,
                get_chat_member=AsyncMock(side_effect=UserNotParticipant),
                join_chat=AsyncMock(),
            )

            logger = SimpleNamespace(info=lambda *args, **kwargs: None, warning=lambda *args, **kwargs: None)
            result = await ensure_assistant_in_chat(app_client, assistant_client, -100123456, logger)

            self.assertTrue(result)
            assistant_client.join_chat.assert_awaited_once_with("https://t.me/joinchat/example")

        asyncio.get_event_loop().run_until_complete(run_test())

    def test_refreshes_expired_invite_link_before_retrying(self):
        async def run_test():
            app_client = AsyncMock()
            app_client.get_chat = AsyncMock(return_value=SimpleNamespace(invite_link="https://t.me/old-link"))
            app_client.export_chat_invite_link = AsyncMock(return_value="https://t.me/joinchat/fresh")

            assistant_client = SimpleNamespace(
                id=123456,
                get_chat_member=AsyncMock(side_effect=UserNotParticipant),
                join_chat=AsyncMock(side_effect=[Exception("INVITE_HASH_EXPIRED"), None]),
            )

            logger = SimpleNamespace(info=lambda *args, **kwargs: None, warning=lambda *args, **kwargs: None)
            result = await ensure_assistant_in_chat(app_client, assistant_client, -100123456, logger)

            self.assertTrue(result)
            self.assertEqual(assistant_client.join_chat.await_count, 2)
            self.assertEqual(assistant_client.join_chat.await_args_list[0].args[0], "https://t.me/old-link")
            self.assertEqual(assistant_client.join_chat.await_args_list[1].args[0], "https://t.me/joinchat/fresh")

        asyncio.get_event_loop().run_until_complete(run_test())

    def test_refreshes_link_on_generic_join_error(self):
        async def run_test():
            app_client = AsyncMock()
            app_client.get_chat = AsyncMock(return_value=SimpleNamespace(invite_link="https://t.me/old-link"))
            app_client.export_chat_invite_link = AsyncMock(return_value="https://t.me/joinchat/fresh")

            assistant_client = SimpleNamespace(
                id=123456,
                get_chat_member=AsyncMock(side_effect=[UserNotParticipant, UserNotParticipant, None]),
                join_chat=AsyncMock(side_effect=[Exception("CHAT_WRITE_FORBIDDEN"), None]),
            )

            logger = SimpleNamespace(info=lambda *args, **kwargs: None, warning=lambda *args, **kwargs: None)
            result = await ensure_assistant_in_chat(app_client, assistant_client, -100123456, logger)

            self.assertTrue(result)
            self.assertEqual(assistant_client.join_chat.await_count, 2)
            self.assertEqual(assistant_client.join_chat.await_args_list[0].args[0], "https://t.me/old-link")
            self.assertEqual(assistant_client.join_chat.await_args_list[1].args[0], "https://t.me/joinchat/fresh")

        asyncio.get_event_loop().run_until_complete(run_test())

    def test_accepts_pytgcalls_wrapper_by_unwrapping_hydrogram_client(self):
        async def run_test():
            app_client = AsyncMock()
            app_client.get_chat = AsyncMock(return_value=SimpleNamespace(invite_link="https://t.me/joinchat/example"))

            real_assistant = SimpleNamespace(
                id=123456,
                get_chat_member=AsyncMock(side_effect=UserNotParticipant),
                join_chat=AsyncMock(),
            )
            wrapped_assistant = SimpleNamespace(mtproto_client=real_assistant)

            logger = SimpleNamespace(info=lambda *args, **kwargs: None, warning=lambda *args, **kwargs: None)
            result = await ensure_assistant_in_chat(app_client, wrapped_assistant, -100123456, logger)

            self.assertTrue(result)
            real_assistant.join_chat.assert_awaited_once_with("https://t.me/joinchat/example")

        asyncio.get_event_loop().run_until_complete(run_test())

    def test_treats_channel_private_as_not_joined(self):
        async def run_test():
            app_client = AsyncMock()
            app_client.get_chat = AsyncMock(return_value=SimpleNamespace(invite_link="https://t.me/joinchat/example"))

            class ChannelPrivateError(Exception):
                code = 406

            def channel_private_error(*args, **kwargs):
                raise ChannelPrivateError("Telegram says: [406 CHANNEL_PRIVATE] - The channel/supergroup is not accessible (caused by \"channels.GetParticipant\")")

            real_assistant = SimpleNamespace(
                id=123456,
                get_chat_member=AsyncMock(side_effect=channel_private_error),
                join_chat=AsyncMock(),
            )

            logger = SimpleNamespace(info=lambda *args, **kwargs: None, warning=lambda *args, **kwargs: None)
            result = await ensure_assistant_in_chat(app_client, real_assistant, -100123456, logger)

            self.assertTrue(result)
            real_assistant.join_chat.assert_awaited_once_with("https://t.me/joinchat/example")

        asyncio.get_event_loop().run_until_complete(run_test())


if __name__ == "__main__":
    unittest.main()
