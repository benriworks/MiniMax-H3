# Claude Duetとdots比較

2026-10-23：独立production wrapperと実素材準備を実装。Aoede14区間は生成・検証済み。全14場面と人物切替・完成映像を確認し、75秒の動画とレビュー用ZIPを作成済み。S3の再生用・保存用MP4は完全GET/hash検証済み。聴感は環境制約により未確認。既存dots・Claude制作物は変更していない。

- 制作ID：`COMPARE_20261022_duet_dots`
- 見出し：【ChatGPT】Claude Duetとdots、何が違う？3つの比較ポイント
- 台本：440文字、14カット。暫定82秒から、実音声68.113秒＋余白をもとに75秒へ確定。
- 基本音声：Aoede。
- 新人物：森川遥（架空）。確認済みMiniMax実動画の思考・ひらめき・締めを重複なしで使用。
- 比較軸：知らせ方／作業の見え方と手元PC／利用条件と利用枠。

`script-draft.json` は調査用の構成案で、既存creator-storyの実行schemaではない。`narration-ja.txt`、`STORYBOARD_JA.md`、`evidence-table.json`、`RESEARCH_JA.md`、`sources.json`、`SOURCES_JA.md`、`image-quote-candidates.json`、YouTube見出し・説明文を保存した。

先にあった `character-prompt.json` と `frontend-reuse-proposal.json` は変更していない。frontend案の78秒・13カットは先行案で、この台本案は読み上げ密度を下げるため82秒・14カットを提案する。最終尺は音声計測で決める。

調査段階では既存コード・動画・原稿・音声を変更せず、API生成・TTS・YouTube投稿はしていない。人物動画、実音声、完成画面、最終試聴、利用者採用は制作時に確認する。

2026-10-22追記：公式3ページの実撮影を終え、C02発表記事、C07ブラウザー制限、C08コンピューター操作例の公開候補4PNGを`captures/`へ保存した。C08は引き継ぐ前のボタンと、公式例でボタンを押した後の操作欄の2候補。詳細は`captures/README_JA.md`、入力一覧は`captures/manifest.json`。画素一致とhash・既存proof読み込みの検証、子エージェントの実目視は合格。親の最終画像確認・完成画面での可読性・利用者採用は別の未完了状態。撮影前の引用候補リストは履歴として残し、実際の画像と引用語数はcapture manifestを優先する。


## 制作コマンド

- `python productions/COMPARE_20261022_duet_dots/produce.py generate`：明示した14区間だけ生成。完了cacheは追加要求0。
- `prepare`：来歴検証・音声実測・実素材propsを固定。
- `stills`：実素材の全カットと人物切替を確認。
- `render`：独立ProductComparisonの無音映像を生成。
- `assemble`：自作BGMとAoedeだけを合成し、完全decode・音量を検証。
- `review --review-evidence <json>`：実目視と実聴の証拠を検査。
- `package`：review済み候補を公開素材だけのZIPへ。

情報確認2026-10-23、公式画像撮影2026-10-22。原稿・調査用JSONの暫定状態は履歴として保持し、最新の制作状態はstate.jsonと出力verificationを参照。聴感・利用者採用・外部公開は技術検査と別管理。


聴感未確認を正直に示すレビュー配布は `package_review.py` が担当する。目視・完全decode・音量・元PCM一致を必須とし、`technical_and_visual_passed_listening_pending` を保持する。厳格な実聴完了用review/packageの条件を偽って満たさない。S3アップロードは既存AllowedRootsへの明示的コピーとhash照合後に行い、署名URLはディスクへ保存しない。期限・ArtifactId・hashだけを出力のs3-receipts.jsonに記録する。

## 人物を全画面にする改訂版

2026-10-23：冒頭・ひらめき・締めを縦画面全面の人物映像へ変更。顔を避けて大きな見出しと字幕を重ね、実動画区間の終端から要点表示へ切り替える。全75秒・音声・字幕・人物の重複しない3区間は維持。旧AACをstream copyし、音声packet hashの完全一致を検証済み。人物以外の11場面は確認PNGのhashも旧版と一致した。

独立driverは `revise_presenter.py`、状態は `presenter-revision-state.json`、完成出力は `outputs/productions/COMPARE_20261022_duet_dots/20261022T191503600528Z-immersive`。旧出力とstate.jsonは維持。追加TTS・MiniMax生成は0。新しい確認記録と公開ZIPを保存し、音声の聴感と利用者採用は未確認として扱う。

全画面改訂版もS3の再生用・保存用共有が完了し、HEADと全体GETのhash照合は合格。共有URLの期限は2026-10-24 04:25 JST台。署名URLをファイルへ保存せず、確認済みのID・期限・hashだけを出力内s3-receipts.jsonへ保存した。
