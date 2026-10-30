# Claude Desktop 実画面解説 — 2026-09-06


> 2026-10-30整理：現在の判断と次の作業は [再開履歴兼ノウハウ](RESUME_AND_KNOWHOW_JA.md) を先に確認する。以下の制作時点の記録は履歴・詳細根拠として保持する。

**次のレビュー:** v4の冒頭全体構図は利用者了承。場面間の差とOpusの思考中表示について追加要望を受け、[依頼→処理中→結果のカット案](NEXT_STORYBOARD_JA.md)を保存した。素材不足を記録した段階で、新しいデモ送信や再収録は行っていない。

**最新追補:** 利用者からv3の過拡大とSayakaの周期的な異音について作品品質不合格の評価を受けた。v4で冒頭のウィンドウ全体を表示し、原音／軽い帯域整理の同音量比較を作成した。[構図修正・音声診断・比較ファイル](AUDIO_REVIEW_JA.md)を参照。以下のv3技術合格は公開品質合格ではない。

## 目的と範囲

「1種類の良質な画面解説テンプレート」を実際のClaude Desktopへ適用する試作。利用者の了承を受け、架空のカフェに関する依頼を**この制作で1件だけ**送信した。既存チャットとは別の新規チャットを使った。録画ドライバー自体はClaudeを操作・送信しない。

MiniMax/H3や画像生成によるUIの再現は使わない。公開・共有・外部検索・ファイル作成は依頼せず、有料TTS APIも使用しない。Claude側の既存契約の利用量は発生し得るため「全工程0円」とは表現しない。

## 実際に送信した依頼

```text
架空カフェ「こもれび珈琲」の告知文を3案ください。
条件：9月20日オープン／自家焙煎コーヒー／各案40文字以内。
短い告知文だけを、1〜3の番号付きで出してください。
実在の店舗ではありません。外部検索・ファイル作成・公開は不要です。
```

回答3案を実画面で確認。条件をすべて満たす模範解答としては扱わず、「最後は日付・文字数を確認する」構成にした。原文を画面上で書き換えたり、追加依頼で回答を取り直したりしていない。

## カット割り

| 完成尺 | 使用する実収録区間 | 意図 | ナレーション |
| --- | --- | --- | --- |
| 0〜7秒 | 0〜7秒 | 依頼に条件を添える | 条件を添えて、三案まとめて依頼。 |
| 7〜14秒 | 15〜22秒 | スクロールして回答を見る | 候補が出たら、使う表現を選びます。 |
| 14〜21秒 | 23〜30秒 | 回答の日付を拡大する | 最後は、日付と文字数を確認。 |

収録は送信・回答取得後であり、送信クリックや生成待ち時間をリアルタイムに記録した映像ではない。21秒は編集後の尺で、Claudeの処理速度を示す値ではない。固定拡大は画面全体ではなく説明する範囲だけを見せる。選択・コピー・貼り付けの完了を示すものではない。

## 素材と正規制作経路

- production: `production_18812c9ff18e4955858700ee7815f678`
- 収録受付: `claude_capture_52dede446256444c9e9ed7a5a0965628`
- 収録Job: `job_ad5c7434598740bd9977d81f67ae7ef3`
- 元動画artifact: `art_9e344d7299e339f7781c17d5832985dc`
- 元MP4 SHA-256: `B8B9E07B8987D824D8DD1BE0EE7DACDF9613C82406E2B53763841CA6AF01A362`
- 元動画: 30.000秒／1920×1080／24fps／720frames／音声streamなし。実ウィンドウは846×572。高解像度ネイティブ収録と誤認しない。
- 6成果物の登録・全decode・hash照合成功。個人の履歴とアカウント名は非表示にした。録画後にアプリの拡大表示を通常倍率へ戻した。

`produce.py`は既存Studioの同一workspace lockと既定DBを使用する。素材専用Jobから、版付き`screen_explainer_ja_v1` → Detailed Job → SAPI → Remotion → FFmpeg → 技術QC → 標準Deliveryへ接続する。汎用編集機能や別レンダラーは追加していない。別プロセスのStudioが起動していれば停止し、DBを共有実行しない。

制作記録は`outputs/studio/verification/claude-desktop-real-20260906/`、元動画は`outputs/studio/claude-captures/`に残す。生成物はGit対象外。台本・編集設定・ドライバーをこのフォルダーに保存する。

## 確認上の注意

