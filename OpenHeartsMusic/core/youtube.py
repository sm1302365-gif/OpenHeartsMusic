# ==============================================================================
# youtube.py - YouTube Integration
# ==============================================================================
# Handles searching for tracks, downloading them via yt-dlp, and managing cookies.
# ==============================================================================

import os
import re
import glob
import time
import importlib
import yt_dlp
import random
import asyncio
import aiohttp
from dataclasses import replace
from pathlib import Path
from typing import Optional, Union

from OpenHeartsMusic import config, logger

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROOT_COOKIE_FILE = PROJECT_ROOT.parent / "cookies.txt"
COOKIES_DIR = PROJECT_ROOT / "cookies"


# yt-dlp uses JavaScript runtimes for current YouTube extraction challenges.
deno_path = os.path.expanduser("~\\.deno\\bin")
if deno_path not in os.environ.get("PATH", "").split(os.pathsep):
    os.environ["PATH"] = os.environ.get("PATH", "") + os.pathsep + deno_path

BROWSER_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36 Edg/151.0.0.0"

YTDLP_COMMON_OPTIONS = {
    "quiet": True,
    "no_warnings": True,
    "js_runtimes": {"deno": {}, "node": {}},
    "geo_bypass": True,
    "nocheckcertificate": True,
    "proxy": config.PROXY_URL,
    "http_headers": {
        "User-Agent": BROWSER_USER_AGENT,
    },
}

AUTOPLAY_SEARCH_KEYWORDS = (
    "top global hits music",
    "popular Bollywood songs",
    "Bollywood latest hit songs",
    "Bollywood evergreen songs",
    "Hindi superhit songs",
    "bengali superhit songs",
)

AUTOPLAY_BLOCKED_TITLE_TERMS = (
    " live ", "radio", "podcast", "news", "talk show", "interview",
    "conversation", "speech", "audiobook", "story", "stories", "mix",
    "playlist", "compilation", "full album", " nonstop", "non-stop",
    "24/7", "sleep music", "study music", "white noise", "sound effects",
)

from hydrogram import enums, types
from py_yt import Playlist, VideosSearch
from OpenHeartsMusic.helpers import Track, utils


