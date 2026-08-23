# MiniMaxH3 Studio MVP

## 目的

MiniMaxH3 Studioは、制作案件、ログ、中間成果物、費用、承認履歴を1か所で確認するためのローカルWebアプリです。チャットは企画と監督の窓口、Studioは実行状態と証跡を保持する制御盤として分離します。

このMVPはPowerDirectorのような汎用ノンリニア編集ソフトではありません。既存の`productions/`と`outputs/productions/`を読み込み、制作記録の閲覧、再実行計画、承認、監査exportを扱う土台です。TTS、画面収録、Remotion、H3、外部有料APIを実際に実行するworkerは後続段階です。

## MVPでできること

- 制作一覧と案件詳細をローカルブラウザで確認する。
- run、工程、イベント、費用、承認状態を分けて表示する。
- 動画、音声、画像、字幕、JSON、JSONL、一般テキストログなどの中間成果物を確認する。安全な構造化redactionを保証できない設定・markup形式はpathとmetadataだけを表示する。
- 動画、音声、画像のA/B比較と、対応するmedia同士の再生、停止、時刻合わせを行う。
- 変更対象から、再実行する工程と再利用候補を計画する。
- 新しいrunを既存runへ上書きせず作成する。
- existing台帳のtechnical、creative、public release statusを混同せず表示する。
- 有料工程を想定したrunの費用上限を承認または却下し、以前の判断を残す。
- manifest、記録、成果物hashを監査ZIPとしてexportする。
- SQLite索引を、ファイル上の制作台帳から更新する。
- provider secretをWindows DPAPIで暗号化して登録、状態確認、削除する。

MVPが行わないこと:

- 有料処理の自動実行
- TTS、画面収録、動画生成、合成、QC workerの起動
- ブラウザから任意ローカルpathを読むこと
- creativeまたは公開権利を自動承認すること

「run作成」は監査可能な実行計画を保存する操作です。現在のMVPでは、それだけで映像生成や課金API呼び出しは始まりません。
課金対象のrequested stageを含むrunには正の見積額が必須です。0以下または未指定の見積はfail closedで拒否し、runを残しません。

## セットアップと起動

前提:

- Windows PowerShellまたはPowerShell 7
- Python 3.10以降。既存の`.venv`があれば優先して使用
- Node.js 20.19以降の20系、または22.12以降とnpm。Node.js 21と22.0〜22.11はVite 8の対応範囲外

初回とfrontend更新後:

```powershell
.\setup-studio.ps1
```

通常起動:

```powershell
.\run-studio.ps1
```

`http://127.0.0.1:8765`だけで待ち受け、build済みの`studio/dist/`をPython backendが配信します。ポート変更とブラウザ自動起動の停止も可能です。

```powershell
.\run-studio.ps1 -Port 8876 -NoBrowser
```

frontend開発時:

```powershell
.\run-studio.ps1 -Dev
```

この場合はbackendを`127.0.0.1:8765`、Viteを`127.0.0.1:5173`で起動します。どちらもLANへ公開しません。`Ctrl+C`で終了します。

## API secretの登録

APIキーをチャットへ貼りません。PowerShellの非表示入力を使うCLIから登録します。現在登録できるprovider識別子は`minimax`、`elevenlabs`、`azure_speech`、`openai`です。

```powershell
python -m tools.studio.cli secret set minimax
python -m tools.studio.cli secret status minimax
python -m tools.studio.cli secret delete minimax
```

`python`がPATHにない場合は`py -3 -m tools.studio.cli ...`を使います。既存`.venv`を明示する場合は`.\.venv\Scripts\python.exe -m tools.studio.cli ...`でも同じです。

登録値は現在のWindowsユーザーに紐づくDPAPIで暗号化し、`outputs/studio/secrets/<provider>.dpapi`へ保存します。平文値は再表示せず、SQLite、ログ、監査ZIP、Gitへ含めません。MVPでsecretを登録しても外部APIは実行されません。

## 保存構造

