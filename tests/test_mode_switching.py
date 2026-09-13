#!/usr/bin/env python3
"""Test script for mode-switching feature."""

from OpenHeartsMusic.core.calls import TgCall
from OpenHeartsMusic.helpers import AudioEffectManager
import asyncio
from types import SimpleNamespace

from hydrogram import raw


async def test_mode_switching():
    call_manager = TgCall()

    # Test 1: Audio FX state management
    print('Test 1: Audio FX State Management')
    print('  - get_audio_fx(123) before set:', call_manager.get_audio_fx(123))
    call_manager._audio_fx[123] = 'bassboost'
    print('  - get_audio_fx(123) after set:', call_manager.get_audio_fx(123))

    # Test 2: Karaoke mode state management
    print('\nTest 2: Karaoke Mode State Management')
    print('  - get_karaoke_mode(456) before set:', call_manager.get_karaoke_mode(456))
    call_manager._karaoke_modes[456] = 'standard'
    print('  - get_karaoke_mode(456) after set:', call_manager.get_karaoke_mode(456))

    # Test 3: Effect validation
    print('\nTest 3: Effect Validation')
    print('  - is_valid_effect("bassboost"):', AudioEffectManager.is_valid_effect('bassboost'))
    print('  - is_valid_effect("invalid_fx"):', AudioEffectManager.is_valid_effect('invalid_fx'))

    # Test 4: Available effects
    print('\nTest 4: Available Effects')
    effects = AudioEffectManager.list_effects()
    print(f'  - Available effects: {effects}')

    # Test 5: Filter retrieval
    print('\nTest 5: Effect Filter Strings')
    for effect in ['karaoke', 'bassboost', '8d', 'nightcore', 'lofi']:
        filter_str = AudioEffectManager.get_filter(effect)
        preview = filter_str[:50] + '...' if len(filter_str) > 50 else filter_str
        print(f'  - {effect}: {preview}')

    print('\n✅ All mode switching tests passed!')


async def test_karaoke_mode_restarts_active_stream():
    call_manager = TgCall()
    calls = {'restart': 0}

    async def fake_get_call(chat_id):
        return True

    async def fake_restart(chat_id):
        calls['restart'] += 1
        return True

    call_manager.restart_stream = fake_restart
    call_manager._karaoke_modes = {}
    call_manager._audio_fx = {}

    import OpenHeartsMusic.core.calls as calls_module
    original_get_call = calls_module.db.get_call
    calls_module.db.get_call = fake_get_call

    try:
        result = await call_manager.set_karaoke_mode(999, 'standard')
        assert result is True
        assert calls['restart'] == 1
        assert call_manager.get_karaoke_mode(999) == 'standard'
    finally:
        calls_module.db.get_call = original_get_call


async def test_video_stream_resyncs_after_assistant_unmute():
    call_manager = TgCall()
    import OpenHeartsMusic.core.calls as calls_module

    chat_id = 999
    assistant = SimpleNamespace()
    media = SimpleNamespace(video=True)
    resync_calls = []

    async def fake_get_assistant(value):
        return assistant

    async def fake_restart(value):
        resync_calls.append("restart")
        return True

    async def fake_pause(value):
        resync_calls.append("pause")

    async def fake_resume(value):
        resync_calls.append("resume")

    assistant.pause = fake_pause
    assistant.resume = fake_resume

    original_get_assistant = calls_module.db.get_assistant
    original_active_calls = calls_module.db.active_calls
    original_get_current = calls_module.queue.get_current
    calls_module.db.get_assistant = fake_get_assistant
    calls_module.db.active_calls = {chat_id: 1}
    calls_module.queue.get_current = lambda value: media
    call_manager.restart_stream = fake_restart

    def participant(muted):
        return raw.types.GroupCallParticipant(
            peer=raw.types.PeerUser(user_id=123), date=0, source=1, muted=muted
        )

    def update(muted):
        return raw.types.UpdateGroupCallParticipants(
            call=SimpleNamespace(), participants=[participant(muted)], version=1
        )

    try:
        # Telegram can report the assistant as unmuted without first sending
        # a muted=True update.
        await call_manager._handle_assistant_unmute(assistant, 123, update(False))
        await call_manager._handle_assistant_unmute(assistant, 123, update(True))
        await call_manager._handle_assistant_unmute(assistant, 123, update(False))
        await asyncio.sleep(1.3)
        assert resync_calls == ["restart", "pause", "resume"]
    finally:
        calls_module.db.get_assistant = original_get_assistant
        calls_module.db.active_calls = original_active_calls
        calls_module.queue.get_current = original_get_current


async def test_video_stream_restarts_when_pause_resume_fails():
    call_manager = TgCall()
    import OpenHeartsMusic.core.calls as calls_module

    chat_id = 1000
    assistant = SimpleNamespace()
    media = SimpleNamespace(video=True)
    calls = []

    async def fake_get_assistant(value):
        return assistant

    async def fake_restart(value):
        calls.append("restart")
        return True

    async def fake_pause(value):
        calls.append("pause")

    async def fake_resume(value):
        raise RuntimeError("simulated renegotiation failure")

    assistant.pause = fake_pause
    assistant.resume = fake_resume
    original_get_assistant = calls_module.db.get_assistant
    original_active_calls = calls_module.db.active_calls
    original_get_current = calls_module.queue.get_current
    calls_module.db.get_assistant = fake_get_assistant
    calls_module.db.active_calls = {chat_id: 1}
    calls_module.queue.get_current = lambda value: media
    call_manager.restart_stream = fake_restart

    def participant(muted):
        return raw.types.GroupCallParticipant(
            peer=raw.types.PeerUser(user_id=123), date=0, source=1, muted=muted
        )

    try:
        await call_manager._handle_assistant_unmute(
            assistant,
            123,
            raw.types.UpdateGroupCallParticipants(
                call=SimpleNamespace(), participants=[participant(False)], version=1
            ),
        )
        await asyncio.sleep(2.8)
        assert calls[:4] == ["restart", "pause", "restart", "pause"]
        assert len(calls) >= 4
    finally:
        calls_module.db.get_assistant = original_get_assistant
        calls_module.db.active_calls = original_active_calls
        calls_module.queue.get_current = original_get_current


if __name__ == "__main__":
    asyncio.run(test_mode_switching())
    asyncio.run(test_karaoke_mode_restarts_active_stream())
    asyncio.run(test_video_stream_resyncs_after_assistant_unmute())
    asyncio.run(test_video_stream_restarts_when_pause_resume_fails())
