# 出典と撮影の範囲

確認日：2026-10-31。調査と個別の実機反映を区別する。

| ID | 出典 | 用途 |
| --- | --- | --- |
| ultra_help | [What is the Ultra plan?](https://support.claude.com/en/articles/17728952-what-is-the-ultra-plan) | 改称、自動移行、Web価格、認証、5時間制限、残る週上限、確認手順 |
| ultra_price | [Claude Pricing](https://claude.com/pricing) | 月額200ドルと認証済みアカウントという脚注を照合 |
| account_release | [ChatGPT release notes](https://help.openai.com/en/articles/6825453-chatgpt-release-notes) | 2026-10-30のiOS/Androidへの順次提供発表 |
| account_help | [Using multiple ChatGPT accounts on web and mobile](https://help.openai.com/en/articles/20001068-using-multiple-chatgpt-accounts-on-web-and-mobile) | 最大2件、設定手順、データと契約の分離、通知、公式掲載の画面例 |

旧slugの検索結果には「モバイル未対応」という古い本文が残っていた。新しい公式本文と当日のリリースノートを直接読み、仕様の採用根拠とした。検索断片を最新仕様として使わない。Claudeの告知原投稿の直接取得、10/30の発表時刻、全対象への反映完了は未確認。本編では確認日を示し、個別反映を断定しない。

引用は公式画面の必要部分へ限定し、自作図と見た目・来歴を分ける。Claudeヘルプは条件の7語、価格の10語、認証の見出し7語の合計24語の抜粋。ChatGPTは公式掲載の架空アカウントの画像と、設定手順の短い抜粋を使う。元画面は `outputs/.../captures/`、切り出しと画素一致の検査、座標、URL、bytes、SHA-256は `asset-manifest.json`。原文の数字やUIを描き直さない。

PC撮影はComputer Use。Claudeデスクトップの入口とログイン済みChromeの設定→使用量を確認し、原本を `_private/captures/` へ保存した。実表示はMaxとセッション欄であり、Ultra適用の実証にしない。公開用の公式キャプチャにユーザー環境の情報を混ぜない。Android SDK adbの接続端末0、Computer Useに端末ミラーなし。実機での切替・通知動作は未検証。

公式画面原本は約1236〜1251px幅で保存。小さな引用切り出しは原寸を記録し、高解像度化と呼ばない。記事用の説明図は別に1600×900で作り、原本と派生を区別する。

blogの[AGENTS](https://github.com/benriworks/blog/blob/main/AGENTS.md)、[画像規定](https://github.com/benriworks/blog/blob/main/docs/visual-identity.md)、[文体](https://github.com/benriworks/blog/blob/main/docs/tone-and-manner.md)、指定の日本語文章規範2冊を読んだ。記事は共通Markdown草稿で、blogへの配置・MDX検査・公開は行わない。動画の人物をblog共通の案内役と無条件に置き換えない。公開用写真・バナーは未作成。
