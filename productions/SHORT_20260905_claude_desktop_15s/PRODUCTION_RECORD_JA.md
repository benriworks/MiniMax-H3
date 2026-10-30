# Claude Code デスクトップ紹介 — 15秒動画の制作記録


> 2026-10-30整理：現在の判断と次の作業は [再開履歴兼ノウハウ](RESUME_AND_KNOWHOW_JA.md) を先に確認する。以下の制作時点の記録は履歴・詳細根拠として保持する。

制作日: 2026-09-05

追記: 利用者の聴取で、全発話中にジリジリする音が報告された。下記のtechnical / visual PASSは聴感上の無ノイズを保証しない。原本を保持した[音声ノイズ低減の比較試験](AUDIO_DENOISE_TRIAL_JA.md)を追加し、軽め・強めの音声差替え版と同音量のA/B比較を作成した。聴感による採用判断は未完了。

## 意図と方式

前作Codex版の抽象的な「依頼 → 実装 → 確認」から、今回は「Codeタブ → フォルダ選択 → ボタンの色変更を依頼 → 差分・動作確認」という具体例へ寄せた。声を早口にせず、説明しきれない利用条件は注意書きと投稿説明に分ける。

中央のカットには内蔵imagegenで新規生成した実写風のデスク・PC画像を使用した。写真そのものはAI生成であり、写真のパン／ズームと画面内の文字・カーソル・操作カードはReact / Remotionで描く。これはMiniMaxで写真を動画化したものでも、Claude Desktopの実画面収録でもない。

使用した画像・正確な生成プロンプト・公式出典は[ASSET_PROVENANCE_JA.md](ASSET_PROVENANCE_JA.md)、カットの構成は[CUT_PLAN_JA.md](CUT_PLAN_JA.md)、手動投稿用の文面は[PUBLICATION_JA.txt](PUBLICATION_JA.txt)に記録する。

## 再生成

```powershell
node productions/SHORT_20260905_claude_desktop_15s/render.mjs --stills
node productions/SHORT_20260905_claude_desktop_15s/render.mjs --videos
.venv\Scripts\python.exe productions/SHORT_20260905_claude_desktop_15s/assemble.py --probe-voice
.venv\Scripts\python.exe productions/SHORT_20260905_claude_desktop_15s/assemble.py
```

先に案件の`outputs/.../assets/desktop-hero.png`を用意する。画像はGitへ入れないため、新しいチェックアウトには自動で付属しない。保存済みPNGをhash照合して持ち込むか、プロンプトから再生成して新しい素材として扱う。AI画像の同一生成は保証しない。

通常Studioがworkspaceを使用中なら先に終了する。合成時は既存のsingle-writer lockを取得する。出力は実行keyとtimestamp別のディレクトリへ保持する。案件のsource renderは同名の案件素材を更新するが、過去の実行manifestと取込済み動画を消さない。

これは通常Quick Createの新テンプレートではなく、制作専用スクリプトから既存workerへ接続する経路。`studio_run_id` / `studio_top_job_id`はnull、独立worker cache IDを明示する。Studioには正規に動画を取り込み、中間成果物と完了eventを残す。標準成功Jobを必要とする納品ZIPとは別経路である。

## 音声の調整

Microsoft Haruka Desktopのrate=0を使い、`Claude Code`を`クロードコード`へ読み替える。6文それぞれを本物のSAPIで生成し、raw音声を保持して末尾だけを調整する。

10ms窓、-45dBFSのRMS判定で長い句末静音を検出し、少なくとも250msの静音がある場合だけ120msの余韻を残す。先頭と発話を含むPCM接頭部は変更しない。これはASRによる単語境界検出ではなく、音量に基づく制作専用の前処理である。

開始予定: 0.450 / 1.590 / 5.450 / 6.690 / 10.250 / 12.320秒。実WAVのframe数から、6文の重複がなく、それぞれ対応する5秒カット内に収まることを検証する。raw / trimmed PCM、WAVのhash、検出時刻、最終timingsを監査用に保持する。

## 検証状態

状態: **technical / independent visual PASS**。人による最終試聴・公開は未実施。

