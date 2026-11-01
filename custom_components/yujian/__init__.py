"""The 玉简 integration.

玉简 (Yujian) is a small Android TV app that turns the TV into a LAN notification
screen: it serves ``POST /{token}/notify`` over HTTP and draws the payload as a
tvOS-style banner. The app also broadcasts ``_yujian._tcp.local.`` (the older
``_tvnotify._tcp.local.`` is still accepted) with the
access token in the TXT record, so this integration discovers the TV and
learns the token without the user copying anything by hand.

The TV's firmware kills the app while it sits in standby, so a failed push is
retried once after reviving the app over ADB (through the Android TV
integration, which is already configured for this TV).
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT, CONF_TOKEN, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import async_extract_entity_ids

from .client import YujianClient, YujianError
from .const import BANNER_POSITIONS, DISPLAY_NAME, DOMAIN, LEGACY_NAMES, THEMES
from .coordinator import YujianCoordinator
from .tts_audio import YujianTtsError, async_speech_text_url, speech_text_for

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.NOTIFY]

# Convenience service, registered in the notify domain like the legacy
# platforms are: yujian.notify pushes a banner to every configured TV.
SERVICE_NOTIFY = "notify"

# Which voice you get:
#   off -> no speech at all
#   ha  -> Home Assistant renders the audio and the TV just plays the URL
#          (the only path that works on Android 6 TVs: no Chinese voice there)
#   tv  -> the TV app reads the title + body with its own TTS engine
SPEAK_MODES = ("off", "ha", "tv")

# Legacy booleans: true used to mean "HA synthesizes".
SPEAK_MODE_ALIASES = {True: "ha", False: "off"}


def _speak_mode(value: Any) -> str:
    """Normalise the speak option (bool or mode string) to a mode."""
    if isinstance(value, bool):
        return SPEAK_MODE_ALIASES[value]
    if value in SPEAK_MODES:
        return str(value)
    return "off"


SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required("message"): cv.string,
        vol.Optional("title"): cv.string,
        vol.Optional("duration"): vol.Coerce(int),
        vol.Optional("level"): vol.In(("info", "warn", "error")),
        vol.Optional("sticky"): cv.boolean,
        vol.Optional("sound"): cv.boolean,
        vol.Optional("max_duration"): vol.All(vol.Coerce(int), vol.Range(min=30, max=3600)),
        vol.Optional("image"): cv.string,
        vol.Optional("video"): cv.string,
        vol.Optional("notify_id"): cv.string,
        vol.Optional("position"): vol.In(BANNER_POSITIONS),
        vol.Optional("image_interval"): vol.All(vol.Coerce(int), vol.Range(min=1, max=10)),
        vol.Optional("queue"): cv.boolean,
        vol.Optional("speak"): vol.Any(cv.boolean, vol.In(SPEAK_MODES)),
        # HomeAssistant merges the call's `target` into the service data before
        # validating it, so these three keys must be part of the schema or a
        # targeted call fails with 400. They stay optional: a call without a
        # target still fans out to every TV.
        **cv.ENTITY_SERVICE_FIELDS,
    }
)

SERVICE_DISMISS = "dismiss"

# First app version that downloads and plays an audio URL passed in ``tts``
# instead of handing the string to the local TTS engine.
AUDIO_MIN_VERSION = (1, 3, 2)


def _version_tuple(version: str) -> tuple[int, ...]:
    """Turn "1.3.2" into (1, 3, 2); ignore any suffix and unparsable parts."""
    parts: list[int] = []
    for chunk in version.split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts) or (0,)

# Push the TV's own do-not-disturb switch, default banner position and theme.
SERVICE_SET_CONFIG = "set_config"

SET_CONFIG_SCHEMA = vol.Schema(
    {
        vol.Optional("muted"): cv.boolean,
        vol.Optional("position"): vol.In(BANNER_POSITIONS),
        vol.Optional("theme"): vol.In(THEMES),
        **cv.ENTITY_SERVICE_FIELDS,
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up 玉简 from a config entry."""
    client = YujianClient(
        hass,
        entry.data[CONF_HOST],
        entry.data.get(CONF_PORT, 8791),
        entry.data[CONF_TOKEN],
    )
    coordinator = YujianCoordinator(hass, entry, client)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "entry": entry,
        "client": client,
        "coordinator": coordinator,
    }
    _async_migrate_display_name(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _async_register_service(hass)

    # The first health check runs after the platforms are up, and a failure
    # must not block the setup: the TV may legitimately be off or in standby
    # (its firmware kills the app), and the entry still has to load so the
    # user can configure it and so a later push can revive the TV.
    try:
        await coordinator.async_config_entry_first_refresh()
    except (ConfigEntryNotReady, YujianError) as err:
        _LOGGER.debug("电视暂时不可达，集成照常加载: %s", err)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        if not hass.data.get(DOMAIN):
            hass.data.pop(DOMAIN, None)
            for svc in (SERVICE_NOTIFY, SERVICE_DISMISS, SERVICE_SET_CONFIG):
                if hass.services.has_service(DOMAIN, svc):
                    hass.services.async_remove(DOMAIN, svc)
    return unloaded


def _async_migrate_display_name(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Move an entry over to the current display name.

    Entries created by earlier versions carry an old default title (the mDNS
    instance name such as "TVNotify-tyeq", or "电视通知"). Those are replaced
    with the current display name; a title the user chose themselves is left
    untouched.
    """
    old_title = entry.title
    if not old_title.startswith(LEGACY_NAMES):
        return

    _LOGGER.debug("把配置项名称从 %s 迁移为 %s", old_title, DISPLAY_NAME)
    hass.config_entries.async_update_entry(
        entry,
        title=DISPLAY_NAME,
        data={**entry.data, CONF_NAME: DISPLAY_NAME},
    )


def _async_register_service(hass: HomeAssistant) -> None:
    """Register the yujian.notify convenience service."""
    if hass.services.has_service(DOMAIN, SERVICE_NOTIFY):
        return

    async def _async_handle_notify(call: ServiceCall) -> None:
        """Push a banner to the targeted TVs (all of them when none is given)."""
        title = call.data.get("title") or ""
        message = call.data["message"]

        targets = await async_extract_entity_ids(call)

        for entry_data in hass.data.get(DOMAIN, {}).values():
            entity = entry_data.get("entity")
            if entity is None:
                continue
            # `target` in the service call narrows the push to the picked
            # notify entities; without it the call fans out to every TV.
            if targets and entity.entity_id not in targets:
                continue
            extras = {
                "duration": call.data.get("duration", entity.default_duration),
                "level": call.data.get("level"),
                "sound": call.data.get("sound"),
                "sticky": call.data.get("sticky"),
                "max_duration": call.data.get("max_duration"),
                "image": call.data.get("image"),
                "video": call.data.get("video"),
                "notify_id": call.data.get("notify_id"),
                "position": call.data.get("position"),
                "tts": None,
                "image_interval": call.data.get("image_interval"),
                "queue": call.data.get("queue"),
            }

            # speak: off | ha | tv
            #   ha -> Home Assistant synthesizes title + body with the TTS
            #         entity from the options and sends the audio URL (the only
            #         voice path that works on Android 6 TVs).
            #   tv -> let the TV app read the banner with its own engine; on
            #         Android 6 that engine usually has no Chinese voice.
            speak_mode = _speak_mode(call.data.get("speak"))
            if speak_mode == "tv":
                extras["tts"] = True
            elif speak_mode == "ha":
                tts_entity = entity.tts_entity
                try:
                    extras["tts"] = await async_speech_text_url(
                        hass,
                        tts_entity or "",
                        speech_text_for(title, message),
                    )
                except YujianTtsError as err:
                    _LOGGER.warning("为 %s 合成语音失败: %s", entity.entity_id, err)
                    extras["tts"] = None
                else:
                    version = str((entity.coordinator.data or {}).get("version") or "")
                    if version and _version_tuple(version) < AUDIO_MIN_VERSION:
                        _LOGGER.warning(
                            "电视上的玉简 App 是 %s，播放音频需要 %s 以上；"
                            "这条会退化成让电视自己朗读（可能没有声音），"
                            "请把 App 升级到 %s",
                            version,
                            ".".join(map(str, AUDIO_MIN_VERSION)),
                            ".".join(map(str, AUDIO_MIN_VERSION)),
                        )
            # Push through the notify platform's own entry point so it records
            # the "last notified" timestamp -- that timestamp *is* the entity
            # state. Calling async_push() directly would send the banner but
            # leave the entity state stuck at "unknown".
            send = getattr(entity, "_async_send_message", None)
            try:
                if send is not None:
                    await send(message=message, title=title, **extras)
                else:  # pragma: no cover - fallback if HA renames the hook
                    await entity.async_push(title=title, message=message, **extras)
            # One offline TV must not abort the push to the others.
            except HomeAssistantError as err:
                _LOGGER.warning("推送到 %s 失败: %s", entity.entity_id, err)

    async def _async_handle_dismiss(call: ServiceCall) -> None:
        """Close the banner on the targeted TVs (all of them by default)."""
        targets = await async_extract_entity_ids(call)
        for entry_data in hass.data.get(DOMAIN, {}).values():
            entity = entry_data.get("entity")
            if entity is None:
                continue
            if targets and entity.entity_id not in targets:
                continue
            try:
                await entity.async_dismiss()
            except HomeAssistantError as err:
                _LOGGER.warning("关闭 %s 的横幅失败: %s", entity.entity_id, err)

    async def _async_handle_set_config(call: ServiceCall) -> None:
        """Push mute / position / theme to the targeted TVs (all by default)."""
        targets = await async_extract_entity_ids(call)
        for entry_data in hass.data.get(DOMAIN, {}).values():
            client = entry_data.get("client")
            coordinator = entry_data.get("coordinator")
            if client is None:
                continue
            entity = entry_data.get("entity")
            if targets and (entity is None or entity.entity_id not in targets):
                continue
            try:
                result = await client.async_set_config(
                    muted=call.data.get("muted"),
                    position=call.data.get("position"),
                    theme=call.data.get("theme"),
                )
            except YujianError as err:
                _LOGGER.warning("设置 %s 的电视配置失败: %s", client.host, err)
                continue
            # The endpoint echoes the TV's real state -- merge it in so the
            # entity reflects the change immediately (no poll cooldown wait).
            if coordinator is not None and isinstance(result, dict) and result:
                merged = dict(coordinator.data or {})
                merged.update({k: v for k, v in result.items() if k != "ok"})
                coordinator.async_set_updated_data(merged)

    hass.services.async_register(
        DOMAIN, SERVICE_NOTIFY, _async_handle_notify, schema=SERVICE_SCHEMA
    )
    hass.services.async_register(DOMAIN, SERVICE_DISMISS, _async_handle_dismiss)
    hass.services.async_register(
        DOMAIN, SERVICE_SET_CONFIG, _async_handle_set_config, schema=SET_CONFIG_SCHEMA
    )
