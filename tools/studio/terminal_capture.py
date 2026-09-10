"""Still-only Windows Terminal adapter; never infer or run a CLI command.

Reuses the native WGC engine, one-use claims and target-change guards. Tokens
are isolated from the Claude Desktop controller. Captures the entire selected
terminal window, including visible tabs/panes; no command line or title reads.
"""
from pathlib import PureWindowsPath
import re

from .claude_capture import ClaudeCaptureController, _Win32, _fail

FAMILY = "Microsoft.WindowsTerminal_8wekyb3d8bbwe"


def terminal_package_binding(process_path, family, full_name, application_id, package_root):
    if family != FAMILY or application_id != FAMILY + "!App":
        return False
    if not re.fullmatch(r"Microsoft\.WindowsTerminal_\d+(?:\.\d+){3}_(?:x64|arm64|x86|neutral)__8wekyb3d8bbwe", full_name):
        return False
    executable, root = PureWindowsPath(process_path), PureWindowsPath(package_root)
    if not executable.is_absolute() or not root.is_absolute() or ".." in executable.parts or ".." in root.parts:
        return False
    # The installed stable MSIX manifest declares this exact relative executable.
    return executable == root / "WindowsTerminal.exe"


class TerminalWindows(_Win32):
    executable_name = "windowsterminal.exe"
    window_class = "CASCADIA_HOSTING_WINDOW_CLASS"
    package_binding = staticmethod(terminal_package_binding)


class TerminalStillController(ClaudeCaptureController):
    def _system(self):
        return TerminalWindows()

    def inspect(self, *, session_binding):
        result = super().inspect(session_binding=session_binding)
        result.update(provider="local_windows_terminal_still", cli_content_verified=False)
        result["reason"] = None if result["available"] else "terminal_window_not_available"
        for index, selection in enumerate(result["selections"]):
            selection["label"] = f"Windows Terminal {index + 1}"
        return result

    def claim(self, *args, **kwargs):
        _fail("invalid_claude_capture_request", "Terminal capture supports still images only.")

    def capture(self, *args, **kwargs):
        _fail("invalid_claude_capture_request", "Terminal capture supports still images only.")

    def capture_still(self, *args, **kwargs):
        report = super().capture_still(*args, **kwargs)
        report.update(target="selected_windows_terminal_window",
                      target_identity_policy="windows-terminal-stable-msix-v1",
                      cli_content_verified=False, command_execution_performed=False)
        return report
