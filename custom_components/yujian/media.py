"""Browse and play Music Assistant media through Home Assistant services.

Home Assistant's Music Assistant integration exposes every MA player as a
``media_player.music_assistant_*`` entity. We reuse that instead of talking to
MA directly, so the TV never needs a separate MA token.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any

import aiohttp

from .playlists import playlist_item

_LOGGER = logging.getLogger(__name__)

# HA entity id prefix of Music Assistant players.
MASS_PREFIX = "media_player.music_assistant_"

# media_content_type the MA integration uses to address its own source.
MASS_SOURCE_TYPE = "music_assistant"

# Largest cover accepted before we drop it (a thumbnail is usually a few KB).
MAX_COVER_BYTES = 2 * 1024 * 1024


def find_mass_player(hass, preferred: str | None = None) -> str | None:
    """Return the MA media_player entity to use.

    ``preferred`` wins when it still exists; otherwise the first
    ``music_assistant_*`` entity (sorted, missing ones skipped) is used.
    """
    if preferred and hass.states.get(preferred) is not None:
        return preferred
    candidates = sorted(
        entity_id
        for entity_id in hass.states.async_entity_ids("media_player")
        if entity_id.startswith(MASS_PREFIX) and hass.states.get(entity_id) is not None
    )
    return candidates[0] if candidates else None


def _unwrap(response: Any, entity_id: str) -> dict[str, Any]:
    """Unwrap the browse_media service response, which is keyed by entity."""
    if isinstance(response, dict):
        if entity_id in response:
            value = response[entity_id]
        elif len(response) == 1:
            value = next(iter(response.values()))
        else:
            value = response
        return value if isinstance(value, dict) else {}
    return {}


async def async_browse(
    hass, entity_id: str, media_content_type: str | None, media_content_id: str | None
) -> dict[str, Any]:
    """Call media_player.browse_media and return the (unwrapped) media tree."""
    data: dict[str, Any] = {"entity_id": entity_id}
    if media_content_type is not None:
        data["media_content_type"] = media_content_type
    if media_content_id is not None:
        data["media_content_id"] = media_content_id
    response = await hass.services.async_call(
        "media_player",
        "browse_media",
        data,
        blocking=True,
        return_response=True,
    )
    return _unwrap(response, entity_id)


async def async_list_playlists(hass, entity_id: str) -> list[dict[str, Any]]:
    """Return the MA playlists as a list of ``{id, name, thumbnail}``."""
    root = await async_browse(hass, entity_id, None, None)
    node = next(
        (
            child
            for child in (root.get("children") or [])
            if child.get("media_content_id") == "playlists"
        ),
        {},
    )
    content_type = node.get("media_content_type") or MASS_SOURCE_TYPE
    content_id = node.get("media_content_id") or "playlists"
    listing = await async_browse(hass, entity_id, content_type, content_id)

    playlists: list[dict[str, Any]] = []
    for child in listing.get("children") or []:
        media_id = child.get("media_content_id")
        if not isinstance(media_id, str) or not media_id.startswith("library://"):
            continue
        playlists.append(
            {
                "id": media_id,
                "name": child.get("title") or media_id,
                "thumbnail": child.get("thumbnail"),
            }
        )
    return playlists


async def async_play_playlist(hass, entity_id: str, uri: str) -> None:
    """Play a whole playlist on the MA player (replacing the queue)."""
    await hass.services.async_call(
        "media_player",
        "play_media",
        {
            "entity_id": entity_id,
            "media_content_id": uri,
            "media_content_type": "playlist",
            "enqueue": "replace",
        },
        blocking=True,
    )


async def async_fetch_cover_b64(hass, url: str | None) -> str | None:
    """Download a thumbnail and return it as a data URI, or None on failure."""
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        return None
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    session = async_get_clientsession(hass)
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=6)) as resp:
            if resp.status != 200:
                return None
            mime = (resp.headers.get("Content-Type") or "image/jpeg").split(";")[0]
            mime = mime.strip() or "image/jpeg"
            if not mime.startswith("image/"):
                mime = "image/jpeg"
            data = await resp.read()
    except (aiohttp.ClientError, TimeoutError) as err:
        _LOGGER.debug("拉取封面失败 %s: %s", url, err)
        return None
    if not data or len(data) > MAX_COVER_BYTES:
        return None
    return f"data:{mime};base64," + base64.b64encode(data).decode("ascii")


async def fetch_covers(hass, playlists: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach base64 covers to the playlist list with bounded concurrency."""
    sem = asyncio.Semaphore(5)

    async def _one(item: dict[str, Any]) -> dict[str, Any]:
        async with sem:
            cover = await async_fetch_cover_b64(hass, item.get("thumbnail"))
        return playlist_item(item["name"], item["id"], cover_b64=cover)

    return await asyncio.gather(*(_one(item) for item in playlists))
