"""Isolated Studio HTTP/SQLite with fake native controls. No real app operations."""
import json
import shutil
import sys
import threading
import uuid
from pathlib import Path

from tools.studio.server import create_server
from tests.test_studio_claude_control import install_fake


def main():
    repo = Path(__file__).resolve().parents[1]
    root = repo / "studio/output/playwright" / ("claude-control-" + uuid.uuid4().hex)
    root.mkdir(parents=True)
    shutil.copytree(repo / "studio/dist", root / "ui")
    server = create_server(root, port=0, static_dir=root / "ui", session_token="control-fixture-" + "x" * 32)
    install_fake(server.service)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    print(json.dumps({"studio_url": f"http://127.0.0.1:{server.server_address[1]}", "workspace": str(root), "native_boundary": "synthetic_only"}), flush=True)
    try: sys.stdin.readline()
    except KeyboardInterrupt: pass
    finally: server.shutdown(); server.server_close(); thread.join(timeout=5)


if __name__ == '__main__': main()
