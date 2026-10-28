# dots入門 第5〜9回：公式引用入り最終5本

制作・公式情報の確認日：2026年10月22日。

第1〜4回に続く5本の30秒ショートを制作するフォルダーです。各回の主題に合わせた動く解説と、OpenAI公式資料の短い画面引用を組み合わせます。引用は公式資料の説明・UI例であり、利用者のアカウントで実際の作業を実証した録画ではありません。架空の依頼例は映像内で区別します。

この制作作業ではYouTubeへの公開を行っていません。映像の技術・AIによる画面確認と、利用者の最終試聴・採用判断は別の状態として記録します。

## 範囲と見出し

| 回 | 主題 | YouTube用見出し | MP4名 |
|---|---|---|---|
| 5 | 記憶と好み | 【ChatGPT】毎回の説明を減らす！dotsの「記憶」はどこまで？ | `dots-05-memory-official.mp4` |
| 6 | 会話と通話 | 【ChatGPT】声でも頼める！dotsは通話を切った後も仕事が続く | `dots-06-channels-official.mp4` |
| 7 | 定期実行 | 【ChatGPT】毎朝の確認を任せる！dotsの定期実行は「保存」が大事 | `dots-07-schedule-official.mp4` |
| 8 | 先回り調査 | 【ChatGPT】頼む前に気づく？dotsの「先回り調査」でできること | `dots-08-research-official.mp4` |
| 9 | 権限と停止 | 【ChatGPT】任せる前に知りたい！dotsの権限と「止め方」3つ | `dots-09-controls-official.mp4` |

各回の確定入力は `05`〜`09` 配下の `creator-story.json`、`youtube-title.txt`、`youtube-description.txt`、`SOURCES_JA.md` です。音声生成開始時に原稿全体のSHA-256を固定します。開始後に `build_stories.py` を再実行して入力を上書きしないでください。

## 公式出典と説明の境界

