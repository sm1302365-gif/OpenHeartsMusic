# ==============================================================================
# lang.py - Multi-Language Support System
# ==============================================================================
# This file manages translations for the bot in multiple languages.
# - Translation files are stored in OpenHeartsMusic/locales/ as JSON files (en.json, si.json)
# - Each chat can have its own language preference stored in the database
# - The @language() decorator automatically injects translations into message handlers
# ==============================================================================

import json
from functools import wraps
from pathlib import Path

from OpenHeartsMusic import db, logger

# Supported language codes and their display names
lang_codes = {
    "en": "English",  # English language
}


class SafeLangDict(dict):
    """Dictionary wrapper that falls back to English values for missing keys."""

    def __init__(self, data: dict, fallback: dict | None = None):
        super().__init__(data)
        self.fallback = fallback or {}

    def __getitem__(self, key):
        if key in self:
            return super().__getitem__(key)
        if self.fallback and key in self.fallback:
            return self.fallback[key]
        return f"{{{key}}}"

    def get(self, key, default=None):
        if key in self:
            return super().__getitem__(key)
        if self.fallback and key in self.fallback:
            return self.fallback[key]
        return default


class Language:
    """
    Language class for managing multilingual support using JSON language files.
    """

    def __init__(self):
        """Initialize the language system and load all translation files."""
        self.lang_codes = lang_codes
        # Directory containing translation files
        self.lang_dir = self._resolve_lang_dir()
        self.languages = self.load_files()  # Load all language files into memory

    def _resolve_lang_dir(self) -> Path:
        candidates = [
            Path(__file__).resolve().parents[1] / "locales",
            Path(__file__).resolve().parents[1] / "OpenHeartsMusic" / "locales",
            Path("OpenHeartsMusic/locales"),
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[0]

    def load_files(self):
        """Load all language JSON files from the locales directory."""
        languages = {}
        for lang_code in self.lang_codes.keys():
            lang_file = self.lang_dir / f"{lang_code}.json"
            if lang_file.exists():
                try:
                    with open(lang_file, "r", encoding="utf-8") as file:
                        languages[lang_code] = json.load(file)
                except Exception as e:
                    logger.warning(f"Failed to load language file {lang_file}: {e}")
                    languages[lang_code] = {}

        if "en" not in languages:
            languages["en"] = {}

        english = SafeLangDict(languages.get("en", {}))
        safe_languages = {"en": english}
        for lang_code, data in languages.items():
            if lang_code != "en":
                safe_languages[lang_code] = SafeLangDict(data, fallback=english)

        logger.info(f"🌐 Loaded languages: {', '.join(safe_languages.keys())}")
        return safe_languages

    async def get_lang(self, chat_id: int) -> dict:
        """Get the translation dictionary for a specific chat."""
        return self.languages["en"]  # Return the translation dictionary

    def language(self):
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                fallen = next(
                    (
                        arg
                        for arg in args
                        if hasattr(arg, "chat") or hasattr(arg, "message")
                    ),
                    None,
                )

                if hasattr(fallen, "chat"):
                    chat = fallen.chat
                elif hasattr(fallen, "message"):
                    chat = fallen.message.chat

                if chat.id in db.blacklisted:
                    return await chat.leave()

                lang_code = "en"
                lang_dict = self.languages.get(lang_code, self.languages.get("en"))
                if lang_dict is None:
                    lang_dict = SafeLangDict({})

                setattr(fallen, "lang", lang_dict)
                return await func(*args, **kwargs)

            return wrapper

        return decorator
