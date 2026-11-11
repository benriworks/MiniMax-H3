# 出典・撮影・検証範囲

確認日：2026-10-29 JST。発表・リリース：2026-10-26。週刊ページの日付は10月26〜30日で、撮影時は10月28日の別告知も追加されていた。

| ID | 出典 | 使う内容 |
| --- | --- | --- |
| official_launch | https://learn.chatgpt.com/docs/whats-new/october-26-30-2026 | 画像理解・PC操作、Work/Codex、プラン、Advanced、Chat非対応 |
| official_model | https://developers.openai.com/api/docs/models/gpt-6.1-terra | モデルID、画像入力、Responses API |
| voice_docs | https://developers.openai.com/api/docs/guides/text-to-speech | 代替音声候補の仕様。生成音声の明示を概要欄に付ける |

公式画像は解説の根拠として見出しだけを必要最小限で引用。製品画像の自由な再配布として利用しない。元の公式ページをChrome/Playwrightで表示し、表示倍率200%の見出しを撮影。本文やブランド写真の転載は行わない。引用名義は「OpenAI公式資料」、URLと確認日は概要欄へ記載。取得・公開用画像・寸法・hashは素材台帳から追う。フルページ原本は公開用画像と分ける。

前のターンのComputer UseはURLを判定できず停止。このターンでは独立Chromeから公式ページを開いて保存できた。chatgpt.comも開いたが未ログイン。既存の個人ブラウザー認証・会話へアクセスせず、ログイン操作はしていない。この経路の未ログインをユーザーアカウントの利用不可と一般化しない。

実演はResponses APIへの画像入力、回答JSONの取得、制作側Pythonでの提案値反映。応答モデルはgpt-6.1-terra。実際のcomputer-useツール呼出しは0回。正しい見出しと配置制約を含む入力で1件・1回。結果の一般化、時短率、他モデルへの優位性を主張しない。修正画像の再推論も未実施。

ブログ側 `benriworks/blog` のAGENTS.mdと `docs/visual-identity.md` をGitHubの実ファイルから確認した。記事草稿と候補画像のみ。カバー写真、既存案内役のバナー、MDX配置、記事採用、公開は残作業。
