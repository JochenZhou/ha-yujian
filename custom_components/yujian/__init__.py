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

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT, CONF_TOKEN, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .client import YujianClient, YujianError
from .const import BANNER_POSITIONS, DISPLAY_NAME, DOMAIN, LEGACY_NAMES
from .coordinator import YujianCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.NOTIFY]

# Convenience service, registered in the notify domain like the legacy
# platforms are: yujian.notify pushes a banner to every configured TV.
SERVICE_NOTIFY = "notify"

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
        vol.Optional("tts"): vol.Any(cv.boolean, cv.string),
        vol.Optional("image_interval"): vol.All(vol.Coerce(int), vol.Range(min=1, max=10)),
        vol.Optional("queue"): cv.boolean,
    }
)

SERVICE_DISMISS = "dismiss"

# Push the TV's own do-not-disturb switch and default banner position.
SERVICE_SET_CONFIG = "set_config"

SET_CONFIG_SCHEMA = vol.Schema(
    {
        vol.Optional("muted"): cv.boolean,
        vol.Optional("position"): vol.In(BANNER_POSITIONS),
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
        """Push a banner to every configured TV."""
        title = call.data.get("title") or ""
        message = call.data["message"]

        for entry_data in hass.data.get(DOMAIN, {}).values():
            entity = entry_data.get("entity")
            if entity is None:
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
                "tts": call.data.get("tts"),
                "image_interval": call.data.get("image_interval"),
                "queue": call.data.get("queue"),
            }
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
        """Close the banner currently shown on every configured TV."""
        for entry_data in hass.data.get(DOMAIN, {}).values():
            entity = entry_data.get("entity")
            if entity is None:
                continue
            try:
                await entity.async_dismiss()
            except HomeAssistantError as err:
                _LOGGER.warning("关闭 %s 的横幅失败: %s", entity.entity_id, err)

    async def _async_handle_set_config(call: ServiceCall) -> None:
        """Push mute / default-position changes to every configured TV."""
        for entry_data in hass.data.get(DOMAIN, {}).values():
            client = entry_data.get("client")
            coordinator = entry_data.get("coordinator")
            if client is None:
                continue
            try:
                result = await client.async_set_config(
                    muted=call.data.get("muted"),
                    position=call.data.get("position"),
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