class YouTube:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="  # Base YouTube URL
        self.cookies = []  # List of available cookie files
        self.checked = False  # Whether cookies directory has been checked
        self.warned = False  # Whether missing cookies warning has been shown

        # Match YouTube URLs
        self.regex = re.compile(
            r"(https?://)?(www\.|m\.|music\.)?"
            r"(youtube\.com/(watch\?v=|shorts/|live/|embed/|playlist\?list=)|youtu\.be/)"
            r"([A-Za-z0-9_-]{11}|PL[A-Za-z0-9_-]+)([&?][^\s]*)?"
        )

        # Cache results for 10 mins
        self.search_cache = {}  # {"query_video": (result, timestamp)}
        self.cache_time = {}  # Deprecated, using tuple in search_cache instead
        self._autoplay_history: dict[int, list[str]] = {}

        # Limit concurrent downloads to prevent lag
        self._download_semaphore = asyncio.Semaphore(5)  # Max 5 simultaneous downloads
        self._max_video_height = getattr(config, "VIDEO_MAX_HEIGHT", 1080)
        self._spotify = None

    @staticmethod
    def _is_autoplay_song(item: dict) -> bool:
        """Reject non-song videos before they can enter the autoplay queue."""
        if not item or item.get("is_live") or item.get("live_status") in {
            "is_live", "is_upcoming"
        }:
            return False

        duration = item.get("duration")
        if duration is None:
            return False
        try:
            duration = int(duration)
        except (TypeError, ValueError):
            return False
        if duration < 30 or duration > 15 * 60:
            return False

        title = f" {(item.get('title') or '').lower()} "
        return not any(term in title for term in AUTOPLAY_BLOCKED_TITLE_TERMS)

    def _remember_autoplay_track(self, chat_id: int, track_id: str) -> None:
        history = self._autoplay_history.setdefault(chat_id, [])
        if track_id in history:
            return
        history.append(track_id)
        del history[:-20]

    def is_external_url(self, url: str) -> bool:
        lowered = url.lower()
        return "open.spotify.com/" in lowered or "music.apple.com/" in lowered

    @staticmethod
    def _is_reload_error(error: Exception) -> bool:
        message = str(error).lower()
        return "page needs to be reloaded" in message

    def _get_spotify(self):
        if self._spotify is None:
            client_id = getattr(config, "SPOTIFY_CLIENT_ID", "")
            client_secret = getattr(config, "SPOTIFY_CLIENT_SECRET", "")
            if not client_id or not client_secret:
                raise RuntimeError("Spotify credentials are not configured")
            try:
                spotipy = importlib.import_module("spotipy")
                credentials = importlib.import_module("spotipy.oauth2")
            except ImportError as error:
                raise RuntimeError("Spotify support is not installed") from error
            self._spotify = spotipy.Spotify(
                auth_manager=credentials.SpotifyClientCredentials(
                    client_id=client_id,
                    client_secret=client_secret,
                )
            )
        return self._spotify

    @staticmethod
    def _spotify_track_query(track: dict) -> str | None:
        if not track or not track.get("name"):
            return None
        artists = track.get("artists") or []
        artist = artists[0].get("name") if artists else None
        return f"{track['name']} {artist}" if artist else track["name"]

    async def resolve_external(self, url: str, limit: int) -> list[str]:
        """Resolve Spotify or Apple Music metadata into YouTube search queries."""
        lowered = url.lower()
        if "open.spotify.com/" in lowered:
            return await self._resolve_spotify(url, limit)
        if "music.apple.com/" in lowered:
            return await self._resolve_apple_music(url, limit)
        return []

    async def _resolve_spotify(self, url: str, limit: int) -> list[str]:
        def resolve() -> list[str]:
            client = self._get_spotify()
            kind = url.split("open.spotify.com/", 1)[1].split("/", 1)[0].split("?", 1)[0]
            queries = []
            if kind == "track":
                query = self._spotify_track_query(client.track(url))
                return [query] if query else []
            if kind == "album":
                response = client.album_tracks(url, limit=min(limit, 50))
                while response and len(queries) < limit:
                    queries.extend(
                        query for item in response.get("items", [])
                        for query in [self._spotify_track_query(item)]
                        if query
                    )
                    if not response.get("next"):
                        break
                    response = client.next(response)
            elif kind == "playlist":
                response = client.playlist_items(url, limit=min(limit, 50))
                while response and len(queries) < limit:
                    for item in response.get("items", []):
                        query = self._spotify_track_query(item.get("track"))
                        if query:
                            queries.append(query)
                    if not response.get("next"):
                        break
                    response = client.next(response)
            return queries[:limit]

        return await asyncio.to_thread(resolve)

    async def _resolve_apple_music(self, url: str, limit: int) -> list[str]:
        match = re.search(r"/(?:song|album)/[^/]+/(\d+)", url)
        if not match:
            def extract_playlist() -> list[str]:
                options = {
                    **YTDLP_COMMON_OPTIONS,
                    "quiet": True,
                    "no_warnings": True,
                    "extract_flat": True,
                    "skip_download": True,
                }
                with yt_dlp.YoutubeDL(options) as ydl:
                    info = ydl.extract_info(url, download=False) or {}
                return [
                    item["title"]
                    for item in info.get("entries") or []
                    if item.get("title")
                ][:limit]

            try:
                return await asyncio.to_thread(extract_playlist)
            except Exception:
                return []

        api_url = f"https://itunes.apple.com/lookup?id={match.group(1)}&entity=song"
        try:
            headers = {"User-Agent": BROWSER_USER_AGENT}
            async with aiohttp.ClientSession(headers=headers, trust_env=True) as session:
                async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=15), proxy=config.PROXY_URL) as response:
                    if response.status != 200:
                        return []
                    payload = await response.json()
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            return []

        queries = []
        for item in payload.get("results", []):
            if item.get("wrapperType") != "track":
                continue
            name = item.get("trackName")
            artist = item.get("artistName")
            if name:
                queries.append(f"{name} {artist}" if artist else name)
        return queries[:limit]

    def _locate_download_file(self, video_id: str, video: bool = False) -> Optional[str]:
        pattern = str(PROJECT_ROOT / "downloads" / f"{video_id}*")
        candidates = sorted([
            path for path in glob.glob(pattern)
            if not path.endswith((".part", ".ytdl", ".info.json", ".temp"))
        ])

        def _best_file(paths: list[str]) -> Optional[str]:
            best_path = None
            best_size = -1
            for path in paths:
                if os.path.isdir(path):
                    continue
                try:
                    size = os.path.getsize(path)
                except OSError:
                    continue
                if size > best_size:
                    best_size = size
                    best_path = path
            return best_path

        video_exts = {".mp4", ".mkv", ".webm", ".mov"}
        audio_exts = {".m4a", ".webm", ".opus", ".mp3", ".ogg", ".wav", ".flac"}

        if video:
            video_candidates = [
                path for path in candidates
                if not os.path.isdir(path)
                and Path(path).suffix.lower() in video_exts
            ]
            return _best_file(video_candidates)

        audio_candidates = [
            path for path in candidates
            if not os.path.isdir(path)
            and Path(path).suffix.lower() in audio_exts
        ]
        if audio_candidates:
            return _best_file(audio_candidates)

        fallback_candidates = [
            path for path in candidates
            if not os.path.isdir(path)
            and Path(path).suffix.lower() in {".mp4", ".mkv", ".mov"}
        ]
        if fallback_candidates:
            return _best_file(fallback_candidates)

        return _best_file([path for path in candidates if not os.path.isdir(path)])

    def get_cookies(self):
        def usable(path: str | Path) -> bool:
            try:
                return Path(path).is_file() and Path(path).stat().st_size > 32
            except OSError:
                return False

        configured_cookie = getattr(config, "COOKIE_FILE", None)
        if configured_cookie and usable(configured_cookie):
            return str(Path(configured_cookie).resolve())

        if usable(ROOT_COOKIE_FILE):
            return str(ROOT_COOKIE_FILE)

        if not self.checked:
            if COOKIES_DIR.exists():
                for file in os.listdir(COOKIES_DIR):
                    if file.endswith(".txt") and usable(COOKIES_DIR / file):
                        self.cookies.append(file)
            self.checked = True
        if not self.cookies:
            if not self.warned:
                self.warned = True
                logger.warning("Cookies are missing; downloads might fail.")
            return None
        return str(COOKIES_DIR / random.choice(self.cookies))

    def _cookie_options(self) -> dict[str, str]:
        cookie = self.get_cookies()
        return {"cookiefile": cookie} if cookie else {}

    def _watch_url(self, video_id_or_url: str) -> str:
        if video_id_or_url.startswith(("http://", "https://")):
            return video_id_or_url
        return self.base + video_id_or_url

    async def save_cookies(self, urls: list[str]) -> None:
        logger.info("🍪 Saving cookies from urls...")
        saved_count = 0
        cookies_dir = COOKIES_DIR
        cookies_dir.mkdir(parents=True, exist_ok=True)
        for url in urls:
            try:
                path = str(cookies_dir / f"cookie{random.randint(10000, 99999)}.txt")
                link = url.replace("me/", "me/raw/")
                async with aiohttp.ClientSession(headers={"User-Agent": BROWSER_USER_AGENT}, trust_env=True) as session:
                    async with session.get(link, headers={"User-Agent": BROWSER_USER_AGENT}) as resp:
                        if resp.status != 200:
                            logger.error(f"❌ Cookie download failed: HTTP {resp.status} from {url}")
                            continue
                        content = await resp.read()
                        if not content or len(content) < 50:
                            logger.error(f"❌ Cookie file empty or invalid from {url}")
                            continue
                        with open(path, "wb") as fw:
                            fw.write(content)
                        if os.path.exists(path) and os.path.getsize(path) > 0:
                            saved_count += 1
                            # Update cookie list
                            cookie_filename = os.path.basename(path)
                            if cookie_filename not in self.cookies:
                                self.cookies.append(cookie_filename)
                            logger.info(f"✅ Saved: {cookie_filename} ({len(content)} bytes)")
            except Exception as e:
                logger.error(f"❌ Cookie download error from {url}: {e}")

        # Refresh cookie list
        self.checked = True

        if saved_count > 0:
            logger.info(f"✅ Cookies saved. ({saved_count} file(s))")
        else:
            logger.error("❌ No cookies saved! Check COOKIE_URL in .env. YouTube downloads will fail!")

    def valid(self, url: str) -> bool:
        return bool(re.match(self.regex, url))

    def url(self, message_1: types.Message) -> Union[str, None]:
        messages = [message_1]
        link = None
        if message_1.reply_to_message:
            messages.append(message_1.reply_to_message)

        for message in messages:
            text = message.text or message.caption or ""

            if message.entities:
                for entity in message.entities:
                    if entity.type == enums.MessageEntityType.URL:
                        link = text[entity.offset: entity.offset +
                                    entity.length]
                        break

            if message.caption_entities:
                for entity in message.caption_entities:
                    if entity.type == enums.MessageEntityType.TEXT_LINK:
                        link = entity.url
                        break

        if link:
            return link.split("&si")[0].split("?si")[0]

        # Command arguments are not always represented as URL entities.
        match = re.search(
            r"https?://(?:open\.spotify\.com|music\.apple\.com)/[^\s]+",
            message_1.text or message_1.caption or "",
            re.IGNORECASE,
        )
        if match:
            return match.group(0).rstrip(".,)")
        return None

    async def search(self, query: str, m_id: int) -> Track | None:
        # Check cache (10 min TTL)
        cache_key = query
        current_time = asyncio.get_running_loop().time()

        if cache_key in self.search_cache:
            cached_result, cache_timestamp = self.search_cache[cache_key]
            if current_time - cache_timestamp < 600:  # 10 minutes
                # Return a fresh copy
                fresh = replace(cached_result)
                fresh.message_id = m_id
                fresh.file_path = None
                fresh.user = None
                fresh.time = 0
                fresh.video = False
                return fresh

        try:
            if self.valid(query):
                cookie_options = self._cookie_options()
                attempts = [cookie_options]
                if cookie_options:
                    attempts.append(cookie_options.copy())

                def _extract(options):
                    ydl_opts = {
                        **YTDLP_COMMON_OPTIONS,
                        "quiet": True,
                        "noplaylist": True,
                        "extract_flat": "in_playlist",
                        **options,
                    }
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        return ydl.extract_info(query, download=False)

                data = None
                for attempt_number, options in enumerate(attempts, start=1):
                    try:
                        data = await asyncio.to_thread(_extract, options)
                        break
                    except Exception as error:
                        if (
                            attempt_number == 1
                            and len(attempts) > 1
                            and self._is_reload_error(error)
                        ):
                            logger.warning(
                                "YouTube rejected the configured cookie; retrying URL search with the same cookie file for %s",
                                query,
                            )
                            continue
                        raise
                if not data:
                    return None

                duration_sec = data.get("duration")
                is_live = data.get("is_live", False)
                if duration_sec is None and is_live:
                    duration = "LIVE"
                    duration_sec = 0
                else:
                    duration = utils.format_duration(int(duration_sec)) if duration_sec else "0:00"
                track = Track(
                    id=data.get("id"),
                    channel_name=data.get("uploader") or data.get("channel", ""),
                    duration=duration,
                    duration_sec=int(duration_sec) if duration_sec else 0,
                    message_id=m_id,
                    title=(data.get("title") or "")[:25],
                    thumbnail=data.get("thumbnail") or "",
                    url=data.get("webpage_url") or query,
                    view_count=str(data.get("view_count", "")),
                    is_live=is_live,
                )
            else:
                _search = VideosSearch(query, limit=1)
                results = await _search.next()

                if not results or not results.get("result"):
                    return None

                data = results["result"][0]
                duration = data.get("duration")
                is_live = duration is None or duration == "LIVE"

                track = Track(
                    id=data.get("id"),
                    channel_name=data.get("channel", {}).get("name"),
                    duration=duration if not is_live else "LIVE",
                    duration_sec=0 if is_live else utils.to_seconds(duration),
                    message_id=m_id,
                    title=data.get("title")[:25],
                    thumbnail=data.get(
                        "thumbnails", [{}])[-1].get("url").split("?")[0],
                    url=data.get("link"),
                    view_count=data.get("viewCount", {}).get("short"),
                    is_live=is_live,
                )

            # Cache result (max 100)
            self.search_cache[cache_key] = (track, current_time)
            if len(self.search_cache) > 100:
                oldest_key = min(self.search_cache.keys(),
                                 key=lambda k: self.search_cache[k][1])
                del self.search_cache[oldest_key]

            return replace(track)

        except Exception as e:
            logger.warning(f"⚠️ YouTube search failed for '{query}': {e}")
            return None

    async def random_autoplay_track(
        self,
        chat_id: int,
        m_id: int = 0,
        exclude_id: str | None = None,
    ) -> Track | None:
        """Choose a fresh track from a curated search for autoplay fallback."""
        history = self._autoplay_history.setdefault(chat_id, [])

        try:
            keywords = list(AUTOPLAY_SEARCH_KEYWORDS)
            random.shuffle(keywords)
            entries = []
            for keyword in keywords[:4]:
                def _extract(search_keyword=keyword):
                    options = {
                        **YTDLP_COMMON_OPTIONS,
                        "default_search": "ytsearch5",
                        "extract_flat": "in_playlist",
                        "noplaylist": True,
                        **self._cookie_options(),
                    }
                    with yt_dlp.YoutubeDL(options) as ydl:
                        return ydl.extract_info(
                            f"ytsearch5:{search_keyword}", download=False
                        ) or {}

                info = await asyncio.to_thread(_extract)
                entries.extend(
                    item for item in info.get("entries") or []
                    if self._is_autoplay_song(item)
                    and item.get("id")
                    and item.get("id") not in history
                    and item.get("id") != exclude_id
                )
                if entries:
                    break
            if not entries:
                return None

            item = random.choice(entries)
            track_id = item["id"]
            self._remember_autoplay_track(chat_id, track_id)
            duration_sec = int(item.get("duration") or 0)

            return Track(
                id=track_id,
                channel_name=item.get("uploader") or item.get("channel") or "",
                duration=utils.format_duration(duration_sec) if duration_sec else "0:00",
                duration_sec=duration_sec,
                message_id=m_id,
                title=(item.get("title") or "Unknown Track")[:25],
                thumbnail=item.get("thumbnail") or "",
                url=item.get("webpage_url") or self._watch_url(track_id),
                user="Autoplay",
                view_count=str(item.get("view_count") or ""),
            )
        except Exception as error:
            logger.warning(f"Autoplay fallback search failed for chat {chat_id}: {error}")
            return None

    async def related(
        self,
        video_id: str,
        m_id: int,
        parent_title: str | None = None,
        video: bool = False,
        chat_id: int | None = None,
    ) -> Track | None:
        """Fetch a different track for autoplay instead of the same current song."""
        try:
            url = self._watch_url(video_id)

            def _extract():
                ydl_opts = {
                    **YTDLP_COMMON_OPTIONS,
                    "quiet": True,
                    "noplaylist": True,
                    **self._cookie_options(),
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(url, download=False)

            info = await asyncio.to_thread(_extract)
            history = self._autoplay_history.setdefault(chat_id, []) if chat_id else []
            candidates = []
            for item in info.get("related_videos") or info.get("entries") or []:
                related_id = item.get("id") or item.get("url")
                if not related_id:
                    continue

                if isinstance(related_id, str) and related_id.startswith("http"):
                    related_id = related_id.split("watch?v=", 1)[-1].split("&", 1)[0]

                if not related_id or related_id == video_id:
                    continue
                if related_id in history:
                    continue

                title = (item.get("title") or "").strip()
                if parent_title and title.lower() == parent_title.lower():
                    continue
                if not self._is_autoplay_song(item):
                    continue

                candidates.append(item)

            if candidates:
                item = candidates[0]
                related_id = item.get("id") or item.get("url")
                if isinstance(related_id, str) and related_id.startswith("http"):
                    related_id = related_id.split("watch?v=", 1)[-1].split("&", 1)[0]

                related_url = item.get("url") or self._watch_url(related_id)
                duration = item.get("duration")
                is_live = item.get("is_live", False)
                if duration is None and is_live:
                    duration_text = "LIVE"
                    duration_sec = 0
                else:
                    duration_sec = int(duration) if duration else 0
                    duration_text = utils.format_duration(duration_sec)

                if chat_id:
                    self._remember_autoplay_track(chat_id, related_id)

                return Track(
                    id=related_id,
                    channel_name=item.get("uploader") or item.get("channel") or "",
                    duration=duration_text,
                    duration_sec=duration_sec,
                    title=(item.get("title") or parent_title or "Recommended")[:25],
                    url=related_url,
                    file_path=None,
                    message_id=m_id,
                    thumbnail=item.get("thumbnail") or "",
                    user="Autoplay",
                    view_count=str(item.get("view_count", "")),
                    is_live=is_live,
                    video=video,
                )

            if parent_title:
                fallback = await self.search(parent_title, m_id)
                if fallback and fallback.id != video_id and self._is_autoplay_song({
                    "title": fallback.title,
                    "duration": fallback.duration_sec,
                    "is_live": fallback.is_live,
                }):
                    if chat_id:
                        self._remember_autoplay_track(chat_id, fallback.id)
                    return fallback
            return None
        except Exception as e:
            logger.warning(f"⚠️ YouTube related fetch failed for '{video_id}': {e}")
            if parent_title:
                fallback = await self.search(parent_title, m_id)
                if fallback and fallback.id != video_id and self._is_autoplay_song({
                    "title": fallback.title,
                    "duration": fallback.duration_sec,
                    "is_live": fallback.is_live,
                }):
                    if chat_id:
                        self._remember_autoplay_track(chat_id, fallback.id)
                    return fallback
            return None

    async def playlist(self, limit: int, user: str, url: str) -> list[Track]:
        try:
            plist = await Playlist.get(url)
            tracks = []

            # Check for videos
            if not plist or "videos" not in plist or not plist["videos"]:
                return []

            for data in plist["videos"][:limit]:
                try:
                    # Get thumbnail
                    thumbnails = data.get("thumbnails", [])
                    thumbnail_url = ""
                    if thumbnails and len(thumbnails) > 0:
                        thumbnail_url = thumbnails[-1].get(
                            "url", "").split("?")[0]

                    # Get link
                    link = data.get("link", "")
                    if "&list=" in link:
                        link = link.split("&list=")[0]

                    track = Track(
                        id=data.get("id", ""),
                        channel_name=data.get("channel", {}).get("name", ""),
                        duration=data.get("duration", "0:00"),
                        duration_sec=utils.to_seconds(
                            data.get("duration", "0:00")),
                        title=(data.get("title", "Unknown")[:25]),
                        thumbnail=thumbnail_url,
                        url=link,
                        user=user,
                        view_count="",
                    )
                    tracks.append(track)
                except Exception as e:
                    # Skip broken tracks
                    continue

            return tracks
        except KeyError as e:
            # YouTube API changed
            raise Exception(
                f"Failed to parse playlist. YouTube may have changed their structure.")
        except Exception as e:
            # Re-raise
            raise

    async def download(self, video_id: str, is_live: bool = False, video: bool = False) -> Optional[str]:
        url = self._watch_url(video_id)

        # Extract live stream URL
        if is_live:
            live_format = (
                "bestvideo[height<=1080]+bestaudio/"
                "best[height<=1080]/best"
                if video
                else "bestaudio/best"
            )
            ydl_opts = {
                **YTDLP_COMMON_OPTIONS,
                "quiet": True,
                "no_warnings": True,
                **self._cookie_options(),
                "format": live_format,
                "noplaylist": True,
                "socket_timeout": 20,
                "extractor_retries": 5,
                "sleep_interval_requests": 1,
                # Use android client to bypass YouTube bot detection on server IPs
                # "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
            }

            def _extract_url():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    try:
                        info = ydl.extract_info(url, download=False)
                        if not info:
                            return None

                        direct = info.get("url")
                        if direct:
                            return direct

                        # Find URL in formats
                        for fmt in info.get("formats", []):
                            if fmt.get("acodec") != "none" and fmt.get("url"):
                                return fmt["url"]

                        return info.get("manifest_url")
                    except yt_dlp.utils.ExtractorError as ex:
                        error_msg = str(ex)
                        if "not available" in error_msg.lower():
                            logger.error(
                                "Video format not available or region-blocked.")
                        else:
                            logger.error(
                                "Live stream URL extraction failed: %s", ex)
                        return None
                    except Exception as ex:
                        logger.error(
                            "Unexpected error during live stream extraction: %s", ex)
                        return None

            try:
                stream_url = await asyncio.wait_for(asyncio.to_thread(_extract_url), timeout=35)
            except asyncio.TimeoutError:
                logger.error("Live stream URL extraction timed out for %s", video_id)
                return None

            return stream_url

        # Let yt-dlp choose the best format
        filename_pattern = str(PROJECT_ROOT / "downloads" / video_id)

        # Check existing files
        existing_files = [
            f for f in glob.glob(f"{filename_pattern}.*")
            if not f.endswith('.part')
        ]
        if video:
            video_candidates = [
                f for f in existing_files
                if Path(f).suffix.lower() in {".mp4", ".mkv", ".webm", ".mov"}
            ]
            if video_candidates:
                return video_candidates[0]
        else:
            audio_candidates = [
                f for f in existing_files
                if Path(f).suffix.lower() in {".m4a", ".webm", ".opus", ".mp3", ".ogg", ".wav", ".flac"}
            ]
            if audio_candidates:
                return audio_candidates[0]

            # Fallback to mp4 for audio
            container_fallbacks = [
                f for f in existing_files
                if Path(f).suffix.lower() in {".mp4", ".mkv", ".mov"}
            ]
            if container_fallbacks:
                return container_fallbacks[0]

        # Create downloads dir
        downloads_dir = PROJECT_ROOT / "downloads"
        if not downloads_dir.exists():
            try:
                downloads_dir.mkdir(parents=True, exist_ok=True)
                logger.info("📁 Created downloads directory")
            except Exception as e:
                logger.error(f"❌ Cannot create downloads directory: {e}")
                return None

        # **PERFORMANCE FIX**: Use semaphore to limit concurrent downloads
        # Prevents bandwidth saturation when 15-20 groups download simultaneously
        async with self._download_semaphore:
            cookie = self.get_cookies()
            base_opts = {
                **YTDLP_COMMON_OPTIONS,
                "outtmpl": str(PROJECT_ROOT / "downloads" / "%(id)s.%(ext)s"),
                "quiet": True,
                "noplaylist": True,
                "geo_bypass": True,
                "no_warnings": True,
                "overwrites": False,
                "nocheckcertificate": True,
                "continuedl": True,
                "noprogress": True,
                # Max 4 fragments for stability
                "concurrent_fragment_downloads": 4,
                "http_chunk_size": 524288,  # 512KB chunks
                "socket_timeout": 30,
                "retries": 2,
                "fragment_retries": 2,
                "extractor_retries": 5,
                "sleep_interval_requests": 1,
                # Android client bypass
                # "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
            }

            if video:
                # Download best video
                height_filter = ""
                if self._max_video_height and self._max_video_height > 0:
                    height_filter = f"[height<={self._max_video_height}]"
                format_chain = (
                    f"bestvideo[ext=mp4]{height_filter}+bestaudio[ext=m4a]/"
                    f"bestvideo{height_filter}+bestaudio/"
                    "bestvideo+bestaudio/best"
                )
                ydl_opts = {
                    **base_opts,
                    "format": format_chain,
                    "merge_output_format": "mp4",
                    "postprocessors": [
                        {
                            "key": "FFmpegVideoConvertor",
                            "preferedformat": "mp4",
                        }
                    ],
                }
            else:
                # Download best audio
                ydl_opts = {
                    **base_opts,
                    # "format": "bestaudio[ext=m4a]/bestaudio[acodec=opus]/bestaudio/best",
                    "format": "bestaudio/best",
                    "postprocessors": [],
                }

            ydl_opts_cookie = {
                **ydl_opts,
                **self._cookie_options(),
            }

            def _download(ydl_runtime_opts):
                ydl_instance = None
                try:
                    ydl_instance = yt_dlp.YoutubeDL(ydl_runtime_opts)
                    # Extract info
                    info = ydl_instance.extract_info(url, download=True)
                    if not info:
                        logger.error(f"❌ Failed to extract info for {video_id}")
                        return None

                    time.sleep(0.5)
                    located = self._locate_download_file(video_id, video=video)
                    if located:
                        return located
                    logger.error(f"❌ Download completed but file not found for: {video_id}")
                    return None
                except yt_dlp.utils.ExtractorError as ex:
                    error_msg = str(ex)
                    if "not available" in error_msg.lower():
                        logger.error(
                            "❌ Video not available: May be region-blocked or private.")
                    elif "age" in error_msg.lower():
                        logger.error(
                            "❌ Age-restricted video: Cookies required.")
                    else:
                        logger.error("❌ YouTube extraction failed: %s", ex)
                    return None
                except yt_dlp.utils.DownloadError as ex:
                    error_msg = str(ex)
                    recovered = self._locate_download_file(video_id, video=video)
                    if "unable to rename file" in error_msg.lower() and recovered:
                        logger.warning(
                            f"⚠️ Renaming failed for {video_id}, using recovered file {Path(recovered).name}"
                        )
                        return recovered
                    if "416" in error_msg or "Requested range not satisfiable" in error_msg:
                        # HTTP 416 range error
                        logger.warning(f"⚠️ Range error for {video_id}, skipping")
                    else:
                        logger.warning(f"⚠️ Download error for {video_id}: {ex}")
                        if recovered:
                            logger.warning(
                                f"⚠️ Using recovered file for {video_id} despite download error"
                            )
                            return recovered
                    return None
                except Exception as ex:
                    logger.warning(f"⚠️ Unexpected download error for {video_id}: {ex}")
                    return None
                finally:
                    # Close yt-dlp safely
                    if ydl_instance:
                        try:
                            ydl_instance.close()
                        except Exception:
                            pass

            # Always keep the configured cookie file enabled for YouTube requests.
            return await asyncio.to_thread(_download, ydl_opts_cookie)

    async def stream_url(self, video_id: str) -> Optional[str]:
        """Resolve a short-lived direct audio URL without downloading the track."""
        url = self._watch_url(video_id)
        cookie_options = self._cookie_options()
        attempts = [cookie_options]
        if cookie_options:
            attempts.append(cookie_options.copy())

        def _extract_stream_url(options):
            ydl_opts = {
                **YTDLP_COMMON_OPTIONS,
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
                "format": "bestaudio/best",
                "retries": 2,
                "fragment_retries": 2,
                "extractor_retries": 2,
                **options,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if not info:
                    return None
                direct_url = info.get("url")
                if direct_url:
                    return direct_url
                for fmt in info.get("formats", []):
                    if fmt.get("acodec") != "none" and fmt.get("url"):
                        return fmt["url"]
                return None

        last_error = None
        for options in attempts:
            try:
                stream_url = await asyncio.to_thread(_extract_stream_url, options)
                if stream_url:
                    return stream_url
            except Exception as error:
                last_error = error
                logger.warning(
                    "Direct stream URL attempt failed for %s: %s", video_id, error
                )

        if last_error:
            logger.warning(
                "Direct stream URL resolution failed for %s: %s", video_id, last_error
            )
        return None
