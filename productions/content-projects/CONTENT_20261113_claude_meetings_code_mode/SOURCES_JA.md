# 一次資料・撮影記録

ニュースの日付は2026年11月13日。取得・照合日は11月14日（JST）。

| 根拠 | 内容 |
| --- | --- |
| [Claude Meetings公式発表](https://claude.com/ja/resources/articles/claude-meetings) | 11月12日付。会議参加、ボード、会議ページの掲載画像3点。画像と掲載URLは sources.json。 |
| [公式ヘルプ](https://support.claude.com/en/articles/18325154-use-claude-meetings)・[更新履歴](https://support.claude.com/en/articles/12138966-release-notes) | Google Calendar、全員の同意、組織設定、提供範囲、利用量と期限。外部ゲストの既定値はプラン別のヘルプの記載を採用。 |
| [Code Mode公式ガイド](https://code.claude.com/docs/en/code-mode)・[公式Markdown](https://code.claude.com/docs/en/code-mode.md) | 対応モデル、端末、アカウント、OS条件、既定無効。HTMLを独立した公開ページ用ブラウザーで表示し、Markdownも取得。 |
| [Claude Code v2.1.323](https://github.com/anthropics/claude-code/releases/tag/v2.1.323) | 公式リリースの published_at は2026-11-12T22:12:13Z。国内では11月13日7:12。 |
| [ChatGPT Wallet](https://openai.com/index/introducing-chatgpt-wallet/)・[ChatGPT・Codex変更履歴](https://learn.chatgpt.com/docs/changelog) | 同日付の米国対象Pro向け順次展開とCodex CLIの更新。 |
| [ハッピータイム](https://amachamusic.chagasi.com/music_happytime.html)・[甘茶の音楽工房 利用規約](https://amachamusic.chagasi.com/terms.html) | 明るいポップ。ローカル保管原曲のhashを照合。動画のBGMとして利用。投稿メモは「Content ID登録なし」。 |

## ユーザーPCでの実画面確認

Windowsで起動済みのClaude DesktopウィンドウをComputer Useで確認した。内容を読めない黒い取得結果だったため、ログイン状態とMeetingsメニューは判定できなかった。Chromeは公式ヘルプから得た `claude.ai/meetings` を新規タブで開く試行で現在URLの確認ができず、ログイン済みブラウザーでの操作は停止。会議の招待や文字起こしは未実施。CLIの `claude --version` は2.1.316で、Code Modeの条件は2.1.323以降。現PCのMeetings実画面・Code Mode実行は採録できていない。

## 引用と配布用の素材

掲載元から取得した3枚のPNGは3840×2160、3840×2160、1920×1080。公式発表の見出し、ヘルプの追加手順、Code Mode公式ガイドは分離された1600×1050のChromiumで公開ページを取得した。動画の詳細画面と本文用の切り出しは原本と対応付け、文字やUIを書き換えず、動画では原図の外に見どころと日本語説明を表示する。掲載元・権利者を示した機能説明の引用候補として扱う。元画像・撮影HTML・ローカル曲はローカルに保管。

`captures/figures/manifest.json` は確認日、掲載URL、元画像、座標、実寸、容量、SHA-256を記録。ブログ用に渡す画像は最大幅1600pxのWebP。原図に含まれる英語の細部を本文にも日本語で説明する。Code Modeの操作比較は公式ガイドに基づく説明図。
