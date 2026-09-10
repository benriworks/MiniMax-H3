from __future__ import annotations

import hashlib
import http.client
import json
from pathlib import Path
import shutil
import tempfile
import threading
import unittest

from tools.studio.server import create_server


class ScreenFontHTTPTests(unittest.TestCase):
    """Real HTTP fixture over a copied build asset; never the user's Studio DB."""

    @classmethod
    def setUpClass(cls):
        repo = Path(__file__).resolve().parents[1]
        built_font = repo / "studio/dist/template-assets/NotoSansJP-Variable.ttf"
        if not built_font.is_file():
            raise unittest.SkipTest("Build Studio before checking its distributed font over HTTP")
        cls.expected_bytes = built_font.stat().st_size
        cls.expected_digest = hashlib.sha256(built_font.read_bytes()).hexdigest()
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        workspace = Path(cls.temporary.name).resolve()
        static = workspace / "studio/dist"
        (static / "template-assets").mkdir(parents=True)
        shutil.copyfile(built_font, static / "template-assets/NotoSansJP-Variable.ttf")
        (static / "index.html").write_text("<!doctype html><title>SPA fallback sentinel</title>", encoding="utf-8")
        cls.server = create_server(workspace, host="127.0.0.1", port=0,
                                   static_dir="studio/dist", initial_refresh=False)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.addClassCleanup(cls.close_server)

    @classmethod
    def close_server(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(5)

    def request(self, method, path):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=10)
        try:
            connection.request(method, path)
            response = connection.getresponse()
            return response.status, dict((key.lower(), value) for key, value in response.getheaders()), response.read()
        finally:
            connection.close()

    def test_get_serves_exact_built_font_with_font_mime_and_no_spa(self):
        status, headers, payload = self.request("GET", "/template-assets/NotoSansJP-Variable.ttf")
        self.assertEqual(status, 200)
        self.assertEqual(headers["content-type"], "font/ttf")
        self.assertEqual(headers["x-content-type-options"], "nosniff")
        self.assertEqual(int(headers["content-length"]), self.expected_bytes)
        self.assertEqual(len(payload), self.expected_bytes)
        self.assertEqual(hashlib.sha256(payload).hexdigest(), self.expected_digest)
        self.assertNotIn("set-cookie", headers)
        self.assertNotIn(b"SPA fallback sentinel", payload)

    def test_head_has_font_metadata_and_no_response_body(self):
        status, headers, payload = self.request("HEAD", "/template-assets/NotoSansJP-Variable.ttf")
        self.assertEqual(status, 200)
        self.assertEqual(headers["content-type"], "font/ttf")
        self.assertEqual(int(headers["content-length"]), self.expected_bytes)
        self.assertEqual(payload, b"")

    def test_missing_font_is_404_not_spa_html(self):
        status, headers, payload = self.request("GET", "/template-assets/missing-font.ttf")
        self.assertEqual(status, 404)
        self.assertTrue(headers["content-type"].startswith("application/json"))
        self.assertNotIn(b"SPA fallback sentinel", payload)
        self.assertIsInstance(json.loads(payload), dict)
        self.assertNotIn("set-cookie", headers)


if __name__ == "__main__":
    unittest.main()
