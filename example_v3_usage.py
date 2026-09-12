"""
Example: OpenHeartsMusic with PyTgCalls v3 and CallManager

This script demonstrates using the new CallManager wrapper for PyTgCalls v3.
The CallManager provides a simplified interface for voice chat operations:
- join_call()    : Stream audio with optional audio filters
- pause_stream() : Pause the current stream
- resume_stream(): Resume paused stream
- leave_call()   : Leave the voice chat
"""

import asyncio
import os
from hydrogram import Client
from OpenHeartsMusic.core.call_manager import CallManager

# Load credentials from environment (or configure directly)
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")


async def main():
    """Initialize Hydrogram and PyTgCalls v3 client."""

    # Initialize Hydrogram client
    app = Client(
        "OpenHeartsMusic",
        api_id=API_ID,
        api_hash=API_HASH,
        bot_token=BOT_TOKEN,
    )

    # Initialize CallManager with PyTgCalls v3
    call_manager = CallManager(app)

    try:
        print("🚀 Starting Telegram Bot...")
        await app.start()
        print("✅ Bot started successfully!")

        print("📞 Starting PyTgCalls v3 Client...")
        await call_manager.start()
        print("✅ PyTgCalls v3 started successfully!")

        # Example: Join a voice call and stream audio with karaoke filter
        chat_id = -1001234567890  # Replace with your chat ID
        audio_file = "/path/to/audio.mp3"
        karaoke_filter = "pan=stereo|c0=0.5*c0-0.5*c1|c1=0.5*c1-0.5*c0"  # Vocal removal

        try:
            print(f"📻 Joining voice chat {chat_id}...")
            await call_manager.join_call(
                chat_id=chat_id,
                file_path=audio_file,
                audio_filter=karaoke_filter,  # Optional: apply karaoke filter
            )
            print("✅ Streaming audio...")

            # Simulate some operations
            await asyncio.sleep(5)
            print("⏸  Pausing stream...")
            await call_manager.pause_stream(chat_id)

            await asyncio.sleep(3)
            print("▶️  Resuming stream...")
            await call_manager.resume_stream(chat_id)

            await asyncio.sleep(10)
            print("👋 Leaving call...")
            await call_manager.leave_call(chat_id)

        except Exception as e:
            print(f"❌ Error during streaming: {e}")

        print("✨ All operations completed!")
        await asyncio.Event().wait()

    except KeyboardInterrupt:
        print("\n⏹  Shutting down...")
    finally:
        await app.stop()
        print("✅ Bot stopped successfully!")


if __name__ == "__main__":
    asyncio.run(main())
