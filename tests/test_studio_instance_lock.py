from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.studio.instance_lock import (
    StudioInstanceLockError,
    WorkspaceInstanceLock,
)


class WorkspaceInstanceLockTests(unittest.TestCase):
    def test_same_process_second_owner_is_rejected_and_close_releases(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary).resolve()
            first = WorkspaceInstanceLock(workspace)
            try:
                self.assertEqual(
                    first.path,
                    workspace / "outputs" / "studio" / "studio.instance.lock",
                )
                self.assertTrue(first.path.is_file())
                with self.assertRaises(StudioInstanceLockError):
                    WorkspaceInstanceLock(workspace)
            finally:
                first.close()

            replacement = WorkspaceInstanceLock(workspace)
            replacement.close()
            replacement.close()

    def test_subprocess_cannot_acquire_until_owner_closes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary).resolve()
            owner = WorkspaceInstanceLock(workspace)
            script = """
import sys
from pathlib import Path
from tools.studio.instance_lock import StudioInstanceLockError, WorkspaceInstanceLock

try:
    lock = WorkspaceInstanceLock(Path(sys.argv[1]))
except StudioInstanceLockError:
    raise SystemExit(23)
else:
    lock.close()
    raise SystemExit(0)
"""
            repository = Path(__file__).resolve().parents[1]
            try:
                blocked = subprocess.run(
                    [sys.executable, "-c", script, str(workspace)],
                    cwd=repository,
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
                self.assertEqual(
                    blocked.returncode,
                    23,
                    msg=f"stdout={blocked.stdout!r} stderr={blocked.stderr!r}",
                )
            finally:
                owner.close()

            acquired = subprocess.run(
                [sys.executable, "-c", script, str(workspace)],
                cwd=repository,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            self.assertEqual(
                acquired.returncode,
                0,
                msg=f"stdout={acquired.stdout!r} stderr={acquired.stderr!r}",
            )


if __name__ == "__main__":
    unittest.main()
