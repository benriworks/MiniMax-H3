from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from tools.studio.remotion_timeline import _FIRST_PARTY_SOURCE_PATHS, _stage_screen_font
from tools.studio.remotion_timeline_execution import RemotionTimelineError


class ScreenThemeAssetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name).resolve()
        self.public = self.workspace / "staging/public"
        self.public.mkdir(parents=True)
        self.font = self.workspace / _FIRST_PARTY_SOURCE_PATHS["screen_font_asset"]
        self.font.parent.mkdir(parents=True)
        self.font.write_bytes(b"fixed test font")
        self.identity = {"screen_font_asset": {"sha256": hashlib.sha256(self.font.read_bytes()).hexdigest().upper()}}
        self.clips = [{"layout_preset": "screen_explainer_v1"}]

    def tearDown(self):
        self.temp.cleanup()

    def test_only_fixed_font_is_copied_and_non_screen_stages_nothing(self):
        (self.font.parent / "unapproved.ttf").write_bytes(b"do not copy")
        _stage_screen_font(self.workspace, self.public, [], self.identity)
        self.assertEqual(list(self.public.iterdir()), [])
        _stage_screen_font(self.workspace, self.public, self.clips, self.identity)
        files = [item.relative_to(self.public).as_posix() for item in self.public.rglob("*") if item.is_file()]
        self.assertEqual(files, ["template-assets/NotoSansJP-Variable.ttf"])

    def test_missing_identity_rejects_before_copy(self):
        with self.assertRaises(RemotionTimelineError):
            _stage_screen_font(self.workspace, self.public, self.clips, {})
        self.assertEqual(list(self.public.iterdir()), [])

    def test_existing_destination_is_not_overwritten(self):
        existing = self.public / "template-assets/NotoSansJP-Variable.ttf"
        existing.parent.mkdir()
        existing.write_bytes(b"preserve existing")
        with self.assertRaises(RemotionTimelineError):
            _stage_screen_font(self.workspace, self.public, self.clips, self.identity)
        self.assertEqual(existing.read_bytes(), b"preserve existing")

    def test_symlink_font_is_rejected(self):
        actual = self.font.with_name("actual.ttf")
        self.font.rename(actual)
        try:
            self.font.symlink_to(actual)
        except OSError:
            self.skipTest("symlink creation is unavailable")
        with self.assertRaises(RemotionTimelineError):
            _stage_screen_font(self.workspace, self.public, self.clips, self.identity)

    @unittest.skipUnless(shutil.which("node"), "Node is required")
    def test_node_renderer_validator_accepts_only_screen_themes(self):
        renderer = Path(__file__).resolve().parents[1] / "tools/studio/remotion_render.mjs"
        # Run the actual pure validator, never the expensive rendering entrypoint.
        javascript = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(process.argv[1], 'utf8');
const body = source.slice(source.indexOf('const SCHEMA_VERSION'), source.indexOf('if (process.argv.length !== 4)'));
const context = vm.createContext({});
vm.runInContext(body + ';globalThis.validate = validateInputProps;', context);
const base = {schemaVersion:1,width:1080,height:1920,fps:24,durationInFrames:24,clips:[{
src:'clip-00.mp4',startMs:0,endMs:1000,trimBeforeFrame:0,trimAfterFrame:24,durationInFrames:24,
volumePercent:0,transitionToNext:null,overlay:null,layoutPreset:'screen_explainer_v1'}]};
const pass = (clip) => { try {context.validate({...base,clips:[clip]});return true;} catch {return false;} };
const themes = ['neutral_v1','claude_desktop_v1','claude_code_v1','technical_v1','claude_editorial_v1'];
const invalid = [null,{},[],true,1,'orange','../font.ttf'];
const answers = [pass(base.clips[0]), ...themes.map(screenTheme=>pass({...base.clips[0],screenTheme})),
...invalid.map(screenTheme=>pass({...base.clips[0],screenTheme})),
pass({...base.clips[0],screenTheme:'neutral_v1',layoutPreset:'full_bleed_v1'})];
process.stdout.write(JSON.stringify(answers));
"""
        result = subprocess.run([shutil.which("node"), "-e", javascript, str(renderer)],
                                capture_output=True, text=True, check=True, timeout=10)
        self.assertEqual(json.loads(result.stdout), [True] * 6 + [False] * 8)


if __name__ == "__main__":
    unittest.main()