```text
studio/                         React / Vite frontend source
tools/studio/                   Python backendと索引・監査処理
productions/<production-id>/    Git管理する既存の制作仕様と台帳
outputs/productions/<id>/       ignoredの画像・音声・動画・詳細QC
outputs/studio/
  studio.sqlite3                再構築可能なSQLite検索索引とStudio記録
  events/<scope>/<id>.jsonl     hash chain付きevent mirror
  secrets/<provider>.dpapi      Windowsユーザーに紐づく暗号化secret
  audits/<production>/<job>.zip 監査export
  audits/<production>/<job>.zip.sha256 監査ZIPの外部hash sidecar
```

`outputs/`はGit管理外です。大容量artifact、SQLite、secret、exportを誤ってcommitしません。既存制作の監査上の正本は`productions/`の台帳と、そこから参照される`outputs/productions/`のartifactです。Studioが作るrunと費用承認はimmutable row、eventはscope別hash chainとしてSQLiteへ追記し、JSONL mirrorと監査exportへ固定します。SQLiteだけを長期保全の唯一のcopyにせず、`events/`と必要な監査ZIPも保管してください。

## 記録モデル

```text
Production
  ├─ Artifact / Artifact version
  ├─ Event hash chain
  └─ Revision
       └─ Run
            ├─ Requested stages
            └─ Cost approval history
```

- 既存revisionとrunは上書きしません。修正は新しいrunとして残します。
- artifactは相対path、byte数、media type、生成元を常時記録します。SHA-256は既存manifestから得られる場合、または小容量sidecarを索引時に実測できる場合に記録し、大容量mediaでは`null`の場合があります。監査ZIPへ実際に格納したentryは別途すべて実測hashを持ちます。
- イベントと判断は追記し、過去の採否を書き換えません。
- eventは`previous_hash`と`event_hash`を持ち、起動時と追記時にJSONL mirrorの全chainを検査します。破損時はhealthとUIをdegraded表示にし、該当mirrorを監査ZIPから除外します。これはローカル改変の検出であり、第三者に対する電子署名ではありません。
- hash chainの途中改変や不正な追記は検出しますが、正しいevent境界で末尾だけを削る操作は、外部固定済みtailがなければ単独では検出できません。重要時点の監査ZIPと`.zip.sha256`を別媒体にも保管してください。
- SQLiteはUI検索とMVP操作用です。既存のtracked台帳を置き換えません。
- Studio外で既存台帳が更新された場合は「索引を更新」で再読込します。

MVPは変更種別から`requested_stages`と再利用工程を計画します。実行worker導入時にStage / Attemptを追加し、そのcache keyを工程種別、入力artifact hash、prompt hash、provider/model、設定、実装versionから作ります。例えば字幕だけを変更した場合、映像やナレーションを再利用し、合成とQCだけを新runで実行する設計です。

## ログ、成果物、監査

Studioでは次を別々に扱います。

| 種類 | 記録例 |
|---|---|
| event | 索引、revision/run、job、費用承認の時刻、状態、hash chain |
| artifact | path、bytes、MIME、origin、version、取得できた場合のSHA-256 |
| run cost | 見積、通貨、承認上限、承認／却下履歴 |
| status / approval | 台帳由来のtechnical・creative・public status、run費用上限の承認／却下と理由 |

provider task ID、redaction済みrequest/response、実費、ffprobeや音量等の自動QCは、各workerを接続した段階で同じevent/artifactモデルへ追加します。MVPは存在しないprovider実行ログを作ったようには表示しません。

監査exportは、SQLiteを1つのread transactionで固定した時点の記録をZIPへまとめる派生成果物です。event mirrorもそのsnapshotと一致する検証済みprefixをmemoryへ固定してから格納します。一般テキスト副生成物はZIP格納前に既知の秘密情報patternをredactし、変更対象をpackage manifestの`redacted_text_files`へ記録します。安全な構造化処理を保証できないYAML/YML、INI/CFG/CONF、TOML、CSV/TSV、XML、HTML/XHTML、SVGは`structured_text_requires_local_review`として除外します。未知形式と外部archiveも`unsupported_artifact_kind`として除外します。package manifest自身を除く格納entryごとの実bytes/SHA-256、scope別event chain末尾、検証できず除外したmirrorを記録し、ZIP閉鎖後に全entryを再検証します。ZIP全体のSHA-256は隣接sidecarへ保存します。DB snapshot後に元artifactが更新された場合、artifact metadataの時点とcopy時点は異なり得るため、ZIP内実体については`archive_entries`のbytes/hashを正本とします。既定の`include_media=false`では、record由来を含む動画、音声、画像をZIPへ含めません。監査ZIPが存在するだけで公開権利や人の通し試聴が確認済みになったとは扱いません。

