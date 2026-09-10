# 画面解説テンプレート 実機検証記録

最新レビュー追補: v3の映像構図・Sayaka音声は利用者評価で作品品質不合格。v4は冒頭を全体表示に修正して通常納品まで再実行。原音／AAC診断と軽い帯域整理A/D比較は別の実験コピーとして作成し、聴感改善は未判定。[詳細・測定値・出力hash](productions/SHORT_20260906_claude_desktop_real_capture/AUDIO_REVIEW_JA.md)へ分離する。以下の技術QC passは作品品質を上書きしない。

日付: 2026-09-06 JST。最新判定は**実Claude素材による21秒・3場面の標準制作／納品E2Eを確認済み／聴感・スマートフォン可読性・公開品質は未受入**。

## 最新追補: 承認された架空カフェの実Claude教材

利用者の了承後、新規チャットへ架空カフェの告知文を3案求める依頼を1件送信した。これは下記の初回スモークと想定外送信とは別の制作である。回答取得後の実画面を無音30秒で1回収録し、0〜7／15〜22／23〜30秒を使って21秒に編集した。送信・回答生成をリアルタイムで収録したものではなく、生成速度の実演ではない。UI差し替え・生成UI、MiniMax推論、有料TTS API、外部投稿は使っていない。

- production: `production_18812c9ff18e4955858700ee7815f678`
- source Job: `job_ad5c7434598740bd9977d81f67ae7ef3`。元ウィンドウ846×572、出力1920×1080／24fps／30秒／無音、既知6成果物のみ。全decode・hash照合成功。
- 初回Run `run_9160859b84c84e1f9918f51ad4208941` はSayakaの選択に失敗。Windows PowerShell 5系では利用できず、既存PowerShell 7.6.5では同じSAPIスクリプトで実合成できた。通常経路を既存PowerShell 7優先とし、cache世代をv2へ更新。別音声への黙ったfallbackはせず、旧成果物と失敗履歴を保持した。
- recipe v2は通常4工程と納品に成功。v3は回答を見せるタイミングだけ変更し、音声4成果物を同一ID／hashで再利用、`cache_hit: true`を独立確認。追加収録なし。
- 最終Run: `run_7b1ed11efe9c429aa5639a9a23140bbe`、top Job: `job_84387158c4084168a32737be23d4ae91`、Delivery Job: `job_581b13a979334b9cb1b881f1588e629f`。
- 両MP4: 21.000秒／1080×1920／24fps／504frames／AAC 48kHz、独立全decode成功、技術QC pass。Sayakaの3発話と字幕開始は0／7／14秒。ZIP13項目のCRC・全payload hash・入力artifactのDBと実ファイルの来歴一致を確認。
- 修正後の関連試験55件成功（音声16、Detailed／Quick Create／画面解説39）。以前の全体681件と合算せず、修正後の全体再試験とも扱わない。
- 完成動画の2／10／16／20秒を目視し、場面2の回答表示と見出し・字幕の非重複を確認。固定拡大による周辺の切落とし、黒帯・余白、静止時間は残る。実聴によるSayakaのノイズ改善は確認していない。

ファイル・SHA-256・台本・版履歴は[制作記録](productions/SHORT_20260906_claude_desktop_real_capture/PRODUCTION_RECORD_JA.md)。`public_quality_verified: false`を維持する。以下は各時点の履歴であり、「未完了」はその検証時点を表す。

初回のローカルWeb実機検証を以下に保存し、同日のClaude専用経路・固定注目範囲の追加状況を末尾に分離して記録する。初回の素材・テスト件数を、新機能の実収録成功や最終回帰テスト総数へ読み替えない。

## 検証環境と範囲

- 既存Studioを専用ポート8766、専用DB `outputs/studio/verification/screen-explainer-20260906/studio.sqlite3` で起動。通常DBを置き換えていない。
- Studio画面から取得・台本編集・生成・納品を実行。案件専用の映像描画スクリプトは作っていない。
- 新規隔離ブラウザで `http://127.0.0.1:8766/` を3回収録。各5秒・1920×1080。場面2だけ下へ600pxスクロール。外部サイト、既存ログイン、任意Windowsアプリ、API課金、YouTube投稿は行っていない。
- 出力・ログはローカルに保存するが、重い成果物と検証DBはGit管理対象外。

## 同一素材での版更新

制作ID: `production_9d54615a4efe48e1adec7f7d9abc311a`

レシピID: `announcement_72575601208349d3bf96a08560721aa1`

