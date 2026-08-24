from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.studio.secrets import SecretStore


class SecretResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name).resolve()
        self.store = SecretStore(self.workspace)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_environment_secret_is_resolved_but_never_returned_by_status(self) -> None:
        secret = "environment-elevenlabs-secret"
        with mock.patch.dict(os.environ, {"ELEVENLABS_API_KEY": secret}, clear=False):
            self.assertEqual(self.store.resolve("elevenlabs"), secret)
            status = self.store.statuses()
        self.assertNotIn(secret, json.dumps(status))
        self.assertTrue(next(item for item in status if item["id"] == "elevenlabs")["configured"])

    def test_dotenv_secret_is_resolved_without_becoming_status_data(self) -> None:
        secret = "dotenv-elevenlabs-secret"
        (self.workspace / ".env").write_text(
            f'IGNORED=value\nELEVENLABS_API_KEY="{secret}"\n',
            encoding="utf-8",
        )
        with mock.patch.dict(os.environ, {"ELEVENLABS_API_KEY": ""}, clear=False):
            self.assertEqual(self.store.resolve("elevenlabs"), secret)
            status = self.store.statuses()
        self.assertNotIn(secret, json.dumps(status))

    def test_unknown_provider_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.store.resolve("unknown")


if __name__ == "__main__":
    unittest.main()