| 項目 | 結果 |
| --- | --- |
| 字幕・音声あり | `outputs/productions/SHORT_20260905_claude_desktop_15s/ClaudeCode_desktop_15s_captioned.mp4`、1,318,397 bytes |
| 読み上げ字幕なし | `outputs/productions/SHORT_20260905_claude_desktop_15s/ClaudeCode_desktop_15s_clean.mp4`、1,268,152 bytes。大見出し・操作図・注意書きは残る |
| 尺・映像 | 15.000秒、1080×1920、24fps、360 frames、H.264 / yuv420p |
| 音声 | AAC、48kHz、stereo。元のSAPI音声は22.05kHz mono。変換による音質向上を保証しない |
| 音量・全decode | 両版pass。Integrated -17.8 LUFS / true peak -4.8 dBFS。映像・音声・コンテナの尺が15秒 |
| 黒画面 | 0.5秒以上の黒区間0 |
| 静止の参考警告 | 字幕版2.958〜5.042秒の約2.08秒、clean版約1.71秒。操作図を読み取るホールドを含む。クラッシュや欠損ではなくadvisoryであり、完全に動き続ける動画とは扱わない |
| 目視 | 素材代表3枚と完成動画の1秒ごと15枚。別担当が7.5 / 13.5 / 13.9 / 14.3秒を追加確認。生成写真、操作カード、字幕、CTAに文字切れ・干渉なし |
| ブラウザー | Chromeで15秒まで再生、ended=true、media errorなし、dropped frames=0、console error / warning=0。ミュート検査であり音声を聴取した証拠ではない |
| 制作専用音声処理 | 独立8項目pass。短い静音は維持、全無音・不正PCM・切除範囲の有意なピークを拒否、先頭PCMの保持と120ms余韻、4サンプルレート、重複・枠越え拒否を確認 |
| 処理時間 | 3素材render合計37.223秒、音声・timeline・合成・QC・取込102.969秒。内蔵画像生成、台本、音声preflight、実装・目視時間は含まない |
| Studio登録 | `production_ce49b3a8ef3c5dba86ec52ab6a767b7f`。正規素材・完成動画取込と中間成果物登録、独立完了eventあり |
| 投稿テキスト | tracked原本`PUBLICATION_JA.txt`とoutputs内`publication.txt`。YouTubeへの送信なし |

最終マスターSHA-256:

- captioned: `639567BAE52A1219B7664C347CA4026E3C4D543DC9234DEEDC5FFF9FFD42E2EF`
- clean: `A176B4643E21DD534662D62A5874F3BA0832E11B7F566A601F9C7B5FD59D3E1E`

コピー後の納品ファイルと実行manifestのhashを照合済み。素材と完成ファイルの監査用hashは[manifests/source-hashes.json](manifests/source-hashes.json)にも保持する。

実行ディレクトリ: `outputs/productions/SHORT_20260905_claude_desktop_15s/executions/0A7434AB8A1623781F69BAFAE604A22868C02F91844E705A9CB3287E727B8605/20260905T060424918871Z/`

同ディレクトリに`manifest.json`、request、events、narration／timeline／assembly／QC結果、両マスター、WAV、SRT、timingsを保持。独立worker cache IDは`run_0a7434ab8a1623781f69bafae604a228`。通常のStudio Run／top Jobが成功したという記録は作成していない。

音声の確定時刻は次のとおり。全6句で、削除したPCMサンプルの最大振幅が0（完全無音）、保持部分の元PCMとの一致、検出した発話末端から120ms以上の保持を確認した。

| 文 | 開始〜終了 |
| --- | --- |
| Claude Codeは、 | 0.450〜1.557秒 |
| アプリでも使える。 | 1.590〜2.927秒 |
| フォルダを選んで、 | 5.450〜6.657秒 |
| やりたいことを入力。 | 6.690〜8.196秒 |
| 変更を見て、確認。 | 10.250〜12.285秒 |
| まずは小さな修正から。 | 12.320〜14.136秒 |

カット間には操作を見せるための約2〜3秒の無音がある。句内の不必要な末尾静音を短縮したことと、全編を途切れずナレーションで埋めたことは異なる。読み上げの自然さ・発音の最終確認、公開判断は利用者に残す。

今回は制作ソースと独立したアーキテクチャ文書2本を更新した。アプリcoreの変更はなく、commit / merge / pushはこの制作依頼では実施していない。