| 項目 | v1 | v2 |
|---|---|---|
| 第3場面の見出し | 動画を確認 | 仕上がりを確認 |
| レシピ版ID | annv_0441d4a8f188478f8b0cfbcab8450bfc | annv_6d938221c0354874875edf3e06a56860 |
| Top Job | job_554af0963be849dbb29e58240be91a9c | job_7fe0478923d94a3580d9aad9049be78f |
| Run | run_8019b0ed3f4f4ba781de8986227d5d33 | run_69a9697c63d2407699292ec000ce5b12 |
| 技術QC | pass | pass |
| 音声 | 新規SAPI | 前版と同じ音声cache hit |

3場面の元artifact IDとtrim範囲は両版で一致。収録Jobは次の3個から増えていない。

- `job_56a0dda58f7045ea8154ece8983b25dc`
- `job_d3b9f3dd7a66433fb5bfafa70d9fe9c1`
- `job_9077a00d954546639782c6551f8198e3`

最終ビルドの画面を再読み込みし、同じv2 Job・artifactを復元することも確認。保存・状態確認操作から新規生成は行われない。

## 納品成果物

- v2字幕あり: `outputs/studio/runs/run_69a9697c63d2407699292ec000ce5b12/assembly/17C7E618127DF9C1F4E1292E344762C0C30E544C95B921F7B4C07D18DCA8F2EF/master-captioned.mp4`
- 同じディレクトリの `master-clean.mp4` は読み上げ字幕なし。テンプレートの大見出しは残る。
- v2字幕ありSHA-256: `1E52C04FD91999DC2FB9092F9F1E64B4D2FD215589AEB3511FB1306F52668F7F`、934672 bytes。
- 投稿情報txt: `outputs/studio/verification/screen-explainer-20260906/publication-info.txt`
- 納品Job: `job_5457ef66ac134b50b2f26dd8a76a7707`、成功。
- ZIP: `outputs/studio/deliveries/production_9d54615a4efe48e1adec7f7d9abc311a/32C619C3EE6350366EB533786F8CAD45D098DF053ADB1E0F04D5B7F4E4E3B24B/delivery-package.zip`
- ZIP SHA-256: `A9A7F7627D64DFD9ADA1A0528074FBA0112CE44562255DBAA4E69B1CBA0F1C61`、2402584 bytes。

ZIPの13ファイル: clean/captioned MP4、SRT、QCの3記録、サムネイル3枚、publication.json、production-snapshot.json、events.jsonl、delivery manifest。素材の元動画はRun側に保存。タグは投稿情報txtに含まれ、既存ZIPのpublication.jsonには含まれない。

## テスト・目視証拠

- `outputs/studio/verification/screen-explainer-20260906/python-tests.log`: Studio Pythonテスト635件（634成功、1skip）。不正preset型の追加テスト後は `tests.test_studio_screen_explainer` 4件を再実行し成功。
- `outputs/studio/verification/screen-explainer-20260906/frontend-tests-final.log`: 195件成功。TypeScript/Vite buildも成功。既存の500KB超chunk警告は残る。
- 同フォルダ `master-frame-1.png`、`master-v2-frame-11.png`: 実際の字幕合成後MP4のフレームを確認。見出しと字幕に切れ・重なりなし。
- `output/playwright/screen-explainer-assets.png`、`screen-explainer-mobile.png`: 取得素材と幅390pxの操作画面を確認。
- `output/playwright/screen-explainer-v2-complete.yml`、`screen-explainer-delivery.yml`: 実ブラウザの完了・納品表示。
- v1/v2のブラウザ再生結果: duration 15、ended true、1080×1920、media errorなし。消音再生であり、発音・声のクリーンさの確認ではない。

## 初回ローカルWeb検証から残る未達項目

1. **実際の教材としての画面素材**: 今回はStudio概要画面の収録で、台本に対応した3種類の操作を実演したものではない。
2. **細部の読みやすさ**: 横1920pxを960pxにcontainするため、小さな本文・ボタンはスマートフォンでは読みにくい。固定注目範囲は後続で実装したが、実教材を使った可読性の受入は未完了。収録時の表示調整・必要なら尺の見直しも必要。
3. **音声品質**: SAPIは試作。ElevenLabs等の試聴と一括経路への接続は未完了。技術QCを音質合格へ読み替えない。
4. **対象ソフトへの接続**: 初回検証はローカルWebのみ。後続でClaude Desktop専用の取得経路と15秒の実収録スモークを確認した。3場面教材の制作受入は未完了で、外部URLや任意ネイティブアプリは対象外のままである。

