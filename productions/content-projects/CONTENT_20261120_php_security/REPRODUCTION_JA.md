# レビュー版の再現手順

縦のショートv01は51.250秒。横のフルv02は201.833秒。旧フルv01も別ファイルで保持する。ソースの基点は冬服と既存エンコーダーがそろった個人ブランチのコミット `667f739`。PHP案件のスクリプトはこの文書と同じディレクトリにある。

## 入力をそろえる

- 実行環境はWindows、Python 3.12.2、Pillow 12.3.0、FFmpeg 8.1.2。NumPy、BudouX、markdown-it-py、Playwright、Chromeを使用。字幕と図の書体はリポジトリのNoto Sans JP。SHA-256と容量は[検査台帳](verification-v01.json)の `inputs` に収録。
- 冬服4原本は素材ワークツリーの `outputs/characters/CHARACTERS_20261117_winter_duo/v01/review-v02/clips/`。ローカル曲は同ワークツリーの日本のClaude利用案件の `_private/happytime.mp3`。28本の生成済み原音と各受付はPHP案件の `outputs/content-projects/CONTENT_20261120_php_security/voice/v01/`。再編集にはこのディレクトリごとの保存が必要。
- レビュー時の公式実画面はPHP案件の `captures/original`、抜粋は `captures/quotes`、対象範囲は `captures/manifest.json`。公開日毎の告知集合は `captures/advisory-metadata.json`。後日表示が変わる可能性があるため、元と同じ映像を作るときは保存済みの撮影一式を利用する。
- H3原本と曲、生成済み音声、記事用撮影原本、MP4はGit外。必要な入力一式を作業先の同じ相対位置へ用意する。フルv01とv02で共通の音声には同じIDを使う。APIの初回生成は生成済み入力による再編集と結果が異なり得る。

## 実行

以下はPowerShellの例。作業ディレクトリはリポジトリのルート。成果物を保存した別ワークツリーのパスを `$winterLibrary` に設定する。

```powershell
$p = 'productions/content-projects/CONTENT_20261120_php_security'
$winterLibrary = '..\japan-ai-usage-20261117'
python -X utf8 "$p/capture.py"
python -X utf8 "$p/media_inputs.py" --library-root $winterLibrary
python -X utf8 "$p/voice.py" --edition v01
python -X utf8 "$p/voice.py" --edition v02 --kind full --line version-clarity
python -X utf8 "$p/produce.py" render short
python -X utf8 "$p/produce.py" render full
python -X utf8 "$p/produce.py" render full --edition v02
python -X utf8 "$p/record_project.py"
python -X utf8 "$p/package_article.py"
python -X utf8 "$p/verify.py"
```

既存のMP4や納品ZIPがある同一版への上書きは保護される。再照合だけなら `produce.py preview short`、`produce.py preview full --edition v02` と `verify.py` を実行する。音声が揃っていれば `voice.py` は受付とhashを検証して再利用する。新しい環境で `GEMINI_API_KEY` を使うのは生成が必要な場合。モデルは `gemini-2.5-flash-preview-tts`、女性Aoede／男性Charon。

ローカル音声認識は `audio_check.py short --model <local-model>` と `audio_check.py full --edition v02 --model <local-model>`。依存が別ディレクトリなら `--dependencies` で指定する。faster-whisper small、CPU int8、元音声を最終AACから16kHz monoへ変換して日本語認識した。

## 出力と受け渡し

`outputs/content-projects/CONTENT_20261120_php_security/` からの相対位置。

| 用途 | ファイル |
| --- | --- |
| ショート | `release/v01/short/php-security-november-short-v01.mp4` |
| 最新フル | `release/v02/full/php-security-november-full-v02.mp4` |
| 旧フル | `release/v01/full/php-security-november-full-v01.mp4` |
| 字幕と実フレーム | 各MP4と同階層のSRT・`timeline.json`・`decoded/`・`qc.json` |
| 記事 | `release/v01/article/php-security-article-v01.zip` の `index.html`、MD、MDX本文、公開候補4画像、出典、SHA-256 |
| 私的なDrive照合 | `_private/drive-receipts.json` |
| スタジオ | `workspace-state-full-v02.json` と `blog-handoff/v01/` |

縦・横の全編デコード、24fpsフレーム数、H.264/AAC、BT.709、fast start、音量、字幕原稿とSRTの一致を検査。入力、MP4、SRT、元WAVと記事ZIPのhashは[台帳](verification-v01.json)。収録済み素材を使った制作とこのPCでのQCが対象。別のPCでのバイト一致と人による最終試聴は未検証。
