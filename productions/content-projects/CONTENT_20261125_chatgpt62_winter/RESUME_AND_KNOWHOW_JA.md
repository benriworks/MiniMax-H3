# ChatGPTのチャットに来たGPT-6.2｜制作と再開

更新日 2026-11-25 JST。案件 `CONTENT_20261125_chatgpt62_winter`。[制作索引](../../../docs/video-production/README.md) → [制作総覧](../../../docs/video-production/PRODUCTION_KNOWHOW_JA.md) → 本書。前回の開発環境向けAstra・Sol編は `CONTENT_20261118_gpt62_astra_sol` の別案件。

## 現在地

冬服の男女で、Chatに登場した会話向けGPT-6.2 Solを説明する2本のレビュー版を完成。11月25日の実際の選択画面・架空の料金表・初回の返信と再質問を収録。どちらも最初のフレームと最初の男性の台詞に結論がある。役割・衣装・選択した声と依頼原文は[絵コンテと編集レビュー](REQUEST_AND_EDIT_JA.md)、事実と引用は[出典](SOURCES_JA.md)、投稿セットは[タイトルと概要欄](YOUTUBE_DRAFTS_JA.md)。

| 動画 | 実尺・画角 | その版で扱う内容・検証 |
| --- | --- | --- |
| chatgpt62-chat-short v01 | 49.917秒、1080×1920、24fps、1,198フレーム | 男4・女3発話。料金表→22,000円→徒歩5分で該当なし。15字幕状態。全映像・音声をデコード、最終AAC −16.15 LUFS、−1.74 dBTP。完成MP4から24フレームを抽出。 |
| chatgpt62-chat-full v01 | 3分17.542秒、1920×1080、24fps、4,741フレーム | 男9・女8発話。実機の選び方、条件比較、公式の画像理解と指示追従のグラフ、対象プラン。43字幕状態。全デコード、最終AAC −16.05 LUFS、−1.56 dBTP。完成MP4から62フレームを抽出。 |

担当PCのChrome上でDriveの縦横両方の映像と再生時間の進行を確認。ショートは0:09、フルは0:07でいったん停止。Driveの8点すべてで名前・容量・親フォルダー・非共有を確認。人による全編試聴、スマホ実機、完成版採用、YouTube・記事公開は未確認。次の作業はレビュー返答を対象版に結び付けること。

## 素材・実行環境と所在

媒体のルートは主cloneの `outputs/content-projects/CONTENT_20261125_chatgpt62_winter/`。コードは個人forkの `codex/chatgpt62-winter-20261125`、分岐元 `a511022`。媒体原本はGit外。SHA-256・bytes・対応する素材は [media-manifest.json](media-manifest.json) に記録する。

- `release/v01/short/chatgpt62-chat-short-v01.mp4` と `release/v01/full/chatgpt62-chat-full-v01.mp4`。各フォルダーの `timeline.json`、`captions.srt`、`verification.json`、`encoded-review/` が対応する。
- `cast/winter-pair.png` は既存の架空の成人2人を元にした冬服の基準画。参照元は `CONTENT_20261030_chatgpt_pro_usage_news/characters/{male,female}-reference.png`。顔・髪・席を引き継ぎ、男性は紺の冬ニット、女性はアイボリーのケーブル編みとえんじのハイネック。冬服画像は新規生成、`motion/winter-duet` と `motion/winter-study` はこの1枚から作った新規H3素材。二人の並びから、相手へ身を向ける、考え込む、指を立てる動きを個別に切り出した。
- 先行した個別人物4カットは送信時の読み取りタイムアウトで受付IDが得られなかった。同じ4件の再送はしていない。APIのタスク照会にはIDが必要。MiniMaxコンソールは時間帯ごとの使用量集計で、該当4件の受付・課金は特定できなかった。別構図として受領した二人動画の使用秒数は6秒と8秒。保存した映像と受付を照合した。
- 音声は全採用台詞で `gemini-3.8-flash-tts`。既存のCharon/Aoedeの声名を継承し、音声本体は今回録音した。冒頭の1台詞のみ両版で共用。BGMは共通のオリジナル曲生成と `explanation_v1`、ショートbright・フルcalm。人が収録した音声、外部曲は使用していない。
- `youtube/v01/` に縦横のJPEG、タイトル、貼り付け用概要欄、幅180px・320pxの確認画像。`article/v01/` は[記事草稿](article-draft.md)をHTML・Markdownと画像6枚で格納したZIP。11メンバーのCRC・ハッシュ、390pxと1280pxの表示幅と全画像読込みを照合。共通Studioはrevision 12。DriveのファイルID・PCの再生確認はローカルの `_private/drive-verification.json` 、`qa/drive-*.png` に保管。
- Windows、Python 3.12.2、Pillow 12.3.0、OpenCV 4.11.0、NumPy 1.26.4、FFmpeg 8.1.2。`studio/public/template-assets/NotoSansJP-Variable.ttf`。実画面と配布用切り出し、公式原図、ローカルASR、採用別WAVの対応は[制作構成](ARCHITECTURE.md)と[図](ARCHITECTURE_DIAGRAM.md)を参照。

