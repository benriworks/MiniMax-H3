"""Isolated real Studio/SQLite/HTTP with synthetic native PNG, for UI verification.

No desktop pixel acquisition, commands or user app operations. Fixture only.
"""
from dataclasses import replace
from unittest import mock
from PIL import Image, ImageDraw
from tools.studio import claude_capture as capture
from tools.studio.terminal_capture import TerminalStillController, TerminalWindows
from tests.test_studio_claude_capture import FakeSystem, WINDOW
from tests.still_library_live_server import main

native_capture_still = TerminalStillController.capture_still


def fixture_capture_still(controller, *args, **kwargs):
    report = native_capture_still(controller, *args, **kwargs)
    report.update(actual_capture_performed=False, synthetic_fixture=True, engine='synthetic_terminal_fixture')
    return report


def resolve(controller):
    path = controller.workspace / 'fixture-engine.txt'
    path.write_bytes(b'SYNTHETIC TEST ENGINE - NO REAL CAPTURE')
    return {'ffmpeg': str(path), 'ffmpeg_sha256': capture._sha(path)}


def process(args, **kwargs):
    image = Image.new('RGB', (1100, 700), '#142434')
    draw = ImageDraw.Draw(image)
    draw.text((45, 50), 'SYNTHETIC TERMINAL FIXTURE', fill='white', font_size=36)
    draw.text((45, 120), 'UI / API / library integration test only', fill='#8dd8c1', font_size=26)
    draw.text((45, 185), 'No real CLI capture. No command was executed.', fill='white', font_size=24)
    image.save(args[-1])
    return 0, b'', b''


if __name__ == '__main__':
    system = FakeSystem()
    system.current = replace(WINDOW, width=1100, height=700, window_class=TerminalWindows.window_class)
    with mock.patch.object(TerminalStillController, '_system', return_value=system), \
         mock.patch.object(TerminalStillController, '_resolve_tools', resolve), \
         mock.patch.object(TerminalStillController, 'capture_still', fixture_capture_still), \
         mock.patch.object(capture.native, '_run_contained_process', side_effect=process):
        main()
