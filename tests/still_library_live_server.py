"""Isolated real Studio + deterministic local page, owned by UI integration tests.

No mocks of the Studio API or capture worker. No production workspace DB is used.
Send a line on stdin (or Ctrl-C) to stop both servers and close their workers.
"""
import argparse
import json
import shutil
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PIL import Image
from tools.studio.server import create_server


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    root = (args.workspace or repo / 'studio/output/playwright' / ('still-live-' + uuid.uuid4().hex)).resolve()
    root.mkdir(parents=True, exist_ok=False)
    shutil.copytree(repo / 'studio/dist', root / 'ui')
    production = root / 'productions/TEST_still_library'
    (production / 'manifests').mkdir(parents=True)
    (production / 'PRODUCTION_RECORD_JA.md').write_text('# Still image import fixture', encoding='utf-8')
    (production / 'manifests/source-hashes.json').write_text(json.dumps({'production_id': 'TEST_still_library', 'status': 'draft'}), encoding='utf-8')
    Image.new('RGB', (480, 320), '#b0cbd1').save(production / 'import-fixture.png')
    fixture = (repo / 'tests/fixtures/still-library-page.html').read_bytes()

    class Page(BaseHTTPRequestHandler):
        def do_GET(self):
            body = fixture
            if self.path == '/remote': body += b'<img src="http://example.invalid/no-network.png">'
            if self.path == '/large': body += b'<div style="height:20000px">Too tall</div>'
            if self.path == '/failure': body = b'<h1>Failure fixture</h1>'
            self.send_response(500 if self.path == '/failure' else 200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers(); self.wfile.write(body)
        def log_message(self, *args): pass

    page = ThreadingHTTPServer(('127.0.0.1', 0), Page)
    studio = create_server(root, port=0, static_dir=root / 'ui', session_token='still-local-fixture-session-' + 'x' * 32)
    threads = [threading.Thread(target=server.serve_forever, daemon=True) for server in (page, studio)]
    for thread in threads: thread.start()
    print(json.dumps({'studio_url': f'http://127.0.0.1:{studio.server_address[1]}', 'fixture_url': f'http://127.0.0.1:{page.server_address[1]}', 'workspace': str(root)}), flush=True)
    try: sys.stdin.readline()
    except KeyboardInterrupt: pass
    finally:
        for server in (studio, page): server.shutdown(); server.server_close()
        for thread in threads: thread.join(timeout=5)


if __name__ == '__main__': main()