## 制作履歴と今回の学び

1. 11月23日の発表と11月17日の発表を分け、ユーザー指定の2形式を企画。実画面で6.2 Instantを選択。宿の料金表をアップロードし、2回の回答・実額を確認してから台本にした。
2. 既存男女の輪郭と髪を維持した冬服を生成。別目的の二人動画を2テイク収録し、10,400円の宿泊料金と600円の朝食を図で分けて描いた。
3. フルの導入で初回のモデル番号を2方式が「6.3」と認識。再録の一つではモデル名も聞き取りが不安定だったため、正式名を画面に大きく記し、台詞を「画面に出ているモデル」に変更。日本語終了後に英語の演出指示が混入したテイクの、自然な無音までの10.98秒だけを使った。この採用区間だけを別ファイルから原稿非提示で書き起こし、日本語全文と終端を再確認した。料金、両評価、対象プランの認識差も、単独の音声と公式の表記で照合した。
4. 2本を個別に全デコードし、実フレームで視点・字幕・情報位置を確認。タイトル、概要欄とサムネイルを添えてDriveでレビュー可能にした。冬服と題材は今回の指定。複数台詞を一括認識した結果と単独の結果が異なる場合の確認手順を制作総覧に記録した。既存の音声・字幕規約で運用できるため、AGENTS.mdの改訂は不要と判断した。

## 再編集

検証済みの素材を使う場合は、`dialogue.json` と採用WAV、H3原本、実画面と公式原図を媒体の台帳で照合する。新しい出力ルートに元のディレクトリ構成でコピーし、案件ディレクトリから `python render.py <媒体ルート> short --render` と `python render.py <媒体ルート> full --render` を実行する。`python review_frames.py <媒体ルート>` と `python kit.py <媒体ルート>` で実フレーム・投稿セットを作る。

元の二人の絵と撮影原本から切り出し直すときは `python prepare_visuals.py <媒体ルート> <冬服の基準画>` を使う。H3に送ったJPEGは1152×768、品質86で、保存した原本とのSHA-256一致を確認した。外部APIの新規生成は `python narrate.py <媒体ルート> --generate` と `python shoot_pair.py <媒体ルート> talk` または `study` に分かれる。フルの2台詞目は保存済みの `why3` から `python edit_voice.py <媒体ルート>` で切り出した `why-final` を参照する。10.98秒の切り出し位置はこの収録テイクに対応する。

## 保存と確認

2026-11-25、案件・索引・総覧と構成図を個人フォークへ保存。制作コミット `98f82fe` が [Draft PR #27](https://github.com/benriworks/MiniMax-H3/pull/27) のブランチにあることを確認した。媒体台帳の50ファイルのサイズ・SHA-256、相対参照25件、既存の字幕・音声テスト12件を確認。次は2本のレビュー結果を版ごとに記録する。
