"""Browse and play Music Assistant media through Home Assistant services.

Home Assistant's Music Assistant integration exposes every MA player as a
``media_player.music_assistant_*`` entity. We reuse that instead of talking to
MA directly, so the TV never needs a separate MA token.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import re
from typing import Any

import aiohttp

from .playlists import playlist_item

_LOGGER = logging.getLogger(__name__)

# Entity-registry platform of the Music Assistant integration. The entity ids
# themselves are derived from the player name (``media_player.ke_ting_akubox``)
# and carry no fixed prefix, so the registry is the only reliable source.
MASS_PLATFORM = "music_assistant"

# Legacy prefix, kept as a fallback when the entity registry is unavailable.
MASS_PREFIX = "media_player.music_assistant_"

# media_content_type the MA integration uses to address its own source.
MASS_SOURCE_TYPE = "music_assistant"

# States that mean "this player cannot answer a browse request right now".
UNAVAILABLE_STATES = ("unavailable", "unknown")

# Largest cover accepted before we drop it (a thumbnail is usually a few KB).
MAX_COVER_BYTES = 2 * 1024 * 1024

# Covers are re-encoded before they travel to the TV: Music Assistant hands out
# artwork at up to a megabyte each and the TV rejects a body over 4 MB, so a
# 27-playlist catalog would never fit with full-size images.
COVER_MAX_PIXELS = 320
COVER_JPEG_QUALITY = 80


def shrink_cover(data: bytes, mime: str) -> tuple[bytes, str]:
    """Downscale an image to a small JPEG; return the input untouched on error."""
    try:
        import io

        from PIL import Image

        with Image.open(io.BytesIO(data)) as img:
            frame = img.convert("RGB")
            frame.thumbnail((COVER_MAX_PIXELS, COVER_MAX_PIXELS))
            buffer = io.BytesIO()
            frame.save(buffer, format="JPEG", quality=COVER_JPEG_QUALITY, optimize=True)
            return buffer.getvalue(), "image/jpeg"
    except Exception:  # noqa: BLE001 - a broken cover must not drop the playlist
        return data, mime


def registry_entries(hass):
    """Return the entity-registry entries, or an empty list when unavailable.

    Isolated in its own function so tests can substitute a fake registry.
    """
    from homeassistant.helpers import entity_registry as er

    return list(er.async_get(hass).entities.values())


def mass_player_entities(hass) -> list[str]:
    """Return every enabled media_player entity owned by Music Assistant."""
    found: set[str] = set()
    try:
        entries = registry_entries(hass)
    except Exception:  # noqa: BLE001 - registry is optional for this feature
        entries = []
    for entry in entries:
        if entry.domain != "media_player" or entry.platform != MASS_PLATFORM:
            continue
        if entry.disabled_by is not None or entry.hidden_by is not None:
            continue
        if hass.states.get(entry.entity_id) is None:
            continue
        found.add(entry.entity_id)
    if not found:
        found = {
            entity_id
            for entity_id in hass.states.async_entity_ids("media_player")
            if entity_id.startswith(MASS_PREFIX) and hass.states.get(entity_id)
        }
    return sorted(found)


def is_available(hass, entity_id: str | None) -> bool:
    """Return True when the entity exists and is not unavailable."""
    if not entity_id:
        return False
    state = hass.states.get(entity_id)
    return state is not None and state.state not in UNAVAILABLE_STATES


def find_mass_player(hass, preferred: str | None = None) -> str | None:
    """Return the MA media_player entity to use for playback.

    ``preferred`` wins whenever it still exists (a paused or standby TV must
    stay the play target); otherwise the first available player is used.
    """
    candidates = mass_player_entities(hass)
    if preferred and hass.states.get(preferred) is not None:
        return preferred
    available = [entity_id for entity_id in candidates if is_available(hass, entity_id)]
    pool = available or candidates
    return pool[0] if pool else None


def find_owned_player(hass, model: str | None) -> str | None:
    """Return the Music Assistant player that belongs to this TV model.

    Music Assistant names a Sendspin player after the app's client name, which
    defaults to ``玉简·<Build.MODEL>`` (e.g. ``media_player.yu_jian_tb371fc``).
    Matching the TV's own model against the entity id / friendly name picks the
    TV that asked, instead of whichever MA player happens to sort first.
    """
    needle = _normalise_token(model)
    if len(needle) < 4:
        # Too short to identify anything ("tv", "h6") - would match at random.
        return None
    matches: list[str] = []
    for entity_id in mass_player_entities(hass):
        state = hass.states.get(entity_id)
        names = [entity_id, getattr(state, "name", "") or ""]
        attributes = getattr(state, "attributes", None) or {}
        names.append(str(attributes.get("friendly_name") or ""))
        if any(needle in _normalise_token(name) for name in names):
            matches.append(entity_id)
    if not matches:
        return None
    available = [entity_id for entity_id in matches if is_available(hass, entity_id)]
    return (available or matches)[0]


def _normalise_token(value: str | None) -> str:
    """Lowercase and drop punctuation so ``MiTV4-ANSM0`` matches its slug."""
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def find_browse_player(hass, preferred: str | None = None) -> str | None:
    """Return the MA entity to browse with, skipping players that are offline.

    The playlist library is source-level, so any online Music Assistant player
    can browse it; picking one that is unavailable would fail the request.
    """
    if preferred and is_available(hass, preferred):
        return preferred
    available = [
        entity_id
        for entity_id in mass_player_entities(hass)
        if is_available(hass, entity_id)
    ]
    return available[0] if available else None


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


def clients_session(hass):
    """Return Home Assistant's shared aiohttp session.

    Isolated so tests can substitute a fake session.
    """
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    return async_get_clientsession(hass)


async def async_fetch_cover_b64(hass, url: str | None) -> str | None:
    """Download a thumbnail and return it as a data URI, or None on failure."""
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        return None
    session = clients_session(hass)
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
    data, mime = shrink_cover(data, mime)
    return f"data:{mime};base64," + base64.b64encode(data).decode("ascii")


async def fetch_covers(
    hass,
    playlists: list[dict[str, Any]],
    cache: dict[str, str | None] | None = None,
) -> list[dict[str, Any]]:
    """Attach base64 covers to the playlist list with bounded concurrency.

    ``cache`` maps playlist id to an already downloaded data URI (or None when
    the cover is missing) so a periodic re-push does not refetch every image.
    """
    sem = asyncio.Semaphore(5)

    async def _one(item: dict[str, Any]) -> dict[str, Any]:
        media_id = item["id"]
        if cache is not None and media_id in cache:
            cover = cache[media_id]
        else:
            async with sem:
                cover = await async_fetch_cover_b64(hass, item.get("thumbnail"))
            if cache is not None:
                cache[media_id] = cover
        return playlist_item(item["name"], media_id, cover_b64=cover)

    return await asyncio.gather(*(_one(item) for item in playlists))
