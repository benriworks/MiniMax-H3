import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import { SCREEN_THEMES, screenTheme, screenSceneTheme, editorialChapter } from '../.test-dist/remotion/screenThemes.js';

const source = await readFile(new URL('../src/remotion/screenThemes.ts', import.meta.url), 'utf8');
const luminance = (color) => {
  const channels = color.slice(1).match(/../g).map((channel) => parseInt(channel, 16) / 255)
    .map((value) => value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4);
  return channels[0] * .2126 + channels[1] * .7152 + channels[2] * .0722;
};

test('closed theme families keep all readable text distinct from accent-only orange', () => {
  assert.deepEqual(Object.keys(SCREEN_THEMES), ['neutral_v1', 'claude_desktop_v1', 'claude_code_v1', 'technical_v1', 'claude_editorial_v1']);
  assert.equal(screenTheme(), SCREEN_THEMES.neutral_v1);
  for (const theme of Object.values(SCREEN_THEMES)) {
    for (const foreground of [theme.text, theme.muted]) {
      const values = [luminance(foreground), luminance(theme.background)].sort((a, b) => a - b);
      assert.ok((values[1] + .05) / (values[0] + .05) >= 4.5, `${theme.header}: text contrast`);
    }
  }
});

test('editorial scene contrast is opt-in and readable without mutating old themes', () => {
  const before = JSON.stringify(SCREEN_THEMES);
  const scenes = [0,1,2].map(index => screenSceneTheme('claude_editorial_v1', index));
  assert.equal(new Set(scenes.map(scene => scene.background)).size, 3);
  for (const scene of scenes) for (const foreground of [scene.text, scene.muted]) {
    const values = [luminance(foreground), luminance(scene.background)].sort((a,b) => a-b);
    assert.ok((values[1]+.05)/(values[0]+.05) >= 4.5);
  }
  for (const id of ['neutral_v1','claude_desktop_v1','claude_code_v1','technical_v1']) for (const index of [0,1,2]) assert.equal(screenSceneTheme(id,index), screenTheme(id));
  assert.equal(JSON.stringify(SCREEN_THEMES), before);
  assert.deepEqual([0,1,2].map(editorialChapter), ['導入','ポイント','まとめ']);
});

test('Claude product names stay distinct and there are no deployed logo or remote asset URLs', () => {
  assert.notEqual(SCREEN_THEMES.claude_code_v1.header, SCREEN_THEMES.claude_desktop_v1.header);
  assert.equal(SCREEN_THEMES.claude_code_v1.accent, '#d97757');
  for (const id of ['claude_code_v1', 'claude_desktop_v1']) {
    assert.match(SCREEN_THEMES[id].footer, /非公式/);
    assert.equal(Object.keys(SCREEN_THEMES[id]).some((key) => /logo|url|src/i.test(key)), false);
  }
  assert.equal(/https?:\/\//.test(source), false);
});
