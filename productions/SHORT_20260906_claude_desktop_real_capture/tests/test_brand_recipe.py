import json
from pathlib import Path
import unittest


class BrandRecipeTests(unittest.TestCase):
    def test_visual_only_revision_preserves_recording_script_and_voice(self):
        folder = Path(__file__).resolve().parents[1]
        old = json.loads((folder / 'request.json').read_text(encoding='utf-8'))
        new = json.loads((folder / 'request-brand.json').read_text(encoding='utf-8'))
        changed = {key for key in old['recipe'].keys() | new['recipe'].keys()
                   if old['recipe'].get(key) != new['recipe'].get(key)}
        self.assertEqual(changed, {'screen_theme'})
        self.assertEqual(new['recipe']['screen_theme'], 'claude_desktop_v1')
        self.assertEqual(new['production_id'], old['production_id'])
        self.assertEqual(new['recipe_id'], old['recipe_id'])
        self.assertIn('Claude Codeの実演ではありません', new['metadata']['description'])


if __name__ == '__main__':
    unittest.main()