- [Tasks and memory](https://learn.chatgpt.com/docs/dots/tasks-and-memory)：第5回のメモリとdot独自ノート、第7回の保存済みスケジュール、第8回の先回り調査。第6回の連絡方法をまたぐ文脈も参照。
- [Message your dot](https://learn.chatgpt.com/docs/dots/channels)：第6回の通話、通話中の文字送信、Slack／Teams、スマホの利用方法。
- [Control your dot](https://learn.chatgpt.com/docs/dots/controls)：第7回の予約解除、第8回の調査権限、第9回のカスタムルールと停止操作。

引用場面ではOpenAI公式資料であることと出典ドメインを表示し、YouTube説明欄に該当URLを記載します。切り出した画像自体の内容は変えません。撮影原本・引用元URL・日時・切り出し座標・SHA-256は制作記録に保存します。原本とキャプチャ証跡、APIのリクエスト記録は公開用ZIPへ含めません。

短い動画で誤解しやすい点は、本文または説明欄に明記します。

- ChatGPTのメモリとdot独自ノートは別で、全会話の完全な記録ではありません。
- 通話の終了と作業の停止は別です。連絡方法ごとの画面に、他の会話の全履歴が複製されるわけではありません。
- 定期実行には保存済みスケジュールが必要です。時刻・時間帯・終了条件・通知先と、保存結果を確認します。
- 先回り調査自体は読める情報の調査であり、送信・アプリ変更・ブラウザー／PC操作を行いません。
- `Pause` は現在の主作業、`Activity` は委任した各作業、`Scheduled` は今後の定期実行を扱います。停止しても完了済み操作は取り消されません。

## 音声と映像仕様

- 音声：利用者選択の **Aoede**。モデルは `gemini-2.5-flash-preview-tts` に固定。
- 各シーンの実生成WAVを保存し、24 kHz・モノラルPCMの実サンプル数から尺を計測。原稿・発音置換・生成証跡と照合します。
- 全体30秒、1080×1920、24 fps、720フレーム。完成動画はH.264／AAC、音声48 kHz・ステレオです。
- BGM：既存のオリジナル `bright_groove_v1`。話している間は音量を下げます。
- 重要な文字は54 px以上を基準とし、スマホ表示と全フレームの安全領域を確認します。
- 字幕は実測した発話区間内へ文字量に応じて配置します。単語単位の強制アライメントではありません。

## 再現と安全な再開

リポジトリー直下のPowerShellで実行します。認証情報の値を表示・ファイル保存・コマンド引数への埋め込みはしません。Gemini認証を利用できる実行環境で音声生成だけが外部APIを使用します。

```powershell
.venv\Scripts\python.exe productions\SERIES_20261022_dots_finale\produce.py generate --episode all
.venv\Scripts\python.exe productions\SERIES_20261022_dots_finale\produce.py prepare --episode all
.venv\Scripts\python.exe productions\SERIES_20261022_dots_finale\produce.py render --episode all
```

`--episode` は `5`〜`9`、`05`〜`09`、`all` に対応します。通常の制作では各回を個別に進め、生成・レンダリングの終了を確認してから次の段階へ進めます。

完成動画から生成された各シーンの `preview-*.png` と全体の `contact-sheet.png` を実際に見て、字幕・引用・文字サイズ・重なり・余白を確認してから、具体的な確認内容を記録します。

```powershell
.venv\Scripts\python.exe productions\SERIES_20261022_dots_finale\produce.py review --episode 5 --note "実際に確認した項目と結果を記載"
.venv\Scripts\python.exe productions\SERIES_20261022_dots_finale\produce.py package --episode 5
```

音声生成は全回を通じて送信間隔を22秒以上確保します。`api-cadence.json` は送信時刻だけを保持し、認証情報は含みません。`.generation.lock` は同時生成を防ぎます。強制終了で残った場合、まず生成中のプロセスがないことを確認してください。

検証済みの各シーンは再利用します。リクエストの拒否・通信結果不明・生成証跡欠落は自動再送せず停止します。未確定状態のフォルダーや記録を削除して再送しないでください。完成済み音声を再利用した場合は追加APIリクエストを発行しません。`prepare` と `package` は既存出力を上書きしません。

当初の音声計画は各回7リクエスト、計35リクエストです。第9回の2番目のシーンでは結果不明の送信が1件発生し、音声を取得できていません。担当者が記録を調べ、元の不明状態を残したうえで、1件だけ明示的に置き換える復旧を扱います。この例外は生成先の `manual-recovery.json` に理由、不明件数、明示的な置換許可件数として記録し、自動再送には変更しません。

復旧後に全7シーンが検証できた場合、第9回の `voice-source.json` は `verified_requests: 7`、`unknown_previous_requests: 1`、`external_api_calls: 8` と記録します。他の4回が各7件なら全体は検証済み35件＋結果不明1件の計36件です。結果不明の呼び出しも課金された可能性があるため、実請求額は不明のままとします。`plan.json` の当初上限を後から書き換えて、35件だけ実行したことにはしません。

## 人物を加える映像だけの改訂

人間の案内役を追加する場合も、元の `creator-story.json` と音声生成計画は変更しません。別の `NN/visual-revisions/<識別子>/creator-story.json` に、冒頭と締めの `presenter` 装飾だけを加えます。公式引用場面には人物を重ねません。

```powershell
.venv\Scripts\python.exe productions\SERIES_20261022_dots_finale\produce.py revise-visuals --episode all --presenter outputs\characters\dots-guide-20261022\guide.png --presenter-proof outputs\characters\dots-guide-20261022\guide.json
```

この操作は新しい出力先を準備します。その後は同じ `render` → 実際の画面確認 → `review` → `package` の順です。透過PNGと画像の確認済み証跡を入力し、両方のhashをレンダリングの入力へ結び付けます。

完成済みの旧動画がある回は、既存の音声再利用経路を使用します。元と改訂の発話・字幕・カット尺・BGM・効果音が一致することを検査し、完成MP4では旧AAC音声を再圧縮せずコピーし、その音声ストリームのhashが同一であることも確認します。まだ完成動画のない回は、保存済みの検証済みAoede音声を使います。どちらも人物追加のために音声APIを呼びません。

改訂の `revision.json` には元原稿、新原稿、人物と証跡、旧state、旧成果物のhash、新出力先と `additional_tts_requests: 0` を保存します。旧MP4・ZIPは元の場所へ残します。現在の `state.json` は新出力を指し、納品完了後に `delivery.json` を新成果物へ更新します。改訂前の成果物は旧出力先と改訂記録から追跡できます。

## 成果物と検証

各 `NN/state.json` が生成先と動画出力先を示します。出力先は `outputs/productions/SHORT_20261022_dots_NN_editorial/` 配下です。納品済みの場合は `NN/delivery.json` がMP4・ZIPのサイズとSHA-256、確認状態を保持します。過去の第1〜9回、補足、Aoede第3回、新演出第4回の計12本は変更せず、生成開始時とパッケージ時にhashを照合します。

公開用ZIPは次の10ファイルに限定します。

1. 完成MP4
2. `cover.png`
3. `captions.srt`
4. `youtube-title.txt`
5. `youtube-description.txt`
6. `narration.txt`
7. `SOURCES_JA.md`
8. `quality-report.json`
9. `index.html`
10. `manifest.json`

パッケージはZIPのCRC、9コンテンツのサイズとSHA-256を読み戻して検証します。映像は形式・全フレーム数・尺・全体デコード、音声はラウドネスとピークを確認します。目安は−18〜−14 LUFS、最大真ピーク−1 dBFS以下です。通常の完成音量は約−16 LUFSです。

5本すべての現在の状態が `packaged` になった後、次の集約検査を実行します。

```powershell
.\.venv\Scripts\python.exe productions\SERIES_20261022_dots_finale\finalize.py
```

この処理は完成MP4・ZIPを独立して読み戻し、全メンバーのCRC・サイズ・SHA-256、現在のメディア形式、各場面と発話時間の対応、公式引用と人物画像の証跡、旧納品物の保全を照合します。第5〜8回は旧版とのAAC音声の一致を再検査し、保存済みの要求記録から35件の成功と1件の結果不明を別集計します。人物追加によるTTS要求・追加発話文字数はともに0です。全件の成功後だけ、本フォルダーの `delivery.json`、`verification/shorts-dots-finale-2026-10-22.json` と下記状態説明を更新します。生成API、アップロード、認証情報の読出しは行いません。

2026年10月22日の最終集約検証では、人物版の第5〜9回すべてが `packaged` です。各MP4・ZIPのサイズとSHA-256、ZIP全10メンバー、完成形式と720フレーム、35場面の確認証跡、公式引用5件、人物の冒頭・締め配置、旧12動画と第5〜8回の旧納品物を独立照合しました。第5〜8回のAAC音声は前版と同一です。成功した音声要求35件と結果不明1件を別集計し、人物追加によるTTSは0件です。最新成果物は本フォルダーの `delivery.json`、集約検証は `verification/shorts-dots-finale-2026-10-22.json` に記録しています。

`verified_candidate_awaiting_user_review` は技術・画面確認を終えた利用者確認用の状態です。`user_approved: false`、最終試聴 `pending`、`youtube_uploaded: false` は利用者の判断や公開が未確認であることを表します。

アプリ全体の構成と独立した図は、リポジトリー直下の `ARCHITECTURE.md` と `ARCHITECTURE_DIAGRAM.md` を参照してください。

## スマホ向けS3共有

人物入りの最新5本を、再生用（inline）とMP4保存用（attachment）の計10オブジェクトとしてS3へ共有しました。すべて送信後のHEAD・全体GET・サイズ・SHA-256一致で検証済みです。[共有記録](s3-receipts.json)にファイル名、サイズ、SHA-256、ArtifactId、ObjectKey、期限、料金内訳を保存しています。署名URLは会話でのみ返し、この制作フォルダーへ保存しません。最も早いリンク期限は2026年10月23日19:44:43 JST、オブジェクト保存は設定どおり7日です。

S3料金は2026年10月3日確認の単価に基づく概算です。今回の最新10オブジェクトは、各1回の利用者取得、送信後の追加検証、7日保存を合計し、無料転送枠を適用しない場合に約0.00638 USD。人物追加前の共有5件も含む作業全体は約0.00908 USDです。無料枠の残量と実請求は不明で、再生・再視聴・シークによる取得回数と転送量は増減します。音声・画像生成の費用はこのS3概算に含みません。
