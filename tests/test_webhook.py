"""Tests for the play webhook's token resolution logic."""

import importlib
import sys
import types
import unittest
from pathlib import Path

package = types.ModuleType("yujian_webhook_test")
package.__path__ = [
    str(Path(__file__).resolve().parents[1] / "custom_components" / "yujian")
]
sys.modules[package.__name__] = package
webhook = importlib.import_module("yujian_webhook_test.webhook")


class ResolveRuntimeTests(unittest.TestCase):
    def test_resolves_by_token(self):
        runtime = {"callback_token": "abc"}
        data = {"entry1": runtime, "_flag": True}
        self.assertIs(webhook.resolve_runtime("abc", data), runtime)

    def test_rejects_wrong_token(self):
        data = {"entry1": {"callback_token": "abc"}}
        self.assertIsNone(webhook.resolve_runtime("xyz", data))

    def test_rejects_missing_or_empty_token(self):
        data = {"entry1": {"callback_token": "abc"}}
        self.assertIsNone(webhook.resolve_runtime(None, data))
        self.assertIsNone(webhook.resolve_runtime("", data))

    def test_empty_data(self):
        self.assertIsNone(webhook.resolve_runtime("abc", {}))


if __name__ == "__main__":
    unittest.main()