機能数ではなく、ユーザーが選ぶ対象ソフト1種類で素材取得の手間を削減し、公開候補3本と部分修正・再開を同じ経路で通すことを次の受入条件とする。

## 同日追補: Claude専用収録と固定注目範囲

### 実装した経路

- Studioから非収録inspectで公式MSIX版Claudeの可視・非最小化ウィンドウを確認し、匿名番号と寸法から選ぶ。任意HWND・パス・commandは受付対象にしない。OSのpackage family・application identity・package配下の実行パス・classまで確認し、非MSIX版は未対応として拒否する。
- 選択はStudio sessionへ束縛した60秒・単回token。利用者の明示確認後、15〜30秒の単一ウィンドウ・無音source Jobを1件だけ作る。既存FFmpegのWGC経路とプロセス封じ込めを再利用し、新しい録画エンジンは作らない。
- 開始前・収録中・終了前のidentity照合とWinEvent監視を行い、閉じる・最小化・非表示・移動・サイズ変更・対象変化時は停止する。短時間の変更後に復帰しても成功扱いにせず、全画面や別ウィンドウへ切り替えない。
- 送信前に受付IDをdraftへ保存し、応答不明は同じ制作・受付IDのcheckpoint APIで照合する。同一要求は同一Jobを返し、条件不一致は拒否する。結果不明の収録を自動再送しない。token、HWND、タイトル、実行パス、会話は受付記録へ保存しない。
- 構造・尺・無音・全decodeと6成果物のpath／bytes／hashを確認後、Job成功とartifactをDBの同じtransactionで登録する。異常・取消・登録失敗では部分素材を登録せず、既知ファイルだけを掃除する。サーバー再起動時の掃除も、そのDBに属する未完了requestだけに限定する。
- 共通の無音MP4を3場面の連続区間で共有し、任意の固定注目範囲を場面ごとに保存する。字幕・音声・最終合成は通常の版付きrecipeとDetailed Jobへ渡す。素材収録に架空のRunや完了済み音声工程を割り当てない。

### 確認できたことと保留したこと

| 範囲 | 状態 | 解釈 |
|---|---|---|
| Win32による対象列挙・エンジン利用可否 | 非収録inspectで公式MSIX候補を確認 | pixel・音声を取得していない。録画成功ではない |
| Claudeの実画面 | 初回白画面の後、表示復帰し標準source Jobで実収録成功 | 無音15秒の技術スモーク。3場面の教材完成ではない |
| 単一window guards・TTL・checkpoint・登録失敗時cleanup | 実装とmock／契約試験の対象 | 最終試験結果は別途追記。実window故障注入の完了とはしない |
| 共通素材と固定注目範囲 | 標準recipe／timelineへの結線を実装 | 実Claude素材で文字を読めるか、台本どおりかは未受入 |
| 元音声・AV同期 | 対象外 | 無音素材のみ。AV同期gateの合格を捏造しない |
| 有料API・音声購入・外部投稿 | 実行なし | SAPI試作の品質や公開可能性を合格へ読み替えない |

### 実Claude収録の技術スモーク

初回のCUA確認ではClaudeが白画面だったため一度保留した。その後、主担当の操作で表示が復帰した。白画面の原因は未特定であり、根本修正を行ったという記録ではない。履歴を非表示にし、個人の会話・アカウント名がない画面で標準source Jobを実行した。

- 制作ID: `production_3799109d7d66b767ad4091a3ad2aafea`
- 受付ID: `claude_capture_7ba077160fe2ea649c489ac5d6147ff9`
- source Job: `job_5f1b8cbfee50486ebe9b0570883077b5`
- 保存先: `outputs/studio/claude-captures/production_3799109d7d66b767ad4091a3ad2aafea/claude_capture_7ba077160fe2ea649c489ac5d6147ff9/`
- MP4: `claude-capture.mp4`、69523 bytes、SHA-256 `647B0F03545BC57801DCC02DBE1EB15E4C20B8A5D0F7C6BF697C3095364DA9F7`
- 実測: 15.000秒、360frames、1920×1080、24fps、H.264／yuv420p、音声streamなし、全decode成功。要求尺も15.000秒。Job経過約17.6秒。
- 6成果物（MP4、先頭／末尾PNG、capture-report、ffprobe、manifest）の検証と原子的なJob成功・artifact登録を確認した。reportは`capture_only`に相当する素材検証の記録で、`content_quality_verified: false`、`public_release_ready: false`を維持している。
- 主担当は`first-frame.png`と`last-frame.png`を目視し、入力欄に「画面収録テスト：この文章は送信しません。」が入る変化を確認した。このテスト文は未送信で、後に消去した。
- 文書更新時もreport・ffprobeを読み直し、MP4の実ファイルSHA-256が上記値と一致することを確認した。これは主担当の先頭／末尾の目視確認を独立した通し再生へ読み替えるものではない。

