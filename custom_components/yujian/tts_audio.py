"""Turn text into an audio URL the TV app can fetch.

The app plays audio when the notify payload's ``tts`` field is an http(s) URL
(it downloads up to 2 MB, checks the magic bytes and plays it with
MediaPlayer). Home Assistant already exposes every TTS entity through the
media-source bridge, and the resulting ``/api/tts_proxy/<token>`` URL needs no
auth token -- which is exactly what the TV needs, since it has none.

So: pick a TTS entity from the entry options, synthesize, resolve to a URL.
"""

from __future__ import annotations

import logging

from homeassistant.components import media_source
from homeassistant.components.tts.media_source import generate_media_source_id
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.network import NoURLAvailableError, get_url

_LOGGER = logging.getLogger(__name__)


class YujianTtsError(HomeAssistantError):
    """Raised when the audio could not be synthesized."""


async def async_speech_text_url(
    hass: HomeAssistant, engine: str, message: str
) -> str:
    """Synthesize ``message`` with ``engine`` and return an absolute audio URL."""
    message = message.strip()
    if not message:
        raise YujianTtsError("要朗读的文字是空的")
    if not engine:
        raise YujianTtsError(
            "还没有选择 TTS 服务，请到集成选项里选一个（设置 → 设备与服务 → 玉简 → 配置）"
        )

    try:
        media_id = generate_media_source_id(
            hass, message=message, engine=engine, cache=True
        )
    except HomeAssistantError as err:
        raise YujianTtsError(f"TTS 服务 {engine} 不可用: {err}") from err

    try:
        played = await media_source.async_resolve_media(hass, media_id, None)
    except media_source.Unresolvable as err:
        raise YujianTtsError(f"TTS 合成失败: {err}") from err

    url = played.url
    if url.startswith(("http://", "https://")):
        return url

    # Relative (/api/tts_proxy/...) -> absolute. The TV is on the LAN, so the
    # internal URL is the one that reaches this Home Assistant instance.
    try:
        base = get_url(hass, prefer_external=False, allow_cloud=False)
    except NoURLAvailableError as err:
        raise YujianTtsError(
            "取不到 Home Assistant 的局域网地址，电视无法下载音频"
        ) from err
    return f"{base.rstrip('/')}/{url.lstrip('/')}"


def speech_text_for(title: str, message: str) -> str:
    """Build the text to speak from a banner's title and body."""
    title = (title or "").strip()
    message = (message or "").strip()
    if title and message:
        return f"{title}。{message}"
    return title or message
