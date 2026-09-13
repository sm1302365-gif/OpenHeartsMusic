# OpenHearts Music
<br>

[[Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[[License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg?style=for-the-badge)](LICENSE)
[[Telegram Channel](https://t.me/ShreyanshMusicSupport)(https://t.me/Shreyansh_Raghuvanshi)
[[Telegram Support](https://t.me/+jLpKEtUuhyNlODA1)

<img width="640" height="640" alt="Image" src="https://github.com/user-attachments/assets/a29b1c0b-3198-4da1-8448-39c21dda3d40"/>


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

Before deploying **OpenHearts Music**, ensure your system has:

- Python 3.10 or newer
- FFmpeg and ffprobe available on PATH
- A MongoDB Atlas or self-hosted database
- Telegram API credentials from [my.telegram.org](https://my.telegram.org)
- A bot token from [@BotFather](https://t.me/BotFather)
- At least one Hydrogram assistant session string
- Git
- Optional: Docker and Docker Compose

---

# 🚀 Quick Start

Clone the repository and enter its directory.

```bash
git clone <your-repository-url>
cd "OpenHeartsMusic main"
```

Create a virtual environment and install dependencies.

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

On Windows PowerShell, activate the environment with:

```powershell
venv\Scripts\Activate.ps1
```

Create your environment configuration.

```bash
cp sample.env .env
```

On Windows PowerShell, use `Copy-Item sample.env .env` instead. Fill in the required values, then start the bot:

```bash
python -m OpenHeartsMusic
```

You can also use the included start script:

```bash
bash start
```

---

# ⚙️ Environment Variables

Create a `.env` file in the project root and configure the required values.

```env
# Telegram API
API_ID=
API_HASH=
BOT_TOKEN=

# MongoDB and logging
MONGO_DB_URI=
LOGGER_ID=
OWNER_ID=

# Assistant accounts
STRING_SESSION1=
STRING_SESSION2=
STRING_SESSION3=

# Optional features
AUTO_PLAY=False
WELCOME_ENABLED=True
AUTO_END=False
AUTO_LEAVE=False
THUMB_GEN=True
VIDEO_PLAY=True
QUEUE_LIMIT=30
PLAYLIST_LIMIT=20
COOKIE_URL=
```

| Variable | Description |
|----------|-------------|
| `API_ID` | Telegram API ID from my.telegram.org |
| `API_HASH` | Telegram API hash |
| `BOT_TOKEN` | Token received from @BotFather |
| `MONGO_DB_URI` | MongoDB connection URI |
| `LOGGER_ID` | Group or channel ID used for bot logs |
| `OWNER_ID` | Telegram user ID of the bot owner |
| `STRING_SESSION1` | Primary Hydrogram assistant session |
| `STRING_SESSION2` | Optional second assistant session |
| `STRING_SESSION3` | Optional third assistant session |
| `COOKIE_URL` | Optional space-separated YouTube cookie URLs |

See [sample.env](sample.env) for all supported options, including Spotify metadata, images, welcome messages, video limits, and moderation exclusions.

---

# 🛠 Installation Options

## Docker

Build and run the image:

```bash
docker build -t openheartsmusic:latest .
docker run -d \
	--restart unless-stopped \
	--env-file .env \
	-v ./OpenHeartsMusic/cookies:/app/OpenHeartsMusic/cookies \
	-v ./downloads:/app/downloads \
	--name openheartsmusic \
	openheartsmusic:latest
```

## Docker Compose

```bash
docker compose up -d --build
docker compose logs -f
```

Stop or restart the service with:

```bash
docker compose down
docker compose restart
```

---

# 📖 Commands

## 👤 User Commands

| Command | Description |
|---------|-------------|
| `/play <song/url>` | Play a song from a YouTube URL or search query |
| `/vplay <song/url>` | Play supported video media when enabled |
| `/queue` | Display the current music queue |
| `/ping` | Check bot latency and status |
| `/help` | Show the help menu |

## 🛡 Playback and Admin Commands

| Command | Description |
|---------|-------------|
| `/pause` | Pause current playback |
| `/resume` | Resume playback |
| `/skip` | Skip the current track |
| `/stop` | Stop playback |
| `/seek <time>` | Seek to a specific timestamp |
| `/end` | End the current voice chat session |

The exact command availability can vary with deployment settings and enabled plugins.

---

# 📂 Project Structure

```text
OpenHeartsMusic main/
├── OpenHeartsMusic/
│   ├── core/          # Bot, calls, database, sessions, and YouTube logic
│   ├── helpers/       # Playback, queues, thumbnails, effects, and utilities
│   ├── locales/       # Translation files
│   └── plugins/       # Admin, playback, settings, events, and utilities
├── config.py          # Environment-based configuration
├── sample.env         # Configuration template
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── start
├── tests/
├── downloads/
├── MASTER_DOCUMENTATION.md
└── LICENSE
```

---

# 🤝 Contributing

Contributions are welcome. Bug fixes, documentation improvements, performance work, feature suggestions, and tests are all appreciated. Please open an issue or pull request with enough detail to reproduce and review the change.

---

# 📞 Support

| Platform | Link |
|----------|------|
| 📢 Telegram Channel | [Shreyansh Music Support](https://t.me/ShreyanshMusicSupport) |
| 💬 Telegram Support | [OpenHearts Support Chat](https://t.me/+jLpKEtUuhyNlODA1) |

For bugs, include the relevant logs, configuration flags, and reproduction steps. Never share your `.env` file or session strings.

---

# 📄 License

This project is licensed under the **GNU General Public License v3.0 (GPL-3.0)**. See [LICENSE](LICENSE) for the complete license text.

<div align="center">

## ⭐ Support the Project

If OpenHearts Music is useful to you, consider starring the repository and sharing it with your community.

<br>

**Made with ❤️ by the OpenHearts Music contributors**

</div>
