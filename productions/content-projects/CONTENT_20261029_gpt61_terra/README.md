# GPT-6.1 Terra発表ショート

**最新はv03の直立対話・文字配置修正版。** [v03改訂記録](REVISION_V03_JA.md)を参照。女性の前傾を直し二人が直立して対話。見出し・字幕・帯を実グリフ範囲で中央配置した。全26字幕状態の実画素検査で中央誤差最大1px、元PCM・AAC一致を確認。v02を保持し、ナレーションは再生成していない。出力は `outputs/content-projects/CONTENT_20261029_gpt61_terra/v03/terra-explained-v03.mp4`。人物素材の姿勢編集はbuilt-in image_gen、会話は音声包絡による口形差分。新規MiniMax動画生成ではない。

**最新版候補は2026-10-31のv02会話版。** 既存の二人、Charon／Aoedeの音声、MiniMaxの冒頭と簡易口パク、用途の図、実画像の比較を組み合わせて再制作した。[改訂記録](REVISION_V02_JA.md)と[記事草稿v02](article-draft-v02.md)を参照。出力は `outputs/content-projects/CONTENT_20261029_gpt61_terra/v02/terra-explained-v02.mp4`。以下のv01記録は過去版として保持する。完成物の採用・人の試聴・公開とは区別する。

2026-10-29。単発1本、縦1080×1920、24fps。初稿は50秒の字幕・自作BGM版。ナレーションは未収録。

ユーザー依頼「新しくgpt6.1 Terraが発表されたので、ショート動画を作りたい」に約50秒の1本を提案し、「作成して下さい」を受領。共通ContentWorkspaceへ提案・返答原文・採用範囲・実演・出典・絵コンテ・記事を保存した。新規人物シリーズは立ち上げず、前後画像と図解を中心に制作する。最終採用・公開の承認を含まない。

## 内容と検証

架空バナーの見出し欠けをTerra APIが指摘。返されたx=780・文字60pxをPythonで適用し、全文の収まりをAI補助で確認した。入力には正しい題名・画像寸法・配置制約も渡した。1枚1回の結果であり、PCの自動操作、他モデル比較、一般的な精度、時短率、修正後の再推論は未検証。

前後画像→モデルの紹介→実回答と修正→機能の流れ→Work/Codex→選び方→人による確認、の8場面。公式画面は見出しのみを最小限引用し、日本語説明は自作の要約。モデル選択画面は独立Chromeが未ログインのため未撮影。自作結果ビューアーを製品UIとして掲載しない。

## 原本と成果物

原本・動画は `outputs/content-projects/CONTENT_20261029_gpt61_terra/v01/`。旧原本を保全する。

- `gpt61-terra-short-v01-subtitle-bgm.mp4`：50秒の映像初稿。字幕・自作BGM付き、ナレーションなし。
- `subtitles-ja-bgm-draft.srt`：映像初稿の字幕。
- `terra-api/`：要求条件・実応答・使用量。キーは含めない。
- `banner-before.png` / `banner-after.png`：1600×1000の架空バナー。
- `api-result-capture-v03.png`：実API結果を表示する自作ビューアーの実画面。1600px幅で再撮影。
- `official-heading.png`：200%表示の公式見出し引用。
- `asset-manifest.json`：寸法・hash・出典。
- `review/`：場面画像と確認用一覧。最終動画のデコード由来画像は別途保存。

最初の自作HTMLのfile URLはブラウザーに拒否された。`api-result-capture.png` はabout:blankであり、不採用・未取得の診断記録として保持。localhost表示で取り直したv02を登録した後、記事用に1600px幅のv03を取得し、同じ素材IDの版を更新した。影響した主張・場面・記事節だけ再確認し、動画の再生成は行っていない。公式画像の撮影原本は `output/playwright/terra-official-context-v01.png` に保持し、公開用と分ける。

## 音声と残作業

Gemini Aoedeの最初の1要求はHTTP402 quota_exhaustedで拒否。自動再送・課金設定変更は行わず原記録を保持。代替OpenAI日本語音声で初稿を作るか、Aoede復旧を待つか、チャットの質問で確認中。返答前に代替音声の本番生成を行わない。

人の最終試聴・スマホ実機再生・完成動画採用・YouTube公開・記事公開は未実施。記事草稿は [article-draft-v01.md](article-draft-v01.md)、出典・検証範囲は [SOURCES_JA.md](SOURCES_JA.md)。ブログへの配置・カバー・既存案内役のバナーは未制作。

## 再利用

`.venv/Scripts/python.exe productions/content-projects/CONTENT_20261029_gpt61_terra/production.py subtitle-draft` は同名MP4が存在すると上書きを拒否する。新規版は別パスで制作する。`prepare_demo.py` は送信記録があると再送しない。`record_project.py register` は登録済み案件を作り直さない。変更時はContentWorkspaceの版を進め、依存先だけ再確認する。

独立した [アーキテクチャ](ARCHITECTURE.md) と [Mermaid図](ARCHITECTURE_DIAGRAM.md) を維持する。Studio共通コードは変更していない。動画・音声・原本はGitHub保管対象とせず、軽量な制作コード・原稿・出典・検証要約のみ個人forkへ残す。
