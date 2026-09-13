"""Reusable audio effect helpers for PyTgCalls media streams."""

from __future__ import annotations

from typing import ClassVar

from pytgcalls import types


class AudioEffectManager:
    """Manage reusable audio filters and FFmpeg parameters."""

    _FILTERS: ClassVar[dict[str, str]] = {
        "karaoke": "pan=stereo|c0=0.5*c0-0.5*c1|c1=0.5*c1-0.5*c0",
        "studio": "bass=g=12,treble=g=8,aecho=0.8:0.9:500:0.5",
        "bassboost": "bass=g=8",
        "deep_bass": "bass=f=90:g=14,lowpass=f=180,volume=1.15",
        "8d": "pan=stereo|c0=0.5*c0+0.5*c1|c1=0.5*c1+0.5*c0,aecho=0.8:0.8:600:0.5",
        "nightcore": "asetrate=44100*1.25,atempo=1.25",
        "lofi": "asetrate=44100*0.8,atempo=0.8,aecho=0.8:0.88:60:0.4",
        "none": "",
    }

    @classmethod
    def normalize(cls, effect: str | None) -> str:
        """Normalize names like 'BassBoost' into the canonical effect key."""
        if effect is None:
            return "none"
        return str(effect).strip().lower()

    @classmethod
    def get_filter(cls, effect: str | None) -> str:
        """Return the FFmpeg filter string for an effect."""
        key = cls.normalize(effect)
        return cls._FILTERS.get(key, "")

    @classmethod
    def build_ffmpeg_params(cls, base_params: str, effect: str = "none") -> str:
        """Append an effect filter to an FFmpeg params string."""
        params = (base_params or "").strip()
        filter_value = cls.get_filter(effect)

        if not filter_value:
            return params

        if not params:
            return f"-af {filter_value}"

        return f"{params} -af {filter_value}"

    @classmethod
    def build_media_stream(
        cls,
        file_path: str,
        effect: str = "none",
        ffmpeg_parameters: str = "",
        is_video: bool = False,
        audio_quality: object | None = None,
    ) -> types.MediaStream:
        """Create a PyTgCalls MediaStream with the requested audio effect.

        Video playback requires an explicit video source so the camera track survives
        call renegotiation, such as when the assistant is muted and unmuted.
        """
        if not file_path:
            raise ValueError("file_path cannot be empty")

        filter_value = cls.get_filter(effect)
        params = (ffmpeg_parameters or "").strip()
        if filter_value:
            params = f"{params} -af {filter_value}".strip()

        stream_kwargs = {
            "media_path": file_path,
            "audio_path": file_path,  # Explicitly set audio path to prevent audio drop
            "audio_flags": (
                types.MediaStream.Flags.AUTO_DETECT
                if is_video
                else types.MediaStream.Flags.REQUIRED
            ),
            "video_flags": (
                types.MediaStream.Flags.REQUIRED
                if is_video
                else types.MediaStream.Flags.IGNORE
            ),
            "ffmpeg_parameters": params,
        }

        if audio_quality is not None:
            stream_kwargs["audio_parameters"] = audio_quality
        else:
            stream_kwargs["audio_parameters"] = types.AudioQuality.STUDIO

        if is_video:
            stream_kwargs["video_parameters"] = types.VideoQuality.HD_720p

        return types.MediaStream(**stream_kwargs)

    @classmethod
    def is_valid_effect(cls, effect: str | None) -> bool:
        """Return True when an effect name is supported."""
        return cls.normalize(effect) in cls._FILTERS

    @classmethod
    def list_effects(cls) -> list[str]:
        """Return all supported effects, excluding the 'none' sentinel."""
        return [name for name in cls._FILTERS if name != "none"]


__all__ = ["AudioEffectManager"]
