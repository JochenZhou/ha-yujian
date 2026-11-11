"""Protocol regression tests. Run with Python in a Home Assistant environment.

python -m unittest discover -s tests -v
"""

import importlib
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import aiohttp
from aiohttp import web

# Load the real client without executing the integration's HA setup module.
package = types.ModuleType("yujian_protocol_test")
package.__path__ = [
    str(Path(__file__).resolve().parents[1] / "custom_components" / "yujian")
]
sys.modules[package.__name__] = package
client_module = importlib.import_module("yujian_protocol_test.client")


class ClientContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.requests = []
        self.body = {"ok": True}
        self.status = 200
        self.raw_body = None

        async def handler(request):
            payload = await request.json() if request.method == "POST" else None
            self.requests.append((request.method, request.path, payload))
            if self.raw_body is not None:
                return web.Response(
                    text=self.raw_body,
                    content_type="application/json",
                    status=self.status,
                )
            return web.json_response(self.body, status=self.status)

        app = web.Application()
        app.router.add_route("*", "/{path:.*}", handler)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        self.port = site._server.sockets[0].getsockname()[1]
        self.session = aiohttp.ClientSession()
        self.session_patch = patch.object(
            client_module, "async_get_clientsession", return_value=self.session
        )
        self.session_patch.start()
        self.client = client_module.YujianClient(
            None, "127.0.0.1", self.port, "test-token"
        )

    async def asyncTearDown(self):
        self.session_patch.stop()
        await self.session.close()
        await self.runner.cleanup()

    async def test_per_message_theme_keeps_existing_parameters(self):
        await self.client.async_notify(
            "title",
            "body",
            theme="minecraft",
            queue=True,
            notify_id="progress",
            image_interval=2,
        )
        method, path, data = self.requests[-1]
        self.assertEqual((method, path), ("POST", "/test-token/notify"))
        self.assertEqual(
            data,
            {
                "title": "title",
                "text": "body",
                "duration": 5,
                "theme": "minecraft",
                "queue": True,
                "id": "progress",
                "image_interval": 2,
            },
        )

    async def test_default_theme_is_omitted(self):
        await self.client.async_notify("", "body")
        self.assertNotIn("theme", self.requests[-1][2])

    async def test_inline_image_and_duration_bounds(self):
        await self.client.async_notify(
            "",
            "",
            image="data:image/png;base64,AAAA",
            duration=90,
            sticky=True,
            max_duration=10,
        )
        data = self.requests[-1][2]
        self.assertEqual(data["duration"], 30)
        self.assertEqual(data["maxDuration"], 30)
        self.assertIn("image_base64", data)
        self.assertNotIn("image", data)

    async def test_configuration_only_sends_supplied_fields(self):
        await self.client.async_set_config(theme="minecraft", muted=False)
        self.assertEqual(self.requests[-1][2], {"theme": "minecraft", "muted": False})

    async def test_ok_false_is_not_success(self):
        self.body = {"ok": False, "error": "unsupported"}
        with self.assertRaises(client_module.YujianError):
            await self.client.async_dismiss()

    async def test_http_error_is_not_connection_recovery_error(self):
        self.status = 404
        try:
            await self.client.async_notify("", "body")
        except client_module.YujianError as err:
            self.assertNotIsInstance(err, client_module.YujianConnectionError)
        else:
            self.fail("HTTP 404 must raise")

    async def test_invalid_json_is_reported(self):
        self.raw_body = "not json"
        with self.assertRaises(client_module.YujianError):
            await self.client.async_set_config(muted=True)

    async def test_bad_history_is_not_zero_records(self):
        self.body = {"ok": False}
        with self.assertRaises(client_module.YujianError):
            await self.client.async_history()

    async def test_history_preserves_media_key_and_is_bounded(self):
        self.body = [{"id": str(i), "has_media": True} for i in range(25)]
        result = await self.client.async_history()
        self.assertEqual(len(result), 20)
        self.assertTrue(result[0]["has_media"])

    async def test_configuration_url_updates_with_credentials(self):
        self.client.update(host="127.0.0.2", port=9999, token="replacement")
        self.assertEqual(
            self.client.configuration_url, "http://127.0.0.2:9999/replacement/ui"
        )

    async def test_network_failure_is_recoverable(self):
        await self.runner.cleanup()
        with self.assertRaises(client_module.YujianConnectionError):
            await self.client.async_notify("", "body")

    async def test_health_requires_object(self):
        self.body = []
        with self.assertRaises(client_module.YujianError):
            await self.client.async_health()


if __name__ == "__main__":
    unittest.main()
