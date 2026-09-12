# OpenHearts Music

A modern Telegram music bot for streaming audio in group voice chats. This project uses Python, Hydrogram, PyTgCalls, yt-dlp, FFmpeg, and MongoDB to provide a polished music playback experience inside Telegram groups and channels.

## Overview

OpenHearts Music is built to help communities play music in Telegram voice chats with minimal setup. It supports music search and direct links, playback controls, queue management, admin moderation, autoplay, and optional voice effects. The bot also includes a userbot assistant flow for joining calls and streaming media to Telegram voice chats.

## Features

- Play music from YouTube URLs and search queries
- Join and stream audio in Telegram voice chats
- Queue, skip, pause, resume, stop, and seek controls
- Admin and owner utilities for moderation and bot management
- Auto-play and queue limit controls
- Welcome and startup configuration support
- Optional video playback features
- Thumbnail generation for now-playing metadata
- MongoDB-backed bot data storage
- Docker and Docker Compose deployment support
- Audio effect presets for karaoke, studio, bass, and more

## Tech Stack

- Python 3.10+
- Hydrogram
- PyTgCalls
- yt-dlp
- FFmpeg and ffprobe
- MongoDB via Motor
- Pillow and PilMoji
- Docker
- Spotipy and related libraries

## Project Structure

```text
OpenHeartsMusic main/
├── OpenHeartsMusic/
│   ├── __init__.py
│   ├── __main__.py
│   ├── compat.py
│   ├── core/
│   │   ├── bot.py
│   │   ├── call_manager.py
│   │   ├── calls.py
│   │   ├── dir.py
│   │   ├── lang.py
│   │   ├── mongo.py
│   │   ├── preload.py
│   │   ├── telegram.py
│   │   ├── userbot.py
│   │   └── youtube.py
│   ├── helpers/
│   │   ├── _play.py
│   │   ├── _queue.py
│   │   ├── _thumbnails.py
│   │   ├── _track_manager.py
│   │   ├── nowplaying.py
│   │   └── ...
│   ├── plugins/
│   │   ├── admin/
│   │   ├── events/
│   │   ├── games/
│   │   ├── info/
│   │   ├── playback/
│   │   ├── settings/
│   │   └── utilities/
│   └── locales/
├── config.py
├── sample.env
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── start
├── Readme.md
├── MASTER_DOCUMENTATION.md
├── LICENSE
├── tests/
├── downloads/
└── .env
```

## Requirements

Before running the bot, make sure you have:

- Python 3.10 or newer
- FFmpeg and ffprobe installed and available on PATH
- A MongoDB database connection
- Telegram API credentials from my.telegram.org
- A bot token from BotFather
- A Hydrogram session string for the assistant account
- Git
- Optional: Docker for containerized deployment

## Installation

### 1. Clone the repository

```bash
git clone <your-repository-url>
cd "OpenHeartsMusic main"
```

### 2. Create a virtual environment

```bash
python -m venv venv
```

On Windows:

```powershell
venv\Scripts\activate
```

On Linux or macOS:

```bash
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Copy the sample file and fill in your values:

```bash
copy sample.env .env
```

Then edit the .env file with your actual Telegram API credentials, bot token, database URL, owner ID, and assistant session.

Example values:

```env
API_ID=12345678
API_HASH=your_api_hash
BOT_TOKEN=your_bot_token
MONGO_DB_URI=mongodb+//user:password@cluster.mongodb.net/
OWNER_ID=123456789
LOG_CHANNEL=123456789
LOGGER_ID=123456789
STRING_SESSION=your_hydrogram_session
COOKIE_URL=
```

See sample.env for all optional feature flags such as autoplay, welcome messages, custom thumbnails, and video playback toggles.

## Running the Bot

### Local run

```bash
python -m OpenHeartsMusic
```

Or use the included start script:

```bash
bash start
```

### Docker run

```bash
docker build -t openheartsmusic:latest .
docker run -d --restart unless-stopped --env-file .env -v ./OpenHeartsMusic/cookies:/app/OpenHeartsMusic/cookies -v ./downloads:/app/downloads --name openheartsmusic openheartsmusic:latest
```

### Docker Compose

```bash
docker compose up -d --build
```

To follow logs:

```bash
docker compose logs -f
```

## Important Notes

- Keep your .env file private. Do not commit it to version control.
- FFmpeg and ffprobe must be installed and available on PATH.
- The assistant session is required so the bot can join Telegram voice chats and stream audio.
- The project uses MongoDB for bot state and configuration.
- Some features such as age-restricted media access may depend on valid YouTube cookie URLs.

## Typical Bot Commands

This bot includes a plugin-based command system. Common commands may include:

- /play
- /pause
- /resume
- /skip
- /stop
- /queue
- /seek
- /vplay
- /help
- /ping

The exact command list can vary by deployment and plugin configuration.

## Development Notes

- Main entry point: OpenHeartsMusic/__main__.py
- Bot configuration: config.py
- Runtime setup: OpenHeartsMusic/core/
- Helper functions and playback logic: OpenHeartsMusic/helpers/
- Telegram behavior and command modules: OpenHeartsMusic/plugins/
- Tests: tests/

## License

This project is licensed under the GNU General Public License v3.0. See the LICENSE file in this repository for full license details.

## Support

For issues, questions, or feature requests, use the repository issue tracker and the project support channels defined in the bot configuration.

## Disclaimer

This software is intended for lawful, personal, and community use. Please comply with Telegram, YouTube, and other platform terms when using streaming and media features.