- 先頭／末尾フレームと5秒間隔のsource contact sheetを目視した。サイドバーや他アプリが収録された形跡は確認されなかった。自動OCRによる秘匿保証ではない。
- `Microsoft Sayaka`指定の最初の制作Run `run_9160859b84c84e1f9918f51ad4208941` はナレーション工程で失敗した。失敗履歴は保持する。列挙でEnabledでも実合成成功とは限らない。
- Windows PowerShell 5系の実合成ホストでは日本語音声がHaruka Desktopだけで、SayakaとAyumiは`SelectVoice`で失敗した。既存PowerShell 7.6.5（64-bit）では、同じ`System.Speech`・同じスクリプト・同じ1文でSayakaの実WAV生成に成功した。ホスト選択を通常経路でも修正し、音声cache世代を`local-sapi-v2-pwsh-preferred`へ進めた。
- 修正後のrecipe v2／Run `run_e4b8648097004558afc6907d81527c0a` は全工程・技術QC・標準納品成功。Sayakaの3発話は0〜3.938秒／7〜11.153秒／14〜17.858秒。局所WAVは22,050Hz、mono PCM16。発話の重なりはない。
- v2の実レンダーフレームを目視し、場面2で回答へのスクロールが遅いことを確認。v3ではその素材区間だけを11〜18秒から15〜22秒へ修正した。元収録・ナレーション文・声・出力内の発話開始時刻は不変。v2納品は消去せず比較用に残す。
- v3の2／10／16／20秒の完成フレームを目視した。場面2では実回答が表示され、見出しと字幕の重なりはない。場面3は日付への固定拡大で文の右側が範囲外になる。黒帯と余白が大きく、画面の見せ方と終盤の静止時間は改善余地がある。スマートフォンでの可読性、発音・ノイズの聴感、公開品質は未受入。

## 最終試作 v3 の結果

2026-09-06 10:23 JSTに完了。収録から標準納品までの技術E2Eは成立したが、`public_quality_verified: false`を維持する。

- recipe revision: `3`、Run: `run_7b1ed11efe9c429aa5639a9a23140bbe`
- top Job: `job_84387158c4084168a32737be23d4ae91`
- Delivery Job: `job_581b13a979334b9cb1b881f1588e629f`
- 納品: 字幕あり／なしMP4、SRT、QC記録、サムネイル3枚、投稿metadata、制作snapshot、events、manifestを含む13項目のZIP。投稿用UTF-8テキストも別途保存。
- 両MP4: 21.000秒、1080×1920、24fps、504frames、AAC 48kHz。独立ffprobe・全音映像decode成功。技術QC `pass`。
- ZIPのCRC、全12payloadのbytes／SHA-256、6入力artifactのDB・子Job・物理ファイルとの一致、ZIP自身とsidecarのhash一致を独立確認した。
- v3音声Job `job_f0f3fdf086a04d41bb8e190c277ec4c6` は `cache_hit: true`。v2の4音声成果物を同一ID・パス・hashで再利用し、合成し直していない。収録も増えていない。
- ホスト選択・cacheを含む音声試験16件と、Detailed／Quick Create／画面解説の回帰39件、計55件成功。今回の修正後に全Pythonスイートを再実行したという意味ではない。

### ファイルと追跡先

以下はリポジトリrootからの相対パス。生成物はGit対象外のため、他端末へは納品ZIP等を別途移す。

```text
字幕あり:
outputs/studio/runs/run_7b1ed11efe9c429aa5639a9a23140bbe/assembly/F7673843ED173028E835EACF6B25A8F141628335DC6B3065A3FC2CC0C5760033/master-captioned.mp4
SHA256: 7AB16C14D6C6001F3359CB454C796A8B2D363773B59CE14508F473DB84266ADC

読み上げ字幕なし（テンプレート見出しは残る）:
outputs/studio/runs/run_7b1ed11efe9c429aa5639a9a23140bbe/assembly/F7673843ED173028E835EACF6B25A8F141628335DC6B3065A3FC2CC0C5760033/master-clean.mp4
SHA256: 40B0719A8C3A244DDFDBAAADBC1F79E15E3D8B80A0F87577019505FC053A79F6

納品ZIP:
outputs/studio/deliveries/production_18812c9ff18e4955858700ee7815f678/9620E16537AB3CDF1952DBFCE655AD9B6088418CA5E0E9C564FBE78BF2B9E4BC/delivery-package.zip
SHA256: 9B7B08EA803B241440EF1F5B3A0D5AF003F819E7B402685A1D68EBCA671FCA23

封印済みv3入力・結果・投稿文:
outputs/studio/verification/claude-desktop-real-20260906/renders/A688F922A7712EF8050029A750EE9F17B8649037CA2021912C679E360DB7F9FC/
```

同じフォルダーの`publication.txt`がタイトル・説明・タグのテキスト、`result.json`が最終Jobとartifactの索引。目視用画像は`outputs/studio/verification/claude-desktop-real-20260906/final-v3-contact-sheet.png`。外部投稿、追加のClaude依頼、Git commit／merge／pushは行っていない。

## PC操作の介入可能性に対する再確認

利用者から作業中にPCを操作した可能性の連絡を受け、保存済みの元30秒を1秒間隔・計30フレームで再確認した。予定の依頼文から回答へのスクロールが映り、別チャット・サイドバー・他アプリへの切替は確認されなかった。確認画像は同じ検証フォルダーの`interference-review-01.png`〜`03.png`。全フレームの無介入や短時間の変化が一切ないことを保証する検査ではない。

収録reportは30秒・720framesの完了と`window_guard_checks: 1446`を記録している。これはウィンドウ検査の回数であり、人の入力がなかったという証明ではない。元収録は10:02 JST、最終書出しは10:23 JSTに完了済み。今回の確認では新しい画面収録やClaude操作・追加送信は行わず、既存v3を維持した。

最終`result.json`がv3の成功Runを指すこと、字幕ありmasterと納品ZIPの現在のSHA-256が上記の保存値と一致することも再照合した。新規レンダーや成果物の上書きは行っていない。
