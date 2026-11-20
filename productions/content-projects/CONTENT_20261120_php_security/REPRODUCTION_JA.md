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

## 11月21日の配布元を実名で示す版

ショートv02、フルv03、記事v02、YouTube投稿素材v02をそれぞれ別に保存した。修正した章・新規台詞・読みと公式表記は `distribution-revision.json`、旧フルの「末尾が27から28」は `full-v02.json` から継承する。旧動画は作業入力と比較に保持する。

```powershell
$p = 'productions/content-projects/CONTENT_20261120_php_security'
python -B -X utf8 "$p/capture_providers.py"
python -B -X utf8 "$p/voice.py" --kind short --edition v02
python -B -X utf8 "$p/voice.py" --kind full --edition v03
python -B -X utf8 "$p/produce.py" render short --edition v02
python -B -X utf8 "$p/produce.py" render full --edition v03
python -B -X utf8 "$p/package_youtube.py"
python -B -X utf8 "$p/record_revision.py"
python -B -X utf8 "$p/package_article.py" --edition v02
```

- 上の例は保存済み入力から新しい出力先を組み立てる順番。撮影済みの引用を再利用する場合は `captures/providers-v01/` の原本、3抜粋、Red Hat配信のJPEGとmanifestを同じ位置に用意し、撮影工程を省く。写真は833×449の全体を保った。Red Hatの告知とRemiの記事の抜粋は実DOMの文字範囲を計測した。
- 画像生成の冬服参照は `motion/female-guide/022.jpg` と `motion/male-nod/012.jpg`。[最初の生成指示](youtube/thumbnail-prompts-v01.json)から得た2枚を参照に、[改訂の生成指示](youtube/thumbnail-prompts-v02.json)で配布元名を追加した。再編集には保存したPNG原本 `youtube-v02/source/{short,full}-art-v02.png` を使う。生成AIによる再生成結果は変わり得る。
- `package_youtube.py` はFFmpegのLanczosで2160×3840／3840×2160のJPEGを書き出し、章時刻・本文・MP4・引用元画像・寸法・容量・SHA-256を検査する。縦360px／横320pxの確認画像は `youtube-v02/review/`。既存の納品物を再照合するには `python -B -X utf8 "$p/package_youtube.py" --check` を使う。
- MP4は `release/v02/short/php-security-november-short-v02.mp4` と `release/v03/full/php-security-november-full-v03.mp4`。投稿素材は `release/youtube-v02/` にある個別の概要欄2件、JPEG2枚、推奨タイトルのテキスト1件。記事は `release/v02/article/php-security-article-v02-sources.zip`。Driveの非公開レシートは `_private/distribution-drive-v02.json`。検査要約は[改訂版台帳](youtube/verification-v02.json)。
- 音声認識は同じ `audio_check.py` でショートに `--edition v02`、フルに `--edition v03` を指定した。結果は `_private/asr-short-v02.json`・`_private/asr-full-v03.json`。編集評価と自動認識の範囲は[再開記録](RESUME_AND_KNOWHOW_JA.md)に記した。

## 11月20日の出力と受け渡し

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
