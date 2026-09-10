import type { ScreenThemeId } from '../types';

export interface ScreenTheme {
  background: string;
  text: string;
  muted: string;
  accent: string;
  sourceBackground: string;
  sourceBorder: string;
  inactiveStep: string;
  header: string;
  footer: string;
}

/** Independent editorial designs, not official product UI or licensed logos.
 * The Claude palette follows Anthropic's published brand-styling colors.
 * Logo use is withheld pending documented permission; no look-alike symbol.
 */
const CLAUDE_COLORS = {
  background: '#faf9f5', text: '#141413', muted: '#585650', accent: '#d97757',
  sourceBackground: '#141413', sourceBorder: '#b0aea5', inactiveStep: '#e8e6dc',
  footer: '非公式の解説｜Anthropicの提供・協賛ではありません',
} as const;

export const SCREEN_THEMES: Readonly<Record<ScreenThemeId, ScreenTheme>> = {
  neutral_v1: {
    background: '#091726', text: '#f6faff', muted: '#a6bacb', accent: '#70e0ef',
    sourceBackground: '#020810', sourceBorder: '#34536a', inactiveStep: '#284359',
    header: '画面でわかる', footer: '',
  },
  claude_desktop_v1: { ...CLAUDE_COLORS, header: 'Claude Desktop｜操作解説' },
  claude_code_v1: { ...CLAUDE_COLORS, header: 'Claude Code｜開発ガイド' },
  technical_v1: {
    background: '#101e2c', text: '#f1f6fc', muted: '#b2c6d8', accent: '#71d6c5',
    sourceBackground: '#08121b', sourceBorder: '#486174', inactiveStep: '#304759',
    header: '技術をひとつずつ', footer: 'しくみと実画面で理解する、独立した技術解説',
  },
  claude_editorial_v1: { ...CLAUDE_COLORS, header: 'Claude Desktop｜独立解説' },
};

export const screenTheme = (id?: ScreenThemeId): ScreenTheme => SCREEN_THEMES[id ?? 'neutral_v1'];

/** Editorial chapter contrast is opt-in; historical theme geometry/colors stay unchanged. */
export const screenSceneTheme = (id: ScreenThemeId | undefined, index: number): ScreenTheme => {
  const base = screenTheme(id);
  if (id !== 'claude_editorial_v1') return base;
  if (index === 1) return { ...base, background: '#ffffff' };
  if (index >= 2) return { ...base, background: '#24211f', text: '#faf9f5', muted: '#d6ccc4', inactiveStep: '#62564e', sourceBorder: '#a09185' };
  return { ...base, background: '#f4e6dc' };
};

export const editorialChapter = (index: number): string => ['導入', 'ポイント', 'まとめ'][index] ?? 'ポイント';
