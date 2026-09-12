# Docker Setup

This project can run with Docker Compose. The Compose service builds the image
from the repository Dockerfile, loads environment variables from `.env`, and
keeps downloads and Telegram cookies on the host.

## Prerequisites

- Docker Desktop with Docker Compose
- A project-root `.env` file containing the bot configuration

## Start the bot

From the `OpenHeartsMusic main` directory:

```bash
docker compose up -d --build
```

The bot runs as the `open-heart-music-bot` container and restarts automatically
unless stopped.

## Logs and shutdown

```bash
docker compose logs -f hasii
docker compose down
```

## Persistent data

Compose mounts these host directories into the container:

- `./downloads` -> `/app/downloads`
- `./OpenHeartsMusic/cookies` -> `/app/OpenHeartsMusic/cookies`

These directories remain available after the container is recreated.

## Rebuild after code changes

```bash
docker compose up -d --build
```