この素材は**公開用教材ではなく技術スモーク**。素材取得専用の成功Jobを確認したもので、Claudeを説明する完成動画・連続3区間と固定注目範囲・音声字幕・標準納品までの実素材受入はまだ行っていない。

### 準備操作で起きた想定外の送信

主担当がCUAでClaudeの「新規アーティファクト」をクリックしたところ、案内画面が開くだけではなく、Claude側で自動依頼文1件が送信され生成を開始した。想定外だったため停止操作を行い、停止ボタンが消えたことを確認した。生成成果物は得ていない。

これはStudio録画workerの自動操作・送信ではなく、対象アプリを準備する手動操作の副作用である。ただし「今回Claudeへの送信は一切なし」と記載することはできない。上記の収録テスト文はこの自動依頼文とは別で、送信していない。有料API利用・音声購入・外部投稿は行っていない。Claude側の依頼文送信による契約上の利用量をゼロと保証する記録ではない。

### 追補時点の試験記録

- Studio Python全体は681件中680成功・1skip。その後の清掃競合修正を含むClaude・Windows収録・JobManagerの回帰85件も成功。重複する試験なので件数は合算しない。
- API試験7件追加後のフロントエンド通常試験は216件すべて成功。`npm run build`も成功（従来からの500kB超bundle警告は残る）。
- 画面操作のmock試験2件を実行済み。mockの操作確認と、上記の実Claude収録を別の証拠として扱う。

### 次の教材制作・異常系の受入条件

1. 教材に必要な操作・結果を用意し、私的情報と送信操作の有無を確認して1回収録する。最小化・閉じる等の実window異常系は、別途許可された検証条件で確認する。
2. `claude-capture.mp4`、先頭・末尾PNG、capture-report、ffprobe、manifestの保存とhash、1920×1080・24fps・音声streamなし・要求尺以上かつ1frame未満の超過・全decodeを確認する。Jobの成功は素材取得にだけ付くことを確認する。
3. 3場面のartifact IDが同じで、trimが連続し、台本に必要な操作・結果を含むことを確認する。固定注目範囲の表示、字幕、発音と音質を実際の完成動画で確認する。
4. 台本・注目範囲だけを変更した版を再出力し、再収録が発生しないこと、応答不明時の再照合が重複収録を起こさないこと、標準納品・監査記録まで追えることを確認する。

上記と初回loopback検証は別の受入である。技術QC、テスト件数、候補列挙の成功だけで公開品質を合格にしない。

### 最終追補: runtime分離と取消の実機検証

初回成功フォルダでは、GPUドライバーが空の `NVIDIA Corporation/umdlogs` を追加していた。厳密cleanupの許可リストを広げず、全収録関連プロセスのcwdを `outputs/studio/runtime/claude-window-capture` へ分離した。補助ディレクトリはここに保持し、画面素材はrequestの絶対パスに出力する。初回の成功素材は履歴として変更していない。

- 修正後成功Job: `job_e51fbd88c9aa4e3ea694afb902c0a3f7`
- 成功request: `claude_capture_ddb9037667a3010dfca22050799d13bc`
- 同じproduction配下で15秒の再収録に成功。成果物ディレクトリ内は既知6ファイルのみ、partial 0、清掃ブロックなし。MP4 SHA256: `B8001C14BC6C9380A0D22A6F310A36893F496A972AA019FD505B40122F3B8059`。
- 取消Job: `job_abd7f7682b22488595ececdb994c176b`
- 取消request: `claude_capture_9f3ab2bcf0cee84499d43bf796a11bb1`
- 実際の収録開始後3秒で標準cancel APIを呼び、`interrupted`、成果物ディレクトリなし、partial 0、清掃ブロックなしを確認した。取消した途中動画は保持・登録していない。
- runtime分離に対するmock試験2件を追加し、Claude engine/service/HTTPの46件すべて成功。ドライバーがcwdに補助フォルダを作る成功・失敗の両方で、素材の厳密cleanupと補助フォルダの分離を確認した。

この追補ではClaudeへの質問送信は行っていない。先の想定外送信を取り消せたという意味ではない。収録試験後にClaudeを通常のウィンドウサイズへ戻した。教材用の正確な操作シナリオ、高品質音声、実Claude素材を使った最終動画の公開品質は引き続き未受入。
