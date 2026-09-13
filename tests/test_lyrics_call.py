import asyncio
import os
import sys

# Ensure project root is importable when run from workspace root
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from OpenHeartsMusic.plugins.utilities.lyrics import get_synced_lyrics

async def main():
    artist = "Adele"
    title = "Hello"
    print(f"Querying synced lyrics for: {artist} - {title}")
    lyrics = await get_synced_lyrics(artist, title)
    print("Result lines:", len(lyrics))
    for t, line in lyrics[:20]:
        print(f"{t:.2f}s -> {line}")

if __name__ == '__main__':
    asyncio.run(main())