## セキュリティ境界

- HTTPは`127.0.0.1`だけにbindします。
- 変更系POSTは起動ごとのsession tokenとloopback Originで保護し、tokenを永続ログへ保存しません。読取GETはloopback bindとHost検査を境界とします。
- 同じworkspaceへ2つのStudio serverを起動しません。serverはworkspace単位のprocess-lifetime lockを保持し、2台目を起動時に拒否してevent mirrorの多重writerを防ぎます。
- frontendへAPIキーを返すendpointはありません。
- `.env`拡張子、`.env.*`、credential/secret key file、DPAPI secretは索引対象外です。JSON/JSONLは構造化redactionし、一般テキストはAuthorization、Basic/Bearer、Cookie、API key、署名値など既知patternをbest-effortでredactします。
- artifact配信は登録済みかつ許可されたroot内のfileだけを対象にします。
- browser内でinline表示するのはraster image、audio、videoだけです。対応済み`.json`、`.jsonl`、`.log`、`.md`、`.txt`、`.srt`、`.ass`、`.vtt`は`attachment`とCSP sandboxを付け、redact済み内容だけを返します。不正JSON/JSONL、その他の設定・source code・markup・未知形式・外部archiveはMVPではHTTP 415で拒否します。Studio自身が生成・検証した監査ZIPだけはdownloadできます。
- 監査ZIPへ含める対応済みdocument、log、subtitleは秘密情報をredactし、変更対象と格納後hashをmanifestへ記録します。redactionは秘密がないことの証明ではないため、外部共有前に人がpackage manifestと内容を確認してください。
- request/response、Authorization、署名付きURL、Cookieは将来のprovider adapterで保存前にredactします。
- API契約後もキーをチャット、Git、SQLite、コマンドライン引数へ貼りません。
- 現在も課金対象工程のrunには正の見積額を必須とします。課金worker導入後は、対象素材、provider/model、最大額も先に固定し、明示承認なしではfail closedにします。

Studioは個人用loopbackツールです。LANからの攻撃面を作らないため、`0.0.0.0`やLANへ公開しないでください。

## チャットとの分担

1. ユーザーがチャットで制作や修正を依頼する。
2. CodexがStudioのローカルAPIまたはCLIを通して新しいrevision/runを作る。
3. 現在のStudioが索引・監査jobと、成果物、費用計画、ログを保持する。制作worker接続後は長時間工程も同じ台帳へ保持する。
4. ユーザーはStudioで候補や中間成果物を確認する。
5. Codexは完了、失敗、承認待ちなど節目だけを確認する。
6. MVPでは修正の影響工程と再利用候補を新runへ記録し、worker接続後はその範囲だけを実行する。

現MVPだけで削減できるのは索引・監査jobの監視です。制作worker接続後は、長時間生成もStudioが継続・記録し、チャットは節目だけを確認することで監視トークンを抑えます。Studioへ記録済みの状態はチャットを閉じてもローカルに残ります。

## 次段階

1. TTS provider adapter、字幕timing、発音辞書、provider別の実費・task記録
2. RemotionとFFmpegによるpreview／字幕入り／clean master
3. PlaywrightとWindows画面収録
4. ComfyUIとMiniMax APIのtask永続化、再開、二重課金防止
5. frame/timecode精度の連動比較、指定cutだけの再実行、cut/timecode単位コメントとcreative／rights human review UI
6. provider adapter接続時のrequest保存前redaction、外部送信素材の秘密情報検査、監査bundle署名

実装済み範囲を超える工程はRun計画内の未実行項目として表示し、`running`や`complete`とは記録しません。
