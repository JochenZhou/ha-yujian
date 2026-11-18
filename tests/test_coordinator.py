"""Unit tests for YujianCoordinator Sendspin/WLED polling and playlist-loss detection."""

import asyncio
import importlib
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

package = types.ModuleType("yujian_coordinator_test")
package.__path__ = [
    str(Path(__file__).resolve().parents[1] / "custom_components" / "yujian")
]
sys.modules[package.__name__] = package
client_mod = importlib.import_module("yujian_coordinator_test.client")
coord_mod = importlib.import_module("yujian_coordinator_test.coordinator")


def _fake_hass():
    return SimpleNamespace(
        loop=asyncio.get_running_loop(),
        data={},
        config_entries=SimpleNamespace(async_update_entry=MagicMock()),
    )


def _fake_entry():
    return SimpleNamespace(
        entry_id="entry_1",
        unique_id="192.168.101.14",
        data={"host": "192.168.101.14", "model": "MiTV4-ANSM0"},
        options={},
        async_on_unload=MagicMock(),
    )


class CoordinatorTests(unittest.IsolatedAsyncioTestCase):
    async def test_polls_sendspin_wled_fields_and_falls_back_cleanly_on_old_app(self):
        client = MagicMock()
        client.configuration_url = "http://192.168.101.14:8791/tok/ui"
        client.async_health = AsyncMock(
            return_value={
                "ok": True,
                "version": "1.10.3",
                "uptime": 120,
                "model": "MiTV4-ANSM0",
                "playlist_count": 27,
            }
        )
        client.async_history = AsyncMock(return_value=[])
        client.async_sendspin_status = AsyncMock(
            return_value={
                "player_style": "cover_blur",
                "wled_sync_enabled": True,
                "wled_sync_port": 11988,
                "wled_color_sync_enabled": False,
                "wled_color_host": "192.168.101.206",
                "wled_effect": "gravcentric",
                "playlist_count": 27,
            }
        )
        coordinator = coord_mod.YujianCoordinator(_fake_hass(), _fake_entry(), client)
        fake_reg = SimpleNamespace(
            async_get_device_by_identifier=MagicMock(return_value=None)
        )
        with patch.object(coord_mod.dr, "async_get", return_value=fake_reg):
            data = await coordinator._async_update_data()

        self.assertTrue(data["sendspin_config_available"])
        self.assertEqual(data["player_style"], "cover_blur")
        self.assertTrue(data["wled_sync_enabled"])
        self.assertEqual(data["wled_sync_port"], 11988)
        self.assertEqual(data["wled_color_host"], "192.168.101.206")
        self.assertEqual(data["wled_effect"], "gravcentric")
        self.assertEqual(data["playlist_count"], 27)

        client.async_sendspin_status = AsyncMock(
            side_effect=client_mod.YujianError("HTTP 404")
        )
        with patch.object(coord_mod.dr, "async_get", return_value=fake_reg):
            legacy = await coordinator._async_update_data()
        self.assertFalse(legacy["sendspin_config_available"])

    async def test_detects_playlist_drop_to_zero_and_triggers_restart_hook(self):
        client = MagicMock()
        client.configuration_url = "http://192.168.101.14:8791/tok/ui"
        client.async_history = AsyncMock(return_value=[])
        client.async_sendspin_status = AsyncMock(return_value={})
        coordinator = coord_mod.YujianCoordinator(_fake_hass(), _fake_entry(), client)
        triggered = []
        coordinator.on_device_restart = lambda: triggered.append(True)
        fake_reg = SimpleNamespace(
            async_get_device_by_identifier=MagicMock(return_value=None)
        )

        client.async_health = AsyncMock(
            return_value={"ok": True, "uptime": 100, "playlist_count": 27}
        )
        with patch.object(coord_mod.dr, "async_get", return_value=fake_reg):
            await coordinator._async_update_data()
        self.assertEqual(len(triggered), 0)

        client.async_health = AsyncMock(
            return_value={"ok": True, "uptime": 160, "playlist_count": 0}
        )
        with patch.object(coord_mod.dr, "async_get", return_value=fake_reg):
            await coordinator._async_update_data()
        self.assertEqual(len(triggered), 1)
