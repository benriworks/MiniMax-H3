# Architecture

## dots第5〜9回の仕上げ改訂（2026-10-23）

`productions/SERIES_20261023_dots_final_delivery/produce.py`は第5回の文脈保持と第7回の定期実行の使い方を独立IDで改訂する。既存原稿に一致するGemini Aoede発話だけを再利用し、変更分を既存TTSアダプターで生成して共通Shorts処理へ渡す。旧dotsのMiniMax人物動画・公式引用証跡を保ち、第6・8・9回の検証済み動画と合わせて独立フォルダーへ集約する。Driveへの共有は接続ツールによる個別操作。UI・API・DB・実schedule登録経路は追加しない。詳細は[専用アーキテクチャ](productions/SERIES_20261023_dots_final_delivery/ARCHITECTURE.md)。

## チャットで進める動画・記事制作の共通処理（2026-10-23）

`tools/studio/content_projects.py` は共通案件JSONから公開用画像を照合し、`outputs/content-projects/<id>/blog-handoff/<version>/` へ選択した画像、素材台帳、MDXのFigure記述を出力する。CLIは `validate` と `export-blog`。UI・HTTP API・DB migration・自動公開は追加していない。ユーザーは当面チャットを窓口にし、制作中の改善を共通処理へ反映する。

画像はworkspace内の相対パス、種類、hash、bytes、寸法、AI補助のプライバシー確認、alt、captionを検証する。実演は架空素材だけ、公式画像は出典と日付付きの記事用途確認を要求する。`private`／`_private`、外部パス、画像外形式、改変済み素材を拒否する。撮影proofは複製せず、ユーザー採用と公開承認を昇格させない。既存の受け渡し版は上書きしない。

最初の実案件は `productions/content-projects/CONTENT_20261023_claude_docs_reuse/`。7場面の動画は既存Aoede音声6件と既存MiniMax人物動画を再利用し、ブログ案内の締めだけを新規生成する専用ドライバーを用意した。元シリーズの台本・音声・納品ポインターは変更しない。記事は別ブログの独立ブランチで `draft: true` とする。

レビュー配信はGoogle Drive優先。コネクターによるアップロードとメタデータreadbackを今回確認したが、Studio内にDrive連携を実装したものではない。ローカル受領記録に版・Drive ID・サイズ・確認範囲を残し、モバイル実再生とユーザー最終試聴は別の状態とする。S3はDrive不使用時または会社への持ち込み用途で指定された場合に使う。

## 自分用の動画・ブログ共通制作層の設計（2026-10-23）

ユーザーは「まず自分用に磨く」「解説動画から詳細ブログへ誘導」「動画の決定事項と素材を記事にも利用」の方向を示した。現状はStudio／制作スクリプトの動画生成と、別リポジトリ `benriworks/blog` のMDX・画像掲載が別の経路として存在する。共通の画像受け渡しCLIを追加した。共通案件管理やブログ転送のAPI・DB・UIは未追加。

[VIDEO_TO_BLOG_WORKFLOW_JA.md](docs/video-production/VIDEO_TO_BLOG_WORKFLOW_JA.md) は、共通 `content_project_id` から企画、確認した事実と出典、人物、原素材を参照し、動画と記事へ分ける設計を定める。[content-project.example.json](docs/video-production/templates/content-project.example.json) は契約の記載例で、既存DB migrationではない。動画のproduction ID・既存素材パスは維持する。

素材は出自・版・hash・親素材と、動画／ブログ別のレビュー状態を持つ設計とする。公開用切り出しだけを記事用に受け渡し、原撮影や秘密情報入りproofは自動複製しない。字幕前の画像を共用し、媒体別の構図と読みやすさを確認する。公式画像は記事での利用条件・出典・説明文脈を再確認する。生成イメージと実画面の証拠を区別する。

ブログ側は `Figure`、alt、caption、寸法と `public/images/articles/<slug>/` を既存機能として使える。記事原稿と画像は別途draft PRで確認し、mainへのマージを公開操作として扱う。YouTubeショートの説明欄URLがクリックできない制約から、プロフィールのリンクを介した公開記事への経路を想定する。記事一覧の新しい入口・動画埋め込み・自動同期は未実装。

今回のローカル検討例は `outputs/content-projects/CONTENT_20261023_claude_docs_reuse/blog-handoff/v01/`。既存素材のコピー照合と用途の棚卸しであり、新しい記事・画面撮影・画像の掲載許可・ユーザー採用を完了したという意味ではない。

## 制作運用・ナレーション引き継ぎの文書層（2026-10-23）

`docs/video-production/README.md` を制作運用の入口とし、`VIDEO_PRODUCTION_HANDOFF_JA.md` に人物の初期ユーザー確認、MiniMaxでの動画化、シリーズの物語、公式引用と実演、保存、レビュー、納品、GitHub同期の責務を定める。音声の担当者向けには `NARRATION_HANDOFF_JA.md` を独立させ、現行Gemini TTSの生成・実尺測定・音声再利用・配置・最終試聴と手動編集を記す。

撮影担当者向けの `SCREEN_CAPTURE_AND_QUOTES_JA.md` は、Windowsの実画面取得・録画、元画面の倍率、公式製品画像と画面引用の区別、原本と公開用切り出し、人物の全面表示と根拠画面への切り替えを定める。文書の追加で新しい画面収録APIや権利判断の自動化を実装したわけではない。

`AGENTS.md` は人物確認と文書更新、GitHub保管範囲を作業ルールへ接続する。ひな形は制作記録・人物設定・レビュー依頼・素材索引を提供するが、アプリやCLIによる承認状態の自動強制機能を追加したものではない。技術検証、AI補助の画面確認、最終試聴、ユーザー採用、公開は別状態とする。

制作ルール・台本・プロンプト・改善理由・検証要約は軽量なGit管理対象。動画・音声・納品ZIPはローカルまたは共有ストレージで保持し、ID・相対パス・bytes・hashから参照する。`.gitignore` は新しい動画等の誤追加を防ぐ補助で、既存のupstreamデモを削除・追跡解除するものではない。署名付きURLや個人情報入り原本は公開文書へ入れない。ユーザーが示した方向性と未決条件は `DIRECTION_REVIEW_JA.md` に分けて記録する。

## 人物動画を全面に使う演出（2026-10-23）

利用者の指定により、`EditorialScene` の `editorial` かつ実MP4媒体を持つ場面は `FullscreenPresenterEditorial` で表示する。business配色のClaudeと既存dots男女の両方が対象。人物映像を1080×1920全体へcover表示し、わずかな寄りと下部の暗いグラデーションを加える。上半分の顔を空け、本文はy940、見出しはy1015、短い要点はy1210に置く。複数の要点は順に切り替え、既存の字幕と全フレームの安全域検査を維持する。公式引用や実演画像の場面は元の専用表示を保つ。

改訂は既存MP4の上書きではなく、新しい準備・描画・検証・共有記録として保存する。人物の元画像、MiniMax動画、場面尺、台詞、音声素材を再利用し、映像レイアウト変更のための生成API要求を増やさない。dotsの改訂では旧AACのpacket hash一致も検証する。静止画の見やすさ、完成MP4、聴感、利用者採用はそれぞれ区別する。

人物素材より場面が長い場合は、prepareが実probeから `mediaPlayFrames` と `mediaDurationInFrames` を設定する。1秒以上の実映像を必須とし、素材終了前から短いまとめ表示へ移る。末尾フレームの静止延長やループ、ナレーションの切断は行わない。editorial以外の既存動画場面は従来どおり全場面を覆う素材尺を要求する。

`CreatorShortComposition` の字幕は66pxを維持して33px上へ配置する。2行・上下padding・border・冒頭12pxの動きを含めて下端1490px以内へ収める。実際の2frame描画で検出した旧下端1508.6pxの失敗を修正するもので、独立比較compositionの字幕配置は変更しない。

dotsの全面表示改訂は `reprepare_fullframe.py` で旧state・納品物と音声を保持し、`preview_fullframe.mjs` で冒頭・締め・字幕の出現時を確認する。`finalize_fullframe_videos.py` は新しい出力を監査し、旧人物動画版とは別の納品記録へ確定する。Claudeは `renderer-revisions/` で前後の出力を結び、`finalize.py` が5本のZIP全メンバー、35音声区間、公式5場面と実演20場面、人物10場面、既存26動画の不変性を再照合する。共有担当は制作stateを書き換えず、S3専用receiptに署名URLを除いた検証結果を保存する。

共通変更の検証ではTypeScript検査と、素材の実尺境界・公式引用と実演の区別・供給済み音声の12テストを通過した。字幕は修正後の実2frame描画と2行字幕の出現時の描画に加え、完成動画の全frame安全域検査で確認する。部分描画の合格だけを完成動画の合格として扱わない。

## 60〜90秒の比較動画（2026-10-22）

`comparisonEntry.tsx` は独立した `ProductComparison` を登録する。専用props検査・公式引用・上下比較図・opening/insight/closing人物動画を使い、旧CreatorShortの60秒上限や既存動画の描画を変更しない。productionでは実MP4と区間尺を必須にし、素材未取得はfixtureとして明記する。字幕は62pxで2行を1490px以内に収め、固定フォント読み込み後に各frameの文字矩形を検査する。来歴proof・実音声の配分・最終納品検証は外側の制作処理の責任。詳細と独立した構成図は `productions/COMPARE_20261022_duet_dots/ARCHITECTURE.md` と `ARCHITECTURE_DIAGRAM.md` を参照。

比較の実制作は専用 `produce.py` と `studio/comparison-render.mjs` が担当する。Aoede14区間の元PCM68.113秒を無加工で75秒へ配置し、公式3画像の親確認・画素一致と新MiniMax人物の124frameを照合する。人物は思考／ひらめき／締めに重複なく区間分割し、残尺は自作まとめへ切り替える。音声付き元動画の音は使わず、最終mixはAoedeと自作音だけ。技術検証・目視・聴感・利用者採用を分離し、公開ZIPはprivate素材を除外して各memberのSHA-256を再照合する。

## Claude業務編と出典・実演の区別（2026-10-22）

`productions/SERIES_20261022_claude_work/produce.py` は5本・各30秒7場面の独立ドライバー。dots完結編の実装を専用のPythonモジュールへ読み込み、音声生成・検証済みキャッシュ・22秒間隔・不明送信で停止する処理を再利用する。元のdotsドライバー、原稿、音声世代を変更しない。Claude固有のID、公開用ファイル名、公式引用と実演の事前確認、納品メタデータだけを追加する。`preflight` は読取りのみで、公式資料1件以上、実演の入力前と出力後、確認済みMiniMax人物映像を要求する。音声を送信するのは明示的な `generate` のみであり、素材が欠けた状態から自動生成へ進まない。

共通 `source` 場面は従来のorigin未指定dots引用に加え、`scene.visual_style: business` を指定した新しい引用を扱う。`capture.origin: official` はHTTPSの `learn.chatgpt.com/docs/dots/`、`support.claude.com/en|ja/articles/`、`claude.com/resources/articles/` の限定パスだけを許可する。認証情報、任意ポート、queryは付けない。`demonstration` は `product`（Claude／Codex／ChatGPT）と `phase`（before／first-output／revision／after／export）で実際の撮影段階を表し、アカウント固有URLをcapture・proof・描画propsへ持ち込まない。公式説明の引用を、その機能の実操作成功として扱わない。

新しい撮影proofはoriginとタイムゾーン付き `captured_at` を照合する。実演は製品名・段階の一致に加え、`fictional_materials_only: true`、`personal_information_excluded: true`、目視確認済み状態を必須とする。公式は出典URL・タイトルを照合する。どちらも従来どおり画像と元画面のhash、PNG寸法、切出し座標と元画面内の包含を確認し、同梱画像は `capture-NN.png` とする。撮影原本とprivate文脈は公開ZIPへ含めない。旧origin未指定の許可URL・検査・props構造は維持する。

実演の切出しは `prepare_demonstrations.py` が明示した矩形計画だけを処理する。原本PNG・撮影日時JSONを保全し、画素が完全一致するcropを `demonstration/` へ保存する。拡大、ぼかし、画像補完、画面の再作図は行わない。見出し・箇条書き・目的文の前後比較は同一矩形を使い、実際の依頼と確認事実を `operations.json`、各画像・原本・metadataのhashをproofとmanifestへ記録する。担当エージェントの画像確認、親担当の確認、最終動画の可読性、利用者承認を分ける。別アプリで開いた書き出し結果は `external_viewer` と書き出しファイルhashを併記し、Claude画面と混同しない。

撮影原本の拡張子がPNGでも実体JPEGの場合は元bytesを維持し、デコード後の全画素が同一のPNGをprivateの `decoded-png/` へ別保存する。共通検査のPNG要件は緩めず、このPNGを `context`、元JPEGを `raw_capture` として双方のhashと変換方式をproofへ記録する。公開crop、撮影日時、個別目視結果を変更せず、旧proofも別履歴に保全する。

`verify_docx_exports.py` は指定された初回・修正版のDOCXを読取り専用で検査し、ZIP CRC、本文XML、650円・3万円・期間・時間・未定項目、見出しと太字・箇条書きの保持を確認する。XML検証だけではWordの見た目を確認済みと扱わない。実際のWord保護ビューで開いた画面は別のexport段階の撮影証拠として保存する。書き出しメニューの存在、ファイル取得、本文検査、外部アプリでの表示はそれぞれ別の実施事実として記録する。

businessレイアウトは `editorial`／`source` 場面だけで選択する。見出しは2行・各10全角相当まで、引用場面の中央を説明用の文言で覆わない。人物は元のPNGとオフィス用I2VAキー画像に結び付けたMiniMax動画を冒頭hook／締めclosingへ配置し、静止PNGのpresenterは併用しない。2026-10-23の改訂以降、人物動画は上記の全面表示を使う。dotsは既存配色を保ち、人物以外の引用・図解の構図を維持する。モデルや生成ツールの出所は制作証跡へ残し、動画内へツール名のクレジットを追加しない。

## dots既存男女の人物動画改訂（2026-10-22）

`productions/SERIES_20261022_dots_finale/character_video_revision.py` は音声生成コマンドを持たない独立改訂経路。元男性の確認済みフレームと2026年9月30日の女性キー画像から新規生成したMiniMax動画を受け取り、元原稿の冒頭と締めへ `media`／`mediaStart` だけを加える。公式引用・中盤・台詞・字幕・音声署名の一致と、元のカット尺を動画が覆えることを確認する。最新の静止人物版も含め、旧MP4・ZIP・state・deliveryのhashを保存し、旧出力先は上書きしない。

映像準備は最新の完成MP4を `reuse_audio` へ渡し、合成では旧AACを再圧縮せずコピーする。新しい確認と梱包後にだけ納品ポインターを更新する。改訂receiptは元原稿、新原稿、媒体proof、元人物画像、I2VAキー画像、旧納品物を結び付け、追加TTS要求・追加発話文字数はいずれも0と記録する。描画後の実画面確認、最終試聴、利用者承認、YouTube投稿は別状態で管理する。

人物素材の台帳は `productions/characters/motion-registry-20261022.json` に集約する。`productions/CHARACTERS_20261022_explainer_motion/register_completed.py` は完成した5素材のMP4、生成proof、元人物画像、I2VAキー画像、寸法、fps、フレーム数、利用開始フレームと目視状態をhashで結び、既存男女と業務用人物の台帳にも参照を追加する。人物素材の確認を利用者承認と同一視せず、ナレーターAoedeと無音の人物映像を区別する。改訂の準備後は素材proofを書き換えない。

`inspect_character_motion.py` は完成MP4から冒頭と締めの各3時点を抽出し、6枚の画像、一覧画像、元MP4のhashを `motion-evidence.json` へ保存する。実際に画像を確認した記録は別の `motion-visual-review.json` とする。`finalize_character_videos.py` は5本の全35場面と30動作サンプル、公式引用、原稿・字幕・見出し・概要・出典の不変性、旧AACとのpacket hash一致、公開ZIP全メンバー、保護対象12動画を照合する。旧静止人物版の監査を上書きせず、新しい `character-video-delivery.json` と `verification/shorts-dots-character-video-2026-10-23.json` に結果を確定する。

親担当の画面確認は独立した `root-review.json` に、AIによる確認と利用者承認・試聴を分けて保存する。S3共有は検証済みMP4だけを既存AllowedRoots内の一意なフォルダーへコピーし、hashを再確認してから再生用と添付用を別々にdry-runする。各送信の終了コード0と `Status=verified` を要求し、署名URLを除いた共有結果だけを別receiptへ残す。制作時点の監査や旧共有記録は保持し、署名URLは納品返信だけに返す。

## 人物案内役と音声を固定した映像改訂（2026-10-22）

完結編の `revise-visuals` は、音声生成時に固定した原稿を変更せず、各回の `visual-revisions/<識別子>/creator-story.json` へ人物の表示指定だけを追加する。冒頭と締めの `editorial` 場面に限り、`presenter` の `path`・`proof`・`role`（`hook`／`recap`）を受け付ける。公式の `source` 場面には重ねない。台詞・字幕・声・発音・尺・BGM・場面種別・効果音の項目数を含む音声署名の一致と、人物指定を除いた全原稿の一致を確認する。

人物は `outputs/characters/dots-guide-20261022/guide.png` の透過PNG。共通準備処理は、画像のhashに結び付いた `guide.json` の `visual_review_passed`・`generated_humanoid`・透過確認を必要とし、画像と証跡を準備入力へ含める。画像を `presenter-NN.png` としてローカルへ同梱し、描画側へは同梱名と役割だけを渡す。`EditorialScene` は人物を使う専用構図へ分岐し、見出しと字幕の可読性を維持する。画像生成の出所は制作証跡に保持するが、動画内へ生成ツール名のクレジットを足さない。

完成済みの第5〜8回は旧出力を上書きせず、既存 `reuse_audio` 経路でWAV・カット時刻・字幕・BGM・効果音の一致を確認して新しい映像を描く。合成時は旧MP4のAACを再圧縮せずコピーし、完成後に音声ストリームのSHA-256一致を必須とする。初回映像作成前の第9回は保存済みの検証済みAoede音声を使う。人物追加のためのTTS呼び出しは行わない。改訂記録は元と新しい原稿、人物と証跡、旧state、旧MP4／ZIP、新出力、音声の再利用方法と追加TTS 0件を結び付け、旧納品物を再検証する。準備後の `state.json` は新出力を指し、`delivery.json` は新しい確認・梱包が完了してから更新する。

音声計数では当初の各回7件・合計35件の計画を保持する。第9回の結果不明1件を調査して明示的に1件置換した場合、元の不明記録と `manual-recovery.json` を残し、検証済み7件・以前の不明1件・合計8件を区別する。全体は検証済み35件と不明1件の計36件となる。復旧記録は計数用であり、自動再送を許可する仕組みではない。プロバイダーでの不明要求の処理・課金は不明のまま扱う。

## dots完結編の連続制作（2026-10-22）

`productions/SERIES_20261022_dots_finale/produce.py`は第5〜9弾を各30秒で仕上げるファイルベースの共通ドライバー。各番号フォルダーの原稿・出典・見出し・説明欄を読み、独立した`SHORT_20261022_dots_NN_editorial`の音声世代と描画フォルダーへ保存する。従来9本・補足・Aoede第3弾・公式引用第4弾の計12動画はhashを保持し、納品時に再照合する。YouTubeへの投稿はこの経路では行わない。

生成前に選択した全原稿を検証し、各原稿をhashで固定する。Aoedeと`gemini-2.5-flash-preview-tts`を維持し、場面ごとの実WAVと送信証跡を保存。共有の送信時刻と排他ファイルで22秒以上の間隔を守る。再開時は検証済みWAVだけを再利用し、途中の送信や失敗記録を自動再送しない。原稿・APIキー・外部応答の扱いは既存音声ヘルパーに従い、キーを引数や記録へ出さない。

編集レイアウトにmemory・channels・calendar・research・permissions・contrast・statement・recapの8種を追加する。メモ、音声波形、カレンダー、情報の関連づけ、停止の区別などを別の配色と構図で描く。これらは解説図であり、製品の実際の操作画面を模した実証ではない。狭い列には7全角相当以内の文字制限を加え、最小54pxと全frame安全域検査を継続する。引用画像は828×390以内に縦横比を保って収め、引用場面で出典を表示する。

Playwrightで実際の公式ページから必要最小限の見出し・通話UI例・ルールの選択肢を撮影する。元画面、座標、日時、出典、寸法、hashを保存し、目視確認したPNGのみを各回へ同梱する。公開ZIPは動画・字幕・カバー・見出し・説明欄・出典・検証概要・再生ページ・ナレーション・manifestの10ファイルで、撮影原本やAPI記録は除く。全decode・音量・文字配置・最終画面・ZIP CRC/全メンバーhashを検証した後、既存S3upの再生用と添付用の共有経路を使う。署名URLは永続ファイルへ保存しない。

## 公式画面の引用と編集演出の追加（2026-10-22）

`SHORT_20261022_dots_04_editorial`は第3弾まで公開済みという利用者申告を受け、次の並行作業編を7場面で作り直す独立案件。人物素材を使わず、大きな導入、公式資料の画面引用、架空の並行作業、会話中の優先順位変更、公式の進行欄と成果物欄、次回予告へ切り替える。基本音声はAoede、BGMは既存112 BPM。公式ページの実機操作実証とは区別する。

共通CLIに`source`と`editorial`を追加する。`source`は固定の公式dotsドメイン、限定したPNG/JSON保存先、出典タイトル、撮影証跡を必要とする。Playwrightで公式ページを実際に開き、拡大して必要部分だけ撮影する。元画面・切出し座標・撮影日時・URL・PNG寸法・hashを照合し、検査済みの画像だけを`capture-NN.png`として同梱する。引用画面の英文やUIは書き換えず、出典表示と日本語の解説を別の表示層に置く。原画面は非公開の制作記録として保持し、公開ZIPには入れない。

`EditorialScene.tsx`は導入・並行作業・追加指示・結びの4つの閉じたレイアウトと、出典付き画像表示を担当する。引用画像はローカルファイルのみ読み、動画描画中に公式サイトへ接続しない。既存部品の文字54px・安全域・字幕・全frame検査を継続し、画像と新しいソースも描画前後のhashへ含める。証跡不足や元画面外の切出しは、既定の音声生成へ進む前に拒否する。前版の9本・補足編・公開済みAoede版のMP4を保持する。原稿・音声・描画・完成画像・最終試聴・利用者の採用・YouTube投稿は別の状態として記録する。

## dots第3話のAoede音声差替え（2026-10-22）

`productions/SHORT_20261022_dots_03_aoede`は、公開済みのクラウドPC補足編に続く「アプリ連携」を30秒で仕上げる独立改訂版。公式資料を再確認し、接続したGmail・Drive・GitHubと権限の説明を残す。今回の資料で確認できないエコシステムの数値は使わない。利用者が選んだAoedeを既存と同じGemini 2.5 Flash TTSで8場面別に生成し、発音辞書・要求・送信前記録・実WAV・usageとhashを保存する。短い場面に限り0.2〜40秒を許可し、従来の試聴は2〜40秒を維持する。連続要求は22秒以上離し、不明・拒否応答は自動再送しない。キーは実行環境から認証ヘッダーへだけ渡す。

共通`shorts_creator.prepare`の`narration_source`は既に生成された音声記録を読み込むだけで、APIへは送信しない。指定モデル・声、台本・発音辞書・原稿順、全ファイルhash、各発話の生成証跡と原稿、24kHz mono PCMのsample数、結合音声と元sampleの一致を検査してから描画へ進む。前版AACの再利用とは併用しない。従来のSAPI既定経路を維持する。

実WAVの長さから30秒内の場面とフレーズ字幕を再配置し、従来の文字54px以上・全frame安全域検査で映像を再描画する。明るい112 BPMのBGMと効果音を発話に合わせて減音し、完成AACの音量・peak・全decodeを検査する。旧9本と公開済み補足編はhashを照合して保持する。公開用MP4・カバー・字幕・見出し・説明欄・出典・検証結果を別日時フォルダーとZIPへ保存し、CRCと全member hashを確認する。利用者が報告した公開状況、試聴でのAoede選択、完成版の試聴・採用、YouTube投稿はそれぞれ別に記録する。

## Geminiナレーションの少量試聴（2026-10-22更新）

`productions/SHORT_20261021_dots_cloud_benefits/gemini_voice_trial.py`は既存のWindows SAPI版を保持し、冒頭3場面と同じ短い台本をGeminiで試す独立CLI。`prepare`は発音辞書を反映した台本、Kore/Aoedeの2候補、SAPI比較音声を日時・UUID別フォルダーに保存する。この段階ではGeminiへ生成を送らない。`generate --output`だけが`gemini-2.5-flash-preview-tts`の音声専用要求を各声につき1回送る。

キーは既存の`GEMINI_API_KEY`または`GOOGLE_API_KEY`から読み、固定HTTPS先のヘッダーにのみ使用する。キー、ヘッダー、プロバイダーの生エラー本文は記録しない。300文字・40秒・12MiBの試聴上限、24kHz mono PCM、完了応答、全decodeを検査する。送信前の記録とhash照合により、成否不明時の自動再送・改変原稿への旧音声の流用を防ぐ。接続キー無効は実音声生成の成功と区別する。声の自然さ・発音・採用、既存ショートへの組込みは実生成後の試聴で確認する。

2026年10月22日、Windowsのユーザー環境変数を読み直したキーで認証とKore/Aoedeの実生成が成功した。`package_voice_trial.py`は検証済み原稿・音声hashを読み、Windows Sayaka→Kore→Aoedeの順に、BGMなしで音量を調整した720×1280の比較MP4を作る。各行を個別に配置し、最小36pxで表示する。原音、正規化WAV、形式・全decode・音量・hashの検証と360px幅の確認画像を版別に保持する。比較の修正は保存済みWAVだけで行い、APIへ再送しない。S3再生用には指定されたMP4だけを既存S3up経路で検証して共有し、署名URLを制作ファイルへ保存しない。利用者の試聴・採用と45秒版への反映は別の段階とする。

## dotsクラウドPC補足編とBGM選択（2026-10-21）

`productions/SHORT_20261021_dots_cloud_benefits`は既存第2話を保持した45秒の補足編。公式資料の確認日と場面別出典を管理し、比較対象を手元のPCで動くAI作業に限定する。クラウド内の作業継続・状態保持・スマホからの依頼と確認を説明し、ローカル作業の接続条件、独立したログイン、自動移行しないタスクを説明欄にも残す。

共通CLIの台本は閉じた`music_preset`を選べる。省略時は既存と同じ`electro_pop_v1`（120 BPM）。`bright_groove_v1`は112 BPMの明るいプラック、柔らかいベース、シェーカーをローカルで合成する。切り替え効果音、発話時の減音と完成AACの音量検査を継続する。実効プリセットを音声再利用署名と`preparation.json`へ含め、曲の変更時に旧AACを再利用しない。既定曲と効果音のPCM互換、別曲の再現性、ステレオ、発話時減音を検査する。任意の音声パス・外部曲のダウンロード・音楽生成APIは追加しない。完成品、BGM単体、カバー、字幕、見出し、説明欄、出典、検証結果は日時別に保存する。

## 公式情報から機能別ショートを制作（2026-10-06）

`productions/SERIES_20261005_dots`はOpenAI公式資料を2026年10月5日に確認した9本の30秒シリーズ。場面別の`source_ids`と提供条件を台本に保持し、公開用の説明欄と出典資料へ渡す。発表日と段階提供を分け、提供予定の機能を公開済みとして扱わない。一次資料の内部スナップショットと、配布用の要約・リンクを分離する。

共通Shorts Creatorに`diagram`と`stat`を追加。`FeatureDiagram.tsx`が決められた10種のアイコン、接続線、機能ラベルと日付・数値をアニメーション表示する。JSONの種類・ラベル長をPythonとTypeScriptで検査し、描画時には従来の実DOM安全域検査を全フレームで行う。任意SVGやHTMLを台本から受け付けない。既存の6種類の場面・男女素材・最低54pxの文字・音声実測と音量基準を継続する。

シリーズの`produce.py`は準備、最大3本までの並行描画、実画像確認後のレビュー記録、公開用一式の梱包を担当する。共通rendererは新しい図部品もhashへ含め、描画前後の一致を検査する。完成品は1080×1920、24fps、30秒、720frames、H.264/AACを確認する。動画・カバー・字幕・タイトル・説明欄・出典・検証結果を相対リンクのギャラリーとZIPにまとめ、CRCと各ファイルのhashを読み戻して確認する。目視確認と利用者の採用、YouTubeへの公開状態は別に保存する。

## 注釈の除去と女性キャラクターの体格改訂（2026-09-30）

`CreatorShortComposition.tsx`は「図解イメージ」の画面表示を行わない。JSONの`illustration`は制作上の分類として保持し、作品の内容説明は制作記録へ残す。`CATCH_20260930_claude_acquired_female_silhouette_5s`は明るい服装版の始点画像を組込み画像生成で編集し、顔・髪型・配色を維持しながら肩・腕・胴回り・座り姿勢を調整する。新しい始点をローカルH3のI2VAへ渡し、旧素材を保持した別UUID・別保存先で生成する。原本の形式・全decode・体格と手の目視検査を通した生成記録だけを30秒版へ接続する。

共通CLIの`prepare`／`make --reuse-audio <前版の出力先>`は同一制作の検証済みMP4を使用する。台本・声・速度・発音・字幕・場面種別・効果音の項目数を照合し、場面時刻と再構成した音声素材のhashが一致する場合だけ前版のAACをstream copyする。完成品でAAC packetのSHA-256一致を検査するため、視覚だけの改訂で発話・音楽・音量が変わらない。アーキテクチャ図は独立した[ARCHITECTURE_DIAGRAM.md](ARCHITECTURE_DIAGRAM.md)に保持する。

## ショート動画の演出共通化（2026-09-30）

`studio/src/remotion/shortsMotion.ts`が安全域・文字サイズ・決定的なカメラ／見出しの動きを定義し、`ShortsMotionPrimitives.tsx`をStudio timelineと案件向け`CreatorShortComposition.tsx`で共有する。Studioの`shorts_creator_ja_v1`は既存の告知recipe保存・再実行経路へ接続し、10〜30秒、3場面、ハードカット、冒頭からの見出しを既存Detailed payloadへcompileする。旧presetのフェード・尺・保存内容は保持する。新しい任意CSS・URL・実行コードをAPIへ追加しない。

`shorts_creator_v1`見出しは3行／各行14文字相当までに制限する。Pythonの検証とNode描画workerの両方で同じpreset・文字量を許可する。rendererは共通部品と日本語フォントをtool identityへ含め、文字の動きやフォントの変更で古いcacheを再利用しない。`shorts_ja_phrase_v1`字幕は測定済みSRT発話区間を10文字相当以内のフレーズへ配分し、ASS上の96px、右180px・下470pxの余白と短い出入りを適用する。Yu Gothic UIのASS字形はCSSより小さく見えるため、共通図解のCSS字幕66pxとは指定値を分ける。これは語ごとの音声アラインメントではない。

StudioのPOSTが処理前のセッション拒否（403・固定のerror code/message）を返した場合に限り、同一originのトップページをGETしてHttpOnly cookieを再取得し、同じ要求を一度だけ再送する。応答消失・他の拒否・サーバーエラーは自動再送しない。サーバーのorigin検証とセッション検証は変更しない。

`tools/studio/shorts_creator.py`は複数の意味単位から制作する共通ローカルCLI。JSON台本を検証し、SAPI音声を一度生成して実WAV sample数から場面を配置する。音声の切捨て・無条件の早回しは行わず、尺超過を検出する。図解6種と既存人物映像を組み、オリジナルBGM・効果音・発話時の減音を合成する。`studio/creator-render.mjs`が同じ共通描画部品を使い、PNG中間frame／H.264 CRF14へ書き出す。描画中は重要な文字の実DOM領域と横方向のはみ出しも検査する。

音声はstereoを保って2-pass loudnormへ渡し、AAC化した完成品で-18〜-14 LUFS、true peak -1.0 dBFS以下を必須とする。形式、全decode、素材／ソースhash、30秒サンプルの全720frames、目視後のZIP読戻しを検査する。旧版比較・安全域表示を備えたローカル再生ページを併納する。日時別の出力先を使用し、既存の納品物を上書きしない。生成ツール名のテロップは付けない。仕様・使い方と参考資料は[SHORTS_CREATOR_JA.md](SHORTS_CREATOR_JA.md)。

## Claude Code紹介ショート（2026-09-26）

`productions/SHORT_20260926_claude_code_wow_30s`は既存の男女キャラクター映像を冒頭・結末に再利用し、中盤4場面をRemotionの独自図解として描画する30秒の案件専用経路。既存H3原本と生成記録のhashを照合し、新規生成の来歴と区別する。`story.json`を台本と字幕の共通入力とし、Windows SAPI速度1の音声を各5秒枠へ配置する。数式による独自BGM・切り替え音を合成し、発話区間の音楽を下げる。最低54pxの日本語フォントを同梱して720framesを描画し、映像を再圧縮せずAAC音声を合わせる。形式・全decode・音声peakと目視を確認し、公開操作から分離したローカル候補を保存する。

2026-09-29の利用者指定により、以後の完成動画とカバーには「MiniMaxで作成」などの生成ツール名を示すテロップを入れない。生成元の情報は制作記録に保持する。当該旧版では中盤に「図解イメージ」を残していたが、その後の利用者指定に従い、現行制作では表示しない。公式出典案内は引用場面に表示する。視覚だけの改訂では`prepare --reuse-audio <前版>`が台本・声・速度・発音・音楽設定と既存音声成果物のhashを照合する。新しい映像へ検証済み前版のAACをstream copyし、完成後に音声packetのSHA-256一致を確認する。前版を保持し、新しい日時フォルダーへ映像・カバー・検証記録・納品ZIPを保存する。

## 女性版の衣装差分（2026-09-21）

`CATCH_20260921_claude_acquired_female_bright_5s`は前回の女性始点画像をCodex組込み画像生成で編集し、アイボリーのパーカーと水色のインナーを新しいキー画像として保存する。既存女性版の素材・prompt・制作コードを上書きせず、別制作の`LoadImage → MiniMaxH3ImageToVideo.first_frame`へ接続する。ローカルComfyUIは最初から`--reserve-vram 1.5`で起動し、今回のUUID・graph・history・原本を独立して記録する。男性版の検証済み音声とチャイムは従来と同じ照合で再利用し、完成品を前回の服装と比較する。キャラクター台帳では衣装候補と利用者の採用を分離する。

## 参照画像から女性キャラクター版を作る経路（2026-09-20）

利用者が基本に選んだ男性キャラクターの冒頭画像を、Codex組込み画像生成で女性版へ編集し、保存した画像をローカルComfyUIの`LoadImage`から`MiniMaxH3ImageToVideo.first_frame`へ渡す。既存Q4 text/vision encoderとofficial INT8モデルでI2VAを行う案件専用経路で、Studioの標準T2VA UI／APIは変更しない。`productions/characters/programmer-duo`は共通の外観、採用済み男性版と試作女性版の区別、参照画像のpath／hashを記録する。

女性版`generate.py`は送信前にgraph・request UUIDを保存し、送信成功後は同一UUIDのhistoryだけを再照合する。graphと実historyの一致、キー画像・prompt・原本のhashと全decodeを記録し、原本を目視してから描画する。`produce.py prepare`は男性版の声・速度・発音・台詞・開始時刻と既存成果物hashを照合して、ナレーション4成果物とチャイムを再利用する。文字は同じ最低54pxのデザインを使用。始点画像の生成元とローカル動画の生成元を区別して記録する。

8GB VRAMのI2VA試行では、今回用ComfyUIを`--reserve-vram 1.5`で起動し、他の設定を保ってGPUメモリの余裕を増やす。旧IDを対象指定で中断し空queueを確認してから、自分が起動したComfyUIだけを再起動する。旧historyは保存し、新IDの生成記録から参照する。`generate.py --headroom`は試行別の保存先と記録を選び、OSや他アプリの設定を変更しない。

## ゲーム風の5秒キャッチ制作（2026-09-19）

`productions/CATCH_20260919_claude_acquired_5s`は、利用者が指定した「日本人プログラマーがClaudeを手に入れた」というゲーム風の独立した挿入候補を作る。既存30秒動画の経路は維持する。英語promptを固定T2VA graphへ入れ、ローカルMiniMax H3／official INT8 ConvRot + Q4／768×1376／20 stepsで生成し、graph・送信ID・history・原本をhashで結び付ける。原本の目視確認を通過した記録だけを案件rendererへ渡す。

案件用`produce.py prepare`は共通SAPI workerで1.7秒開始の短い発話を作り、実WAVが4.9秒以内に終わるか確認する。獲得音は外部素材を使わず、固定音階と減衰包絡からPCMで合成する。`Catch.tsx`は生成素材を無音表示し、最低54pxのゲーム風バッジと日本語メッセージを加える。`render.mjs`は入力hashを描画前後に照合して1080×1920／24fps／120frames／CRF 12へ出力する。`produce.py finish`は同じ映像packetへ、声と効果音または効果音のみをAAC 48kHzでmuxする。全decode、5秒、媒体形式、音声peak、両版の映像packet一致と360px幅の目視確認を行う。これは案件別制作で、StudioのUI・API・DB・標準workerの変更は含まない。

## 冒頭の画質を上げる制作経路（2026-09-18）

案件の`delivery_profile: hq_direct_v1`は、768px以上の幅・1344px以上の高さで生成したアイキャッチを要求する。画質比較では同じ夜景prompt・seed・20 steps・5秒を保ち、480×864から768×1376へ生成サイズを上げる。単なる最終MP4のサイズ変更とは区別し、原本のffprobe値と生成graphを検証記録に残す。冒頭の生成映像ラベルは下部の出典案内へ統合し、ビル群の中央を覆わない配置にする。

HQ経路のRemotion中間映像はCRF 12。案件用`produce.py`が既存Studioの字幕生成関数と80px presetを再利用し、字幕付き映像を中間映像から直接CRF 14／slowで1回だけ圧縮する。字幕なし版は映像をstream copyする。これにより、標準assemblyのclean→captionedという2回のCRF 18再圧縮を避ける。通常Studioのworkerと既存の標準経路は変更しない。

音声は`prepare --reuse-audio <前版>`で台本・速度・発音・音声4成果物と前版の検証記録／完成MP4を照合し、前版のAAC packetを両完成版へcopyする。完成後に音声streamのSHA-256一致を必須とし、30秒／720frames／1080×1920／24fps／全decode／ZIP読戻しの既存検査も実施する。映像再利用時の比較対象に`delivery_profile`を追加し、圧縮設定を取り違えないようにする。

## 明るい夜景への差し替え（2026-09-18）

Claudeモデル進化動画のアイキャッチを、案件用の英語promptからローカルMiniMax H3で作る経路を追加した。既存の固定API graphを使用し、official INT8 ConvRot + Q4 text encoder／Dynamic VRAM／20 steps／縦0.4MP／5秒で実行する。元の夕景と前版成果物は保持する。`prompts/NIGHT_CITY_H3.md`に照明・反射・構図・カメラ移動を記録し、生成graph・送信ID・完了history・原本MP4のhashを検証記録へ結び付ける。

rendererは従来の原本と生成記録の照合に加えて、記録に含まれる入力ファイルも照合する。`generation_context`で今回用の新規生成と過去素材の再利用を区別し、その区別を成果物へ引き継ぐ。冒頭だけ暗幕を弱め、文字の影と出典案内の半透明背景で読みやすさを補う。素材に`brightness(1.14) saturate(1.12)`を適用する。以降の図解・最低54px・既存ナレーションの再利用を維持する。音声だけの後続改訂でも、映像再利用記録から文字サイズと生成経緯を引き継ぐ。

## 読みやすさとMiniMaxアイキャッチ（2026-09-17）

Claudeモデル進化の案件用`Evolution.tsx`は、全描画文字の下限を54pxへ変更した（1080px幅、360px表示時18px相当）。長い補足を整理し、日付・グラフ軸・出典案内も同じ下限を守る。`Hero`の実行時検査とrendererの文字サイズ定義検査を行い、完成画像を360px幅で目視する。ナレーション字幕は従来の80px presetを維持する。

冒頭5秒だけ`OffthreadVideo`で既存MiniMax H3生成の都市映像を無音表示する。`story.json.eyecatch`に原本path／bytes／SHA-256、生成検証JSONのpath／hash、120frames／audio=falseを保存。rendererは原本と生成記録の対応・媒体形式・全decodeを確認し、固定名でpublicへ配置して描画する。既存生成物の再利用であり、新規H3推論、課金API、Claude Code実画面収録ではない。

`produce.py prepare --reuse-audio <前版>`はvoice／rate／pronunciations／全segmentsが一致する場合に、検証済みナレーション4成果物を参照する。前版の記録と実ファイルのhashを検査し、実WAVと字幕の時刻を保ったまま映像を作り直す。新しい視覚入力を古い映像へ誤適用しないよう、映像再利用時の比較対象へ`visual_style`と`eyecatch`も含める。成果物は新しい出力フォルダーに保存する。[制作記録](productions/SHORT_20260916_claude_code_evolution_30s/README.md)。

## Claudeモデル進化の30秒初稿（2026-09-16）

`productions/SHORT_20260916_claude_code_evolution_30s/`は、公式出典から作る年表・比較図解の案件用制作経路。`SOURCES_JA.md`が根拠、`story.json`が字幕・発音辞書・モデル名・発表日・比較値の正本。`produce.py prepare`は既存Windows SAPIで6発話を生成し、実WAVの尺が各5秒枠へ収まることを検査する。`render.mjs`と`Evolution.tsx`は同梱フォントを読み込み、30秒の独自図解を描画する。`produce.py finish`は既存assembly workerで字幕あり／なしMP4を合成し、形式・全decode・ZIP読戻しを検査する。

映像の数値はAnthropicの同一比較表から得たTerminal-Bench 4.0で、0〜100%の共通軸を使う。Claude Code実画面やモデルの独自実測ではない。入力と描画ソースをhashで拘束し、通常Studio DBには制作／Run／Jobを作らない。`outputs/studio/runs/run_*`は共通workerのファイル作業IDであり、DB登録の証拠ではない。音声ノイズ改善は保留、音声は仮、公開品質と採用は未確認。[制作記録](productions/SHORT_20260916_claude_code_evolution_30s/README.md)。

音声だけの修正では`produce.py prepare <検証済みの前版フォルダー>`により、無音映像を再利用できる。この案件の映像入力（models／duration_ms／fps）、描画コード・フォント・依存定義のhash、前版の無音MP4のhashと検証記録が一致する場合に限定する。前版のpreparation／render記録もhashで参照し、音声・字幕・合成物は別出力へ保存する。利用者指定により現在のSAPI rateは1、小数版`Fable 5.1`は「フェイブルごーてんいち」、整数版の5は「ファイブ」。表示字幕と発音辞書は分離する。

## Claude画面の準備操作（2026-09-12・現行schema 14）

静止画ライブラリに`ClaudeControlPanel`／`claudeControlApi`と`ClaudeControl`サービスを追加。対象は公式Claude MSIX版だけで、Windows Terminal／CLI／Codexは操作しない。利用者が1操作ごとに起動・タブ切替・未送信入力を選択し許可する。撮影手順に自動操作を保存したり、起動→入力→撮影を自動連続実行したりはしない。

`GET /api/claude-control`と`GET .../control_<id>`はStudio session必須。`POST .../inspect`と`POST .../actions`は既存session／origin検証配下。inspectは既存Claude selectorの60秒・session固定tokenを消費し、MSIX identity／PID／開始時刻／ウィンドウの一致を確認する。FlaUI.UIA3 5.0.0のRawViewから、Mode／モード群の上部タブと書込可能な入力欄だけを抽出する。日本語の「チャットと Cowork」「Code、作業中」を閉じた別名として扱う。全文・会話タイトル・runtime ID・native HWND・既存入力のhashはブラウザへ返さず、匿名入力欄名・文字数・相対位置・入力方式のみ表示。操作対象snapshotはvolatile tokenに60秒だけ紐づく。

`native/claude-control-helper`は.NET 8 Windowsコンソールプログラム。起動は固定AUMIDへの`IApplicationActivationManager`要求のみ、引数や任意実行ファイルを受け付けない。タブは`SelectionItemPattern.Select`または許可名の`InvokePattern`。入力は`ValuePattern.SetValue`を優先し、ValuePatternが存在しない場合だけ、LegacyIAccessibleのROLE_SYSTEM_TEXT・focusable・非readonly／非protected等を満たす欄で`SetValue`を選択する。既にValuePatternがreadonlyならLegacyへ迂回しない。送信ボタン・Enter・SendInput・クリップボード・座標fallbackはない。入力は4000 UTF-16 code units以内、LF以外の制御文字を拒否。既存内容があれば明示置換許可が必要。実行直前にidentityとUI snapshot（対象位置・値hash・入力方式・native hostを含む）を再照合し、対象から親ウィンドウまでの可視性・有効状態・所属も検査する。非表示のChat rendererが残る場合を想定し、祖先からのhidden判定を子へ引き継ぐ。ただしUIAには他の人間操作との原子的排他はないので、操作中はClaudeを触らない運用が必要。

UIA3の接続／呼出timeoutは各2秒、最大2500要素・24候補。候補0件の場合だけ300ms後に観察を1回追加し、操作失敗やprovider例外は再試行しない。入力方式は実行前に確定し、書込み後の例外・readback不一致でも別方式へ切り替えない。ヘルパー応答protocol 2をPython境界で検査し、旧buildには更新案内を出す。`packages.lock.json`と`NuGet.Config`で依存を固定し、setupはlocked restoreを要求する。FlaUI／Interopのライセンス通知はhelper出力に同梱する。

`ClaudeControlDiagnostics`はタブ・入力の候補数を別々に表示し、部分対応・候補なしを区別する。inspect応答の診断は固定engine／viewと有界カウンタのみをPythonでallowlistし、候補数との一致も検査する。画面上の直近診断は操作token失効後も説明用に残せるが、操作許可ではない。診断JSONは利用者のクリックで明示的に保存し、全文・window名・パス・ID・tokenを除いた別projectionを使う。自動保存／外部送信／DB追加はない。診断数は原因の断定や実機受入の証拠ではない。

ヘルパーへの文章・identityは有界UTF-8 stdinのみ。既存Windows Job Object封じ込めを再利用し、suspended生成→割当→再開後にstdinを書き、15秒でtimeout。stdout／stderrは上限付きで、provider例外は固定文に置換してからJob記録へ渡す。capturing／controlは同じsubmit lockとcapture laneを共有し、操作受付時と終了時に古い撮影選択を無効化する。操作完了後の撮影は再選択・別許可が必須。

schema 14は追記専用`claude_control_actions`を既存migration transactionに追加。ID・request digest・operation・job ID・文字数・時刻のみをqueue前に保存し、文章・token・UI snapshotは保存しない。UIもlocalStorageにはopaque受付IDだけを保持。応答喪失や再起動はGETによる結果確認だけを行い、自動再実行しない。同じID・同じrequestの再送は既存Jobを返す。失敗・cancel・interrupted・起動要求・照合できないInvoke結果は「実画面確認が必要」で、取り消し／未実行の保証ではない。

実機の受入状態：2026-09-12のComputer Use再観察では、初期はDocument止まりだったがChat画面の描画後にタブ・入力欄が取得できた。Codeへ戻った際に非表示Chat側のtreeが残る挙動も観察した。これはComputer Use経路での観察であり、今回のUIA3ヘルパーによる実入力／実タブ切替／起動の受入は未実施。ネイティブbuild／非操作self-test、合成native境界と実Studio HTTP／SQLite／ブラウザの結合試験は、実Claude操作の成功とは区別する。通常制作DB・実CLI・課金APIは今回の試験に使わない。詳細は[Claude画面操作ガイド](STUDIO_CLAUDE_CONTROL_JA.md)。

## 場面に紐づく撮影と比較・採用（2026-09-11）

静止画ライブラリを二段階拡張した。第一段階は保存済み場面からの撮影、第二段階は旧画像と新画像の比較・明示採用。CLIコマンド実行、Codexデスクトップ、動画生成、課金APIへの接続は増やさない。

`POST /api/still-plans/<plan>/steps/<step>/capture`は画像受付ID・expected revision・一時的な選択token・撮影許可だけを受け付ける。条件はサーバーの保存済み手順版から解決し、クライアントのURLやコマンド上書きは認めない。native撮影では既存のsession／期限／一回限りの選択を再利用する。UIの場面準備は条件欄を固定するが、対象選択・撮影許可は毎回必要。条件変更は手順の再編集・保存・再準備、または明示的な紐づけ解除で行う。

schema 13の追記専用`still_plan_captures`はstill ID・plan ID・plan revision・step IDを保持し、手順版と画像へ外部キーで接続する。Jobのqueue投入前に画像行・初期メモ行・紐づけを同一transactionで保存し、同じwriter lockで手順の最新版を照合する。不一致なら三つの行をrollbackし、Jobはsetup failureで終了して撮影workerを起動しない。Job自体の失敗記録は監査用に残る。DDLとschema versionも同じmigration transaction。撮影要求digestに場面の紐づけを含め、同じ受付IDの異なる場面への再使用を拒否する。

`StillImage.plan_capture`とローカル撮影manifestに紐づけを返すため、画面を閉じたり撮影応答を失ったりしてもstill IDから復元できる。撮影成功は画像公開の境界であり、手順更新の境界ではない。既存画像はparent IDとして保持し、自動採用しない。ブラウザへの受付保存は従来どおりopaque still IDのみ。

`GET /api/still-plans/<plan>/captures/<still>`は撮影時の固定手順版から旧画像ID・メモ版を解決し、新画像の現在メモ版と並べる。比較用snapshotは画像・寸法・hash・固定メモ・手順版を含むが、元URL・選択token・ローカルパスは含めない。旧メモは最新メモへ置換せず履歴から解決。手順が進んでいれば採用済み／再確認必要の理由を表示する。画像差分検出・OCR・公開品質判定は行わない。

`StillCaptureReview`は両PNGの読み込み後のみ確認チェックを許可し、原寸リンクとPC横並び／狭幅縦並びで比較する。画像読み込み失敗・未保存編集・他処理中は採用不可。`POST .../captures/<still>/adopt`は操作ID・expected revision・review digest・明示許可を受ける。DB writer lock内で確認snapshotを再照合し、PNGの完全decode／hashを検証して対象場面のimage参照だけを新しい`still_plan_versions`行へ保存する。同じ操作IDの再送は既存結果を返し、別内容への再使用や競合は409。元PNG・旧手順版は変更しない。

採用応答喪失時は自動POSTせず、画面内の同じ操作IDでの明示再確認またはGETでの採用状況確認を提供。採用requestと許可はブラウザを閉じると失われるが、画像の紐づけと採用済みの手順版はDBに残り、再度画像を選んでGET確認できる。採用成功後は保存済み手順をUIへ反映する。古い手順の候補は強制採用せず、最新手順を読んで既存の手動割り当てを使う。

回帰は`tests/test_studio_still_plans.py`、`tests/test_studio_terminal_still.py`、`studio/tests/still-guided-live.test.mjs`。後者は実Studio／SQLite／ChromiumでローカルHTMLを撮影し、撮影応答喪失・再読み込み・旧新比較・採用応答喪失と同一ID再確認・旧原本保持・手順競合・390px UIを検証する。ユーザーの通常DBや実CLI画面は使用しない。操作説明は[静止画ライブラリ](STUDIO_STILL_LIBRARY_JA.md)。

## 記事素材パック・確認内容に固定した一括書き出し（2026-09-10）

`StillPlans.preview`は手順版と各場面に割り当てた画像のメモ版を照合し、公開物に含める見出し・説明・素材メモ・hashだけのsnapshotを作る。画像が未割り当て／未完成／メモ版変更の場合はblockerを返す。sourceのURL・セレクター・token・元ファイルパス・過去のメモをsnapshotへ転記しない。ユーザー入力と画像内の情報は自動匿名化されない。

`StillPackPreview`は全場面をサムネイルと説明付きで表示し、明示的な確認後だけ書き出せる。`POST /api/still-plans/<id>/export`はexpected revision・review digest・confirm privacy reviewだけを受け取り、現在のsnapshotが確認済みのものと一致しないと409で拒否。全画像を既存StillLibraryで完全decode／SHA-256照合してから、`images/01.png`等の固定名・`ARTICLE.md`・`manifest.json`・`README.md`を返す。1〜12場面・PNG合計128MiB以内。途中のZIPは配信しない。アーカイブ内のパスはユーザー文言から生成しない。

記事説明はHTMLエスケープ済みpre blockと固定リンクで構成し、任意のHTML／外部画像リンクを生成しない。ZIPの時刻は固定し、同じsnapshotから同一バイト列を再生成できる。manifestには手順ID／版／review digest・場面ID・画像ID／版／hash／寸法を含め、持ち出したファイルを追跡できる。これは記事本文の自動執筆・公開・撮影の自動実行ではない。export専用のDB tableや有料APIは追加しない。

手順一覧・詳細・previewはGETにも明示的なStudio session確認を適用する。POSTは従来のtoken／origin検証に従う。実UI＋実HTTP＋SQLite＋登録PNGで、未割り当て拒否・画像割り当て・保存応答喪失からのGET復旧・ZIPダウンロード・確認後のメモ変更拒否を検証。通常の制作DB・ユーザーのデスクトップは使用しない。

## 撮影手順ライブラリ（2026-09-10）

`StillPlans`を`StillLibrary.plans`として追加。schema 12の`still_plan_versions`はplan ID・版・一意なoperation ID・要求digest・JSON payloadの追記専用テーブル。DDLを既存migration transactionに含め、schema更新失敗時は一緒にrollbackする。保存はexpected revisionを照合し、同一操作の再送は重複版を作らない。更新／削除をDB triggerで拒否する。

1〜12場面の見出し・説明・撮影条件と、任意の完成画像ID／メモ版を保存。native sourceはkindのみ保存でき、token・HWND・コマンド・許可の永続化は禁止。Web撮影条件は既存validatorを通す。画像割り当ては同じDB write transactionで成功状態と版を照合する。手順の複製は新ID・新step IDとし、画像割り当てを外す。

`StillPlanPanel`は手動保存・並べ替え・複製・選択画像の割り当て・既存撮影フォームへの条件読み込みを担当。読み込み時に許可とnative selectorをリセットし、撮影は自動開始しない。未保存変更は閉じる／切替／ブラウザ離脱で警告する。通信応答が不明ならopaqueなplan IDのみをlocalStorageに残してGETで確認し、自動再POSTしない。保存手順一覧は最新200件。公開APIは既存Studio認証配下の`/api/still-plans`と`/api/still-plans/<id>`。

実UI＋実HTTP／SQLiteの隔離試験で保存・並べ替え・準備時に撮影されないこと・reload・複製・390px表示を確認。既存撮影と同様、通常Studio DBは試験対象にしない。

## Windows Terminal静止画アダプター（2026-09-10）

`terminal_capture.py`の`TerminalStillController`を静止画ライブラリの`source.kind=terminal`として接続。Claude Code CLIの画面素材用だが、CLIの起動・コマンド送信・実行状態の判定はしない。実際の対象は利用者が選択したWindows Terminalウィンドウ全体。Microsoft Store安定版のpackage family／full name／AUMID／パッケージ内実行ファイル位置／ウィンドウclassを確認し、Preview・unpackaged・従来console hostは対象外とする。

`_Win32`の実行ファイル・class・package照合だけを差し替え可能にした。Claude側の既定ポリシーは変更しない。Terminalは別Controllerのtoken／claim registryを持ち、Claudeのtokenを流用できない。WGC原寸1フレーム・WinEvent guard・PNG検証・共有capture lane・admission lock・画像DB・メモ版履歴・ZIPを再利用する。Terminal adapterの動画claimと動画captureは拒否する。新しいDB schemaや画像エンジンは追加しない。

`POST /api/stills/terminal/inspect`は既存HTTP認証の内側で空bodyのみ受付。画像・ウィンドウタイトル・コマンドラインを読まず匿名候補を返す。`ClaudeStillSelector`をkind別に再利用し、切替時に再mountして遅れて届く別撮影元の応答を無効化。端末のtokenも最大60秒・明示選択・1回限り。撮影報告には`cli_content_verified=false`、`command_execution_performed=false`を記録する。タブ切替や画面内容の変化はウィンドウ同一性guardでは判定できないため、撮影中は操作しないことを案内する。

検証はPythonのnative境界試験、API正規化試験、両撮影元のmock UI試験に加え、隔離Studioの実HTTP／SQLite／Jobと合成PNGの結合で行う。実機でWindows Terminal候補の列挙は確認済み。実際のCLI画面のPNG取得は未検証であり、合成画像を実画面撮影成功とは扱わない。通常のStudio DB・ユーザーのTerminal内容は変更しない。

## Claude直接静止画撮影（2026-09-10）

静止画ライブラリの撮影元に`claude`を追加。`ClaudeStillSelector.tsx`は既存のsession付きClaude inspect APIを呼び、匿名候補を利用者が明示選択する。inspectだけでは画像を取得しない。選択は最大60秒・1回限りで、閉じる／期限切れ／送信後にはUIから破棄する。撮り直しも再inspect・再選択が必要。

`StillLibrary`と既存`ClaudeCaptureService`は同じController・native capture admission lockを共有する。sourceのraw tokenはvolatileな`ClaudeStillClaim`へ変換し、SQLite／Job payload／manifest／localStorageに保存しない。durable sourceには選択digestとsession binding digestだけを含め、一覧には`{kind: claude}`だけを返す。受付IDの照合と元画像の`parent_id`は従来通り。capture laneの実行中・終了処理中Jobがあれば受付を拒否する。

`ClaudeCaptureController.capture_still`は動画claimと型・レジストリを分離する。既存15〜30秒動画契約は変更せず、専用FFmpegコマンドの`gfxcapture=hwnd=...`から`-frames:v 1 -c:v png`で取得する。scale／pad／crop／音声／動画中間ファイル／全画面fallbackはない。元のMSIX identity確認・WinEvent guard・プロセス封じ込めを再利用し、最大20秒でtimeout。PNG生成後の完全decodeまでguardを維持し、対象が動く／閉じる／最小化・サイズ変更された場合は新しく作った失敗PNGだけを除去し、画像を配信しない。

共通`still_media.py`はDB非依存のPNG decode・上限・SHA-256・リンク拒否を担い、native workerとライブラリ配信の双方が利用する。完成画像は既存のJob成功境界を通って名前・メモ・履歴・ZIPへ接続する。取得後にJobが中断／DB保存に失敗した場合の非公開途中ファイルの保持方針は従来と同じ。自動公開・秘密情報の自動匿名化は行わない。

実機でStudio UI→対象確認→許可→撮影→PNG表示が成功。OSのclient座標2560×1392に対し、実PNGは3840×2088、693400 bytes、エンジン実行から画像検証まで約0.57秒（1回の観測値）。Code画面全体を目視確認したが公開用素材としての機密情報確認は別工程。通常Studio DBは触らず、隔離試験workspaceのみを使用した。CLI／Codex／VM対応は未実装。

## 制作から独立した静止画ライブラリ（2026-09-10）

Studioヘッダーの「静止画ライブラリ」から、ProductionやRunを作らずに記事用PNGを収集する。UIは`StillLibraryPanel.tsx`、通信契約は`stillLibraryApi.ts`、HTTP境界は既存`server.py`、業務処理は`still_library.py`。DB schema 11で既存データを保持し、`still_images`と`still_image_edits`を追加する。既存の動画制作・Claude収録・音声処理は変更しない。

- 最初の版は、ローカルWeb（`http://127.0.0.1:1024..65535/`、認証情報・クエリ・fragmentなし）の表示領域／ページ全体／CSS要素撮影と、登録済みPNGからのコピーに対応する。PCは1440×900、モバイル幅は390×844、device scaleは1。モバイル端末自体のエミュレーションではない。
- `playwright_still.mjs`は新しいheadless Chromium contextを使う。ログイン済みプロファイル・Cookie・拡張を持ち込まない。同一origin以外のHTTPリクエストとWebSocketを遮断し、popupを閉じる。ページ・リソース読み込みの失敗や外部HTTPリソース依存は失敗扱い。これはブラウザのリクエスト制御であり、OS／ネットワーク全体の隔離保証ではない。
- JobManagerのcapture laneでプロセスツリーの封じ込め・45秒timeout・キャンセルを再利用。静止画Jobは一度に1件まで受付。完了判定は`jobs.status=succeeded`かつ検証済みmediaの存在。PNG生成後の中断でも、画像の配信・編集・exportを許可しない。成功／失敗のジョブ記録は残り、失敗時の途中ファイルはライブラリAPIから配信しない。
- PNGは最大24 MiB／1600万画素／一辺12000px。Pillowで完全デコードし、元のbytesとSHA-256を保存。取り込み元は既存artifact IDに限定し、直接パス指定・workspace外・symlink/junction・機密ファイル配置を拒否する。プレビュー／export時もhashを再確認する。
- 写真は`outputs/studio/stills/<still_id>/image.png`、撮影条件・manifest・成功したWeb撮影のcapture-reportを同じディレクトリへ保存。タイトル／メモはSQLiteに版として記録。撮り直しは新ID＋`parent_id`で関連付け、元画像を上書きしない。
- 受付ID＋要求digestで重複送信を照合。編集は`expected_revision`のCAS＋operation IDで再送対応。クライアントは送信前にopaque IDだけをlocalStorageへ保存し、応答喪失・再読み込み後はGET照会する。処理中かつライブラリを開いている間のみ3秒間隔で照会し、画面を閉じれば専用監視を停止する。
- 新APIのGETはStudio session必須。POSTは既存のsession／Origin検証を使用。exportは明示的な機密情報確認と版照合後、PNG＋README.md＋最小manifestのZIPを返す。URL・元パス・過去メモは配布ZIPへ含めず、現行メモはHTML-escapeした`pre`で記載する。画像内の個人情報・秘密は自動判定しないため利用者の確認が必要。

Claudeウィンドウの直接1枚撮影は上記の追加経路で対応。CLI／Codex capture、任意ファイルアップロード、複数画像一括export、注釈・crop加工、VMは未実装。既存Claude収録の登録済みPNGも取り込める。使い方と検証範囲は[STUDIO_STILL_LIBRARY_JA.md](STUDIO_STILL_LIBRARY_JA.md)を参照。

## 編集スタイルの30秒・6発話制作（2026-09-09）

`productions/SHORT_20260909_editorial_30s/`は新テーマを本尺に適用する案件用ドライバー。`story.json`に3章の見出し・6つの短い発話・開始時刻・投稿テキストを保存する。2本の10秒編集図解と既存実画面を共通`TimelineComposition`で30秒に組み、共通`generate_local_narration`へ6発話の明示スケジュールを渡す。実WAV長で章越え・発話重複を拒否し、共通`assemble_local_video`で字幕あり／なしのMP4を生成する。音声provider・rate・処理policyは変えない。

これはStudio DB上のrecipe／Run／Jobを作らないファイルベースの制作経路。workerのrun形式ディレクトリをDB保存RunやQC Jobと呼ばない。簡単作成UIの1章1発話制限は未変更。入力・ソースhash、発話時刻、両MP4全decode、確認ZIPのCRCと全entry hashを検証し、[制作記録](productions/SHORT_20260909_editorial_30s/README.md)に通常制作との境界を明示する。新規収録・課金API・画像生成・公開判定へのedgeはない。

実出力で字幕あり／なし30.000秒・720frame・1080×1920／24fps・AAC 48kHzを確認。6発話の章内収容、完成フレームの字幕非重複、確認ZIP10項目の読み戻しが成功した。専用6件と関連30件のテスト成功。音声品質は従来どおり保留し、サブエージェントは使っていない。

## 構成チェックと編集スタイル（2026-09-08）

`screenExplainerWorkflow.reviewScreenStructure`は保存済み下書きから、隣接場面の同じ素材ID＋注目矩形、同じ見出し、極端な横長矩形を検出する純粋関数。`ScreenExplainerPanel`の台本／生成確認段階へ3場面の役割と時間、改善助言を表示する。映像認識や音声解析ではなく、合格点・公開許可を返さない。警告で自動的に素材・台本・確認済み状態を書き換えず、既存validationとは独立する。保存／生成／収録の新しいAPIは追加しない。

選択式`claude_editorial_v1`を既存の閉じたtheme契約へ追加。通常書体のClaude Desktop識別文を使い、導入は暖色、ポイントは白、まとめは墨色へ切り替える。`screenSceneTheme`と`editorialChapter`を共通Remotionで解決し、12frameの見出し移動・不透明度変化は各sceneのframeだけから算出する。ロゴや疑似UIを使わず、映像枠・非公式表記・後段字幕の領域は固定のまま。旧4テーマの配色と演出は変更しない。API→版付きrecipe→Detailed→Node→描画の同じIDを検証し、音声の契約やタイミングを変更しない。

検証はフロント227件、関連Python42件、実React＋mock APIのUI3件、通常buildで成功。390pxで構成メモの縦並びと横はみ出しなし、テーマ変更時のsource ID／trim保持を確認。新規実収録・課金API・音声生成・公開受入はこの検証に含めない。共通compositionの実素材による6秒無音レビューは`productions/SHORT_20260908_editorial_review/`で独立に再現する。

## ロゴなしのイラスト素材を通常制作へ接続（2026-09-06）

`productions/SHORT_20260906_claude_illustrated/`は案件用の素材準備と再現ドライバーを置く。内蔵画像生成で作った独自イラストをworkspaceへ保存し、生成プロンプト・hashを記録する。専用Remotionはフレーム由来の動きと同梱Noto Sans JPで2本の無音7秒素材を作り、画像・ソース依存・出力bytes／hashをmanifestへ封印する。画像生成をStudioの汎用providerとして追加したものではない。

専用`produce.py`がmanifestと既存の封印済みClaude収録証跡を照合し、通常`import_production_video`で素材を登録する。別recipeの3場面へイラスト／実画面／編集図解を並べ、既存`claude_desktop_v1`から通常Quick Create・Detailed・assembly・QC・Deliveryへ進む。元の実画面専用ドライバーの同一source制限は緩めない。台本・声・7秒境界を維持して既存ナレーションcacheの再利用を狙う。追加収録・外部チャット・課金TTS・ロゴ取得へのedgeはなく、音声品質gateも変更しない。[制作記録](productions/SHORT_20260906_claude_illustrated/PRODUCTION_RECORD_JA.md)に出力と受入範囲を分離する。

実Run `run_a2df0ca5610949a397b125e5dd723da8`で21秒の字幕あり／なしMP4・通常技術QC・13項目のDeliveryまで成功。音声4artifact再利用と前版とのAAC payload一致を独立検証した。panelはPNG frame／BT.709で明示変換し、完成動画でも橙色の最大RGB誤差2を確認。15件の隔離テストと完成4フレームの目視は通過したが、音声・公開品質は未受入のままとする。

## 製品別・技術別の外観テーマと日本語見出し（2026-09-06）

画面解説recipeに省略可能な`screen_theme`を追加する。`neutral_v1`／`claude_desktop_v1`／`claude_code_v1`／`technical_v1`の閉じたIDだけを受け、画面解説以外へは渡さない。Studioの下書き・選択UIから版付きrecipe、Detailed clip、Remotion props、cache／manifest／監査まで同じIDを伝播する。未指定の旧payloadは正規化時に既定項目を追加せず互換性を保つ。テーマ選択で素材や台本は破棄せず、保存済みvoice／rate／pronunciationsも復元する。

`screenThemes.ts`が配色・識別文・非公式表記を定義し、`ScreenTypography.tsx`が同梱Noto Sans JPをFontFaceで読み込み、700ウェイトの見出し描画前に完了を待つ。動的ロゴURLや外部フォント通信、任意CSSは許可しない。TTFとOFL・両モジュールはrendererのfirst-party hash集合へ入り、固定TTFだけを一時publicへコピーし前後に実体照合する。Studioのstatic配信もTTFはWindowsのMIME推定に頼らず`font/ttf`を返す。読み込み失敗を代替フォントの完成として扱わない。音声処理や素材収録への新しいedgeはない。

Claudeのロゴ承認は未確認のため未実装。配色と通常書体の製品識別文を使う独立解説デザインで、DesktopチャットをCodeの実演と誤表示しない。[テーマ仕様・利用条件・検証範囲](STUDIO_TEMPLATE_BRANDING_JA.md)を参照。

## 実画面の文脈と試作用音声の比較（2026-09-06追補）

実Claude教材v4は冒頭の`focus_region`を省略し、既存screen layoutの全画面containを使用する。文字だけの切出しではアプリを識別しにくいため、最初にメニュー・会話・入力欄の文脈を見せる。後続の固定拡大と台本は維持する。新しいUI描画や収録は行わず、版付き通常制作・標準Deliveryへ接続する。

`audio_diagnostics.py`は封印済みv3とread-only DBからSAPI原音を解決し、hash照合後にPCM／AACの遅延・gain整列比較、クリップ等の計測、同ラウドネスWAVを作る。24k／48kの同声1文試験とWinRTの一覧診断は製品設定から分離する。周期ピークをノイズと決めつけず、既定sample rate・声・合成フィルターは変更しない。

`assemble_audio_review.py`は同じv4映像payloadと同音量のA／D音声を組み合わせるだけの比較用ドライバー。原音と候補をPCMから同じAAC設定で一度encodeし、全decode・尺・映像hash・encode後ラウドネスを確認する。比較コピーは通常納品や採用済み音声presetではなく、独立したmanifest付き`outputs/studio/verification/.../audio-video-review/`へ保存する。v3の作品品質は利用者評価で不合格、Dも「こもりはないがクリーンではない」との評価。[診断と判断](productions/SHORT_20260906_claude_desktop_real_capture/AUDIO_REVIEW_JA.md)を参照。

`spectrum_review.py`はこの診断manifestと原音／A／Dのhashを固定入力にする読み取り中心の案件用解析。NumPy／SciPyで発話を連結せず個別Welch PSDと時間周波数分布を計測し、Pillowの同一尺度PNG、数値CSV、入出力hash付きJSONを独立verificationへ出力する。挿入無音はPSDから除外し、文中のzeroも録音ノイズ床と見なさない。新規合成、フィルター適用、通常納品登録や品質gate更新のedgeを持たない。固定周波数の目立つノイズは今回の測定で特定できず、声の倍音・音節周期のピークを自動除去対象にしない。

### Local SAPIの連鎖cache参照

`StudioService._cached_local_narration_result`は、直近の成功attemptが再利用結果なら`cache_source_attempt_id`を辿って物理所有Runを解決する。各linkで同production・stage・成功状態・cache key・result metadata・4artifactのID／name／path／bytes／hashを照合し、最後に所有Runの厳密root、DB登録、symlink成分、実ファイルhashを検査する。循環・欠落・他制作・不一致・128link超はcache hitにせず安全側へ戻す。これにより「再利用した版からさらに再利用する」場合の不要な再合成を防ぐ。原本をcacheを使ったRunへコピーせず、監査参照を維持する。外部TTSは今回の修正対象外。

隔離した3runの回帰で修正前worker2回、修正後1回・同4artifactの再利用を確認した。実v4で起きた再合成履歴を成功cacheへ書換えてはいない。

## 実Claude教材の制作ドライバー（2026-09-06）

`productions/SHORT_20260906_claude_desktop_real_capture/produce.py`は、既存Studioの通常サービスを呼ぶ制作再現用ドライバーであり、別の編集・収録エンジンではない。`capture`と`render request.json`を分け、workspace lock取得後に既定DBを開く。収録受付を先に永続化し、成功したsource Jobの6成果物と実hashを封印してから、同じproductionの版付きrecipeをQuick Create／Detailedへ渡す。無音素材なので`narration_only_v1`と素材音量0を使う。納品は成功したDetailed topと工程別のexact artifactから既存Deliveryを作る。確認用JSON・進捗ログ・投稿情報txtを残し、未知の収録受付を自動再送しない。

Claudeへの送信はこのドライバーの外で、利用者が了承した架空データ1件だけをCodexのComputer Useで実施した。収録は回答取得後のウィンドウで、入力・送信の所要時間を測るものではない。API課金、外部投稿、声の購入、レジストリ変更は行わない。SAPI音声の列挙成功と合成成功、技術QCと公開品質を分離する。実行結果は[制作記録](productions/SHORT_20260906_claude_desktop_real_capture/PRODUCTION_RECORD_JA.md)で追跡する。

実績は30秒sourceから21秒・3区間を使うrecipe v3。通常4工程・QC・13項目のDeliveryまで成功し、区間だけ変更したv3はv2の4音声artifactを同一ID／hashで再利用した。字幕あり／なしの両MP4を全decode確認。実ウィンドウ846×572を出力1080p素材へ変換しているため、ネイティブ高解像度とは扱わない。聴感・スマートフォン可読性・公開品質は未受入。以下の初回スモークの「教材未完了」は、その検証時点の記録である。

### SAPIホストの互換性

実制作で、同じ端末でもWindows PowerShell 5系からはSayakaを選択できず、既存PowerShell 7.6.5からは同じ`System.Speech`と合成スクリプトでWAVを生成できることを確認した。通常経路のホスト探索を「既存PowerShell 7の標準位置 → PATH上のpwsh → 既存Windows PowerShell → PATH上のpowershell.exe」へ変更する。候補は存在する非symlink実ファイルに限り、インストールや任意のリクエスト指定パスは受け付けない。選んだホストで失敗したとき、別音声・別ホストへ黙って切り替えない。

音声cacheとmanifestの共有世代を`local-sapi-v2-pwsh-preferred`へ進め、preflight／manifestへ`host_selection_policy`を記録する。旧世代のWAVや動画を上書きしない。初回は新cacheになり、同じ新設定での映像だけの修正では再利用できる。これは音声購入や新TTSプロバイダーの追加ではなく、既存ローカル合成ホストの選択修正である。音質の聴感合格は別に判定する。

## Claude Desktop単一ウィンドウ素材と固定注目範囲（2026-09-06追補）

画面解説の対象をClaude Desktopに絞り、**1回の無音収録を目的・操作・結果の3場面で共有する経路**を追加した。素材の取得後は既存の版付き`screen_explainer_ja_v1` → Detailed Job → SAPI → Remotion → FFmpeg → 技術QC → 標準納品を使う。ソフト操作、プロンプト送信、会話の選択、ログインは自動化しない。見せる画面を事前に用意し、私的情報を含まないことを確認してから利用者が明示的に収録を開始する。

### 境界とデータの流れ

- `claude_capture.py`は既存FFmpegの`gfxcapture`（Windows Graphics Capture）と既存のプロセス封じ込めを再利用する。別のC#収録エンジンやデスクトップ全体へのfallbackは追加しない。対応対象はOSのpackage情報で確認できる公式MSIX版の`Claude_pzs8sxrjxfjjc` / `Claude_pzs8sxrjxfjjc!Claude`のみ。package配下の実行ファイル、PID・開始時刻、ウィンドウclass・寸法を束縛し、名前が`claude.exe`というだけでは許可しない。非MSIX版、任意アプリ、別のpackage identityは未対応である。
- inspectはWin32の候補列挙とエンジン利用可否の確認だけを行い、画面のpixelや音を取得しない。可視・非最小化のtop-level候補を最大16件、匿名番号・寸法・利用可否とopaque selection tokenで返す。タイトル、会話、実行パス、HWNDは公開しない。tokenはStudio sessionに束縛した有効期限60秒・単回利用のメモリ内capabilityで、再選択や期限切れ後は使えない。
- `POST /api/capabilities/claude-capture/inspect`の後、`POST /api/productions/{id}/claude-captures`へ`request_id`、`selection_token`、`duration_ms`、`confirm_capture: true`を渡す。任意HWND、パス、command、URL、音声指定は受け付けない。尺は15,000〜30,000ms。既存capture laneと共通の排他制御を使い、他の収録が動作中なら受付を拒否する。
- `claude_capture_service.py`は制作に属する`claude_window_capture` **source Jobだけ**を作る。収録のための架空Run、narration成功、assembly成功は作らない。成功判定は素材の構造・全decode・hashの確認であり、`capture_only: true`、`content_quality_verified: false`、`public_release_ready: false`を維持する。音声は`none`、音声streamは0で、無音WAVの捏造やAV同期gateの合格は行わない。後段の読み上げ音声はこの素材収録とは別工程である。
- 要求尺を下回らないよう24fpsのframe数を切り上げ、1920×1080・H.264・無音へcontain/padする。実測尺は要求以上かつ1frame未満の超過だけ許可する。元ウィンドウの寸法は別記録であり、小さいウィンドウを1920pxへ変換しても文字の情報量は増えない。
- 収録開始前・収録中・完了前に同じ対象を検査する。最小化、閉じる、非表示、対象identityや寸法の変化、移動・サイズ変更eventを検出したら停止する。短時間で元へ戻しても成功扱いにしない。取消・異常・DB登録失敗時は部分素材を登録せず、対象requestの既知ファイルだけを削除する。unknown file、symlink/junction等があれば安全側で停止する。
- UIは送信前に受付IDを保存し、応答不明時は`GET /api/productions/{id}/claude-captures/{request_id}`で同じJobを照合する。同じ受付ID・設定・sessionの再要求は同じJobを返し、不一致は拒否する。受付未確認を新規収録として自動再送しない。生tokenやprivate window identityはdraft・DB・ログへ保存しない。
- 保存先は`outputs/studio/claude-captures/{productionId}/{requestId}/`。MP4、先頭・末尾PNG、capture-report、ffprobe、manifestの6ファイルを検証してから、Job成功とartifact登録をDBの同じtransactionで確定する。生成中は同じ親の`.{requestId}.{captureId}.partial`を使う。起動時の掃除はそのDBが持つ未完了requestだけに限定し、別DBや他の制作の成果物を掃除しない。
- `screenExplainerWorkflow.ts`は共通MP4のartifact IDを3場面へ渡し、各尺の累積位置から連続区間を使う。台本・見出し・注目範囲だけの修正は同じ素材を再利用する。収録成功だけを完成動画として表示せず、素材確認後に通常の生成Jobへ進む。

### 読める範囲の指定と未受入部分

収録・probe・decode・PNG抽出の作業ディレクトリは `outputs/studio/runtime/claude-window-capture` に分離する。実機で確認したGPUドライバー由来の空の `NVIDIA Corporation/umdlogs` が成果物partialに混ざり、取消時の厳密cleanupを妨げる問題を防ぐ。動画・PNG・JSONは従来の絶対パスに出力し、未知の成果物ファイルを削除してよいことにはしない。ドライバー補助ディレクトリは素材として登録せず、限定cleanup対象にも含めない。

取消と清掃失敗が競合した場合も、Claude source Jobだけは `failed / claude_capture_cleanup_failed` を保持する。未解決の間はClaudeと既存Windows収録の両方を拒否し、起動時の清掃成功は別の監査イベントで記録する。失敗Jobを成功には変えない。DBコミット後に応答処理だけ失敗した場合は、成功を再照合して登録済み素材を保持する。

各場面の任意`focus_region`は元MP4全体に対する正規化矩形（`x, y, width, height`、0〜1、幅・高さ0.2以上、画面内）を表す。`screen_explainer_v1`だけで使用し、Remotionが選んだ矩形全体を既存960×540の画面枠へ固定拡大する。見出し・字幕の位置は保つ。指定がなければ従来の全画面containを維持し、既存clipに新fieldを挿入しない。矩形はrecipe・cache・manifestへ伝播するため、拡大範囲の変更も追跡できる。自動追尾、動的zoom、OCR、機密情報の自動ぼかしではない。素材previewで黒帯を含む実際の映像座標と、説明に必要な周辺情報を確認する。

**実装・技術スモークと実用受入は別**。初回はCUA上のClaude表示が白画面だったが、主担当の操作で表示が復帰した。白画面の原因は未特定。履歴を非表示にし、個人の会話・アカウント名がない画面で、標準source Jobによる15秒の実収録に成功した（1920×1080・24fps・360frames・無音・全decode・6成果物登録、Job経過約17.6秒）。先頭／末尾画像では未送信のテスト文が入力欄に入る変化を主担当が目視確認し、その文は後で消去した。Jobとhash等の証跡は[実機検証記録](STUDIO_SCREEN_EXPLAINER_VERIFICATION_20260906.md#実claude収録の技術スモーク)に分離する。

この素材は公開用教材ではない。Claudeの教材を3区間と固定拡大で標準制作経路の最後まで通す受入、SAPIの聴感改善、公開品質は未完了。なお準備中のCUA手動操作で「新規アーティファクト」をクリックした際、案内表示ではなくClaude側で自動依頼文1件の送信と生成開始が起きた。想定外だったため停止操作を行い、停止ボタンの消失を確認、生成成果物は得ていない。**Studio録画機能が会話を自動送信しないことと、今回の操作全体で送信がなかったことは別**であり、後者は主張しない。有料API、音声購入、外部投稿は行っていない。

## 画面解説テンプレートと素材準備（2026-09-06）

優先対象は編集ソフトの置き換えではなく、実画面を使う技術解説の素材準備と再利用。`ScreenExplainerPanel` / `screenExplainerWorkflow.ts` が目的・操作・結果の3場面を扱い、既存素材選択、動画取込、loopback Web画面の収録を既存APIに接続する。案件専用の映像レンダラーを追加せず、取得済みartifactを版付きrecipeへ渡す。実Claude教材のPythonドライバーは上記の通常サービス呼出と記録を再現するためのもの。

- 新recipe preset `screen_explainer_ja_v1` は15〜30秒・3場面・ハードカット。旧`shorts_ja_15s_v1`の10〜20秒・250ms fadeを維持。
- 任意clip `layout_preset: screen_explainer_v1` は縦1080×1920内に横画面をcontain表示し、上に見出し、下に字幕空間を確保。事前cropするH3鮮明化との併用は拒否。画面を切らないことは小さなUI文字の可読性を保証しない。
- 任意capture `viewport_preset: desktop_16_9` は1920×1080を選び、要求・Playwright・FFmpeg・probe・manifest・公開結果の寸法を照合。省略時は従来の縦収録。任意寸法・外部origin・cookie/profile・任意JavaScriptは不許可。
- 素材の取得済みIDを保持して再収録を省く。収録の応答不明時は既存Jobを照合し、nonceを持つ取得を勝手に再送しない。保存は既存CAS版管理、最終生成は通常Detailed Job→SAPI→Remotion→FFmpeg→QC→Deliveryを通る。
- ブラウザdraftは同一端末での準備再開用。素材・保存recipe・生成Jobは既存サーバー履歴に保持。ブラウザを閉じたまま素材収集操作を自動継続する機能ではない。
- ローカルWebアプリは隔離ブラウザで取得する。Claude Desktopは上記の専用・無音・単一ウィンドウ経路で実収録から3場面・固定拡大・標準納品まで技術E2Eを確認した。公開品質の受入は未完了。外部URL・任意Windowsアプリ・既存ブラウザsessionの流用は未接続で、手元の動画を取り込む。音声はSAPI試作。Sayakaの実合成と再利用は確認したが聴感は未受入。ElevenLabsの試聴・採用・一括接続は必要時の次候補で、無断課金や黙ったSAPI代替は行わない。

手順と実用受入は[STUDIO_SCREEN_EXPLAINER_JA.md](STUDIO_SCREEN_EXPLAINER_JA.md)を参照。

## 案件専用の非破壊音声処理試験（2026-09-05）

`productions/SHORT_20260905_claude_desktop_15s/denoise.py`は、利用者が報告したHaruka発話中のノイズに対する比較用スクリプト。元WAV／MP4をhashで束縛し、未圧縮音声からFFTノイズ低減・EQの軽め／強めと未処理対照を作り、固定遅延を補正して一定gainで同じラウドネスへ揃える。元MP4の映像はcopyし、WAVからAACへ1回だけencodeする。timestamp別outputsにレシピ、原音、候補、比較音声、probe、hashを残す。映像payloadと原本の不変性を確認し、音質の主観的合格は利用者の聴き比べまで保留する。標準Studio worker、Run／Job、費用承認、原版マスターを更新する機能ではない。

## 生成画像を挿入する案件専用経路（2026-09-05）

`productions/SHORT_20260905_claude_desktop_15s/` は、下記Codex版のローカル合成経路に、内蔵 `imagegen` で先に作ったPNGを加える制作例。Studioの一般向け画像生成APIや新しい課金workerを追加したものではない。

- `prompts/DESKTOP_HERO_IMAGEGEN.md` と素材台帳が生成指示・来歴を保持する。リモート内蔵ツールで生成した画像をignoredの案件assetsへコピーし、Remotion source reportでbytes／SHA-256を記録する。
- `ClaudeDesktopShort.tsx` / `render.mjs` が実画像を読み、カメラ移動と説明用UIを決定的に合成する。生成画像の欠落はエラーとし、生成された写真と実アプリ画面を映像中のラベルで区別する。MiniMax動画推論は使わない。
- 案件専用`assemble.py`は実SAPIのraw音声と句末静音を実測し、120msの余韻を残す末尾調整を独自の前処理identityとして記録して既存scheduled narrationへ渡す。音声のraw／処理後hashとタイミングを残し、通常の無加工SAPI cacheと混同しない。
- 外部画像生成とローカル描画／音声／合成／QCを来歴上で分離する。ローカル合成の`network_used:false`は内蔵画像生成までオフラインだったという意味ではない。正規のStudio素材取込・成果物登録を使い、通常pipelineの成功Run／Jobは作らない。

## 案件専用のローカル制作経路（2026-09-05）

`productions/SHORT_20260905_codex_15s/` は、Codex紹介動画を再現するための制作スクリプトと台帳であり、Studioの新しい一般向けテンプレートではない。

- `CodexShort.tsx` / `render.mjs`: 既存のStudio依存ライブラリを利用して、外部画像・APIなしで3本の1080×1920モーショングラフィックス素材を描画する。
- `assemble.py`: 既存SAPI workerの絶対開始時刻、Remotion timeline、FFmpeg assembly、技術QCを案件専用に呼び出す。標準告知recipeの見出し位置に制限されず、読み上げをカットへ整列できる。
- この経路は標準Detailed / Announcementの成功Jobや承認履歴を偽造しない。Studioには正規の動画取込と生成成果物登録を行い、独立worker実行ID・台本・時刻・hash・QC・手動投稿テキストを成果物として残す。標準納品ZIPの成功Jobを必要とするUI経路とは区別する。
- 大見出しは素材動画に焼き込み済みで、clean masterでも残る。後から付けた読み上げ字幕だけをcaptioned masterで追加する。MP4や音声・ログはignoredの`outputs/`、再生成ソース・制作判断はtrackedの`productions/`に置く。

## 目的と境界

このチェックアウトは、上流MiniMax H3のソース/モデル資料に、次の3経路を加えています。

1. Windows上のComfyUIによるローカル **H3-Base-FL2VA** 実行
2. Python標準ライブラリだけを使うMiniMax Video Generation V2 API操作
3. 制作案件の新規作成とローカル動画取込、run、artifact、ログ、承認、監査export、ローカルSAPIと承認制ElevenLabsナレーション、固定workflowによるローカルComfyUI動画生成、isolated Chromiumによるloopback Web画面収録、登録済み動画のローカルFFmpegハードカット／Remotion詳細timeline、既存素材からの詳細テスト動画一括実行、HOOK／MESSAGE／CTAの告知動画recipe、5判断の`かんたん制作`、非破壊制作ライブラリ、cut/timecodeレビュー、始点画像3枚から公式MiniMax H3 I2VAを経て15秒Quick Createへ渡す監査可能なCLI、汎用Job停止、音声・字幕合成、完成masterのローカルtechnical QC、検証済み納品ZIP、Windows収録の受入証跡、private／unlisted限定YouTube安全公開control-planeを扱うloopback専用 **MiniMaxH3 Studio MVP**

ローカル経路はH3-Baseの768px短辺キャンバスを対象にします。H3-Context-IRとH3-Regenerate-2Kはオープンソースreleaseに含まれないため、2K/Context-IR/Regenerateはローカル実行境界の外側で、公式API側の責務です。
[MiniMax H3公式の構成説明](https://github.com/MiniMax-AI/MiniMax-H3#model-architecture)と
[Recommended Workflow](https://github.com/MiniMax-AI/MiniMax-H3#recommended-workflow)が一次情報です。

処理経路の図は[ARCHITECTURE_DIAGRAM.md](ARCHITECTURE_DIAGRAM.md)に分離しています。

## 構成要素と責務

### 2026-09-05: コンテンツ品質・操作性を優先した整備

YouTubeへの自動送信は当面の完成条件から外し、手動投稿用の動画とテキストを出口にする。操作手順は [STUDIO_CONTENT_QUALITY_GUIDE_JA.md](STUDIO_CONTENT_QUALITY_GUIDE_JA.md) に記載する。

- `ProductionWorkspace` は「1. 作る」「2. 確認・修正」「3. 動画・投稿用テキスト」「素材・成果物」を常時表示し、他の12ツールは開閉式にする。既存の未保存変更確認・詳細編集・監査機能を維持する。
- `SimpleCreateWizard` は `simpleCreateStoryboard` と recipe compilerで同じ台本を共有し、作成前に3場面の見出し／セリフを表示する。見出しはbackendと同じ各行半角換算20（全角10）、2行以内として先に検証する。初回の取込・Job登録後に文字幅不一致で止まる問題を修正した。
- `contentQuality.ts` / `QuickCreateForm` は素材の実測情報、使用範囲の動画再生、見出しの仮表示、文字量と発話量の**助言**を担当する。これは品質スコアや発話時刻の実測ではない。英数字入りは推測秒数を出さず発音確認へ案内する。素材再生は自動開始せず、初期ミュート、指定範囲末尾で停止。字幕・音声・鮮明化は完成masterで確認する。
- 低解像度の縦素材には既存 `h3_low_res_sharp_v1` を簡単画面から選べる。実寸不明または対象外は新規選択不可。素材変更時は補正なしへ戻し、backendも実ファイルを再検証する。超解像モデルを追加したものではない。
- `media_metadata.py` は既存取込時ffprobe結果から `duration_seconds / width / height / fps / has_audio / video_codec` の6項目だけを抽出する。不明はnull。`.studio-production.json` schema 1の任意 `media_metadata`（上限512 KiB）にSHA-256・bytes・mtimeを結び付け、SQLite schema 10の `artifacts.media_metadata_json` へ索引する。再取込・再索引・再起動・複製を跨いで保持し、既知情報のGET時はstatによる変更検出を追加する。GETでprobeやhash走査はしないため、同一size/mtimeへの置換の完全検知は後段のhash検証に委ねる。旧生成素材への自動probe、および生成workerの既存probeを登録へ渡す接続は未実装で、旧素材の画素数は不明になり得る。
- `manualPublication.ts` / `DeliveryPanel` は既存Delivery sourceの検証を通ったclean/captioned動画の再生・保存と、現在のフォームのタイトル／説明文／任意タグをUTF-8 BOM付きtxtにまとめる。コピー不可時は選択可能なtextareaへ戻す。txtには日時、制作／Run／Job、動画ID／hash／サイズと判明している尺・画素数を含める。ZIPは既存13-entry契約を維持し、タグはtxtのみ。ZIP作成依頼時の入力snapshotと現在入力を比較し、画面再訪などでsnapshotがなければ一致未確認と表示する。フォームは自動保存しない。

「字幕なし」は読み上げ字幕なしで、大見出しは残る。高品質音声APIの一括制作への接続、字幕の独立編集、リップシンク、レビュー計画からの1カット自動再生成は、この整備で完了した機能ではない。

内部の `get_artifact()` と登録戻り値は従来の閉じた実行bindingを維持し、`get_artifact_view()` と制作詳細一覧にだけ素材metadataを付加する。Voice UpgradeやWindows Captureのexactな照合契約へ表示用フィールドを混入させない。Delivery梱包前後の監査identityは、内容が同じでも変わる取得時刻 `snapshot_at` だけを比較から除外し、ZIP内には時刻を残す。制作タイトル・監査イベント・master変更は引き続き検出する。Studioの納品処理表示はpanel独自pollだけでなく、共通Job更新から到着した成功・失敗も反映する。

今回の検証は [STUDIO_QUALITY_UX_VERIFICATION_JA.md](STUDIO_QUALITY_UX_VERIFICATION_JA.md) に記録。Python 666件（1 skip）、frontend 169件、build、実ブラウザーからの15秒ローカル一括作成・技術QC・投稿txt・13-entry納品ZIPを確認した。映像・音声の表現品質を保証する試験ではない。

| 構成要素 | 責務 | 状態 |
|---|---|---|
| `setup-local.ps1` | Python 3.12 venv、固定Git commit、固定Python依存を導入。dirty repoを保護 | tracked |
| `runtime-lock.json` | ComfyUI/ComfyUI-GGUF/Turbo custom node commit、Python target、torch3種、lock fileを定義 | tracked source of truth |
| `requirements-local-lock.txt` | Windows AMD64 / CPython 3.12で確認したtorch以外のPython依存をexact pin | tracked |
| `download-models.ps1` | license確認後、固定HF revisionからprofileモデルを取得し、容量・byte数を検査 | tracked |
| `model-manifest.json` | model role、repo/revision/path、byte数、SHA-256、license/source URL | tracked source of truth |
| `run-local.ps1` | doctorをgateとしてloopback ComfyUIを起動し、VRAM modeを排他的に構成。custom nodeをprofile別allowlistへ閉じ、対応workflowの手動open先と開始・終了時system metricsを表示 | tracked |
| `tools/system_metrics.ps1` | CPU使用率/温度、RAM、NVIDIA GPU使用率/温度/VRAM/電力をbest-effort取得。保存や連続監視はしない | tracked |
| `runtime/ComfyUI/` | ComfyUI本体、custom node、モデル、Comfyの一時状態 | untracked/ignored |
| `workflows/minimax_h3_t2v_lowvram.json` | GGUF向けT2V、0.2MP、4秒指定、20 steps | tracked |
| `workflows/minimax_h3_t2v_lowvram_turbo.json` | 任意のGGUF + Turbo LoRA経路、0.2MP、5秒指定、simple / 6 steps、merge | tracked / experimental |
| `workflows/minimax_h3_t2v_lowvram_q4_turbo.json` | 品質優先のQ3 diffusion + Q4 text encoder + Turbo経路、0.4MP、5秒、simple / 8 steps、merge | tracked / experimental |
| `workflows/minimax_h3_t2v_official_q4.json` | 公式INT8 ConvRot diffusion + Q4 text encoder、0.4MP、5秒、simple / 20 steps | tracked / 0.6MP・5秒・20-step Emergency run確認済み。tracked 0.4MP既定は未検証 |
| `workflows/minimax_h3_t2v_official_q4_turbo.json` | 公式INT8 ConvRot + Q4 + Turbo LoRA、0.4MP、5秒、simple / 8 steps、merge | tracked / unverified on target hardware |
| `workflows/api/minimax_h3_t2v_official_q4_v1.json` | Studio API専用の公式INT8 ConvRot + Q4 text encoder、約480×864、124 frames / 24fps、20-step固定graph。prompt、seed、出力prefixだけを内部注入 | tracked source of truth |
| ComfyUI Template Library | `official` profile用の公式T2V JSON | installed Python package/runtime |
| `tools/local_doctor.py` | hardware/resource、core lock、model、profile別workflowを非破壊検査 | tracked |
| `run-api.ps1` / `tools/h3_api.py` | `.env`読込、V2 submit/status/wait/download、preflight/security gate | tracked |
| `setup-studio.ps1` | frontend依存、exact pinしたPlaywrightとRemotion `4.0.517`一式を導入し、固定revisionのChromiumをinstall／launch検査、Remotion doctor、Python backend module、frontend buildを検証 | tracked |
| `run-studio.ps1` | `127.0.0.1`限定でbackendとbuild済みUI、または開発用Viteを起動 | tracked |
| `studio/` | React / Viteによる制作一覧、案件詳細、artifact preview / A-B比較、event、cost、approval、ローカルSAPI／ElevenLabsナレーション、固定ComfyUI動画生成とprovider task復旧、Playwright画面収録、`local_pipeline`一括生成と自動継続state、既存素材向け`詳細一括`と2秒top-job監視、HOOK／MESSAGE／CTA告知recipeの保存・複製・preview・一括実行、同じ告知draftを扱う`QuickCreateForm`、新規制作・テンプレート・動画1〜3本・主文の約5判断で既存exact endpointへ収束する`SimpleCreateWizard`、非破壊制作ライブラリ、artifact/revision/run/cut/timecodeに紐付くレビュー、FFmpegハードカット編集、共通Remotion compositionを使う詳細timeline Player preview、カット別の閉じたSource Fidelity v2 preset、字幕preset付き合成、technical QC UI、`納品・公開`タブのローカルDelivery Package作成UI | tracked source。現UIはYouTube preview／uploadを起動しない。`node_modules/`と`dist/`はignored |
| `tools/studio/announcement_video.py` | exactな告知recipe schema v1、3シーン／10〜20秒／見出し／ナレーション制約、250ms fadeと固定overlay位置、Detailed Test Video v1へのcompile | tracked source of truth |
| `tools/studio/production_intake.py` | exactな新規production schema、output-owned制御metadata、bounded raw video upload、production内partial、SHA-256／ffprobe検証、content dedupe、atomic publish／cleanup | tracked source of truth |
| `tools/studio/quick_create.py` / `quick_create_project.py` / `shot_orchestration.py` / `job_control.py` | 既存告知経路の1コマンドCAS保存・実行・低頻度terminal照合とredacted結果、新規production作成・ローカルvideo取込・indexed recipe compile、3枚の始点画像から公式H3 I2VAを3件だけ明示送信してexact 15秒recipeへ渡す再開可能なshot project、ならびにexact schemaの汎用Job停止contract | tracked source of truth |
| `tools/studio/production_library.py` / `reviews.py` | 制作のrename・archive/unarchive・取込素材付きduplicateを物理削除なしで扱うoperation ledgerと、artifact/revision/run/cut/timecode単位のcreative/rights/public_releaseレビューをimmutable eventから再構築する契約。部分修正は現時点では`planned_not_executed`かつM4 adapter未接続 | tracked source of truth |
| `tools/studio/delivery.py` | 成功済み詳細一括のexact lineageとQC passを再検証し、clean／captioned master、SRT、QC 3文書、3 thumbnail、title／description、production snapshot、event JSONL、自己検証manifestを決定的ZIPとSHA-256 sidecarへまとめる0円・ローカル納品worker | tracked source of truth |
| `tools/studio/voice_upgrade.py` / `voice_upgrade_execution.py` | 取得済みElevenLabs WAV／文字alignmentをHOOK／MESSAGE／CTAのscene開始時刻へ配置し直すpure-local alignment coreと、成功済みexternal narration attempt／登録artifactを再検証してpath-freeな0円結果とartifact registration recordへ分けるexecution boundary。次sceneへの重なりを拒否しWAV／SRT／timing／manifestをcacheする | tracked core＋execution contract。`execute-voice-upgrade` route／`voice_upgrade` Job／atomic stage registrationと、登録済み公開結果を厳密再検証するassembly入力分岐まで接続。provider再呼出しなし。Studio UIと告知／Delivery自動接続は未実装 |
| `tools/studio/windows_capture_acceptance.py` | Windows収録8成果物のhash identity、A/V marker統計、loudness／true peak、device切替、親強制終了cleanup、人手attestationを閉じた受入判定へ変換する | tracked source of truth。実機合格証拠は未取得 |
| `tools/studio/youtube_publish*.py` | Delivery／選択master／3 human gate／channel／metadataを束縛するpreviewと明示execute、private／unlisted限定resumable upload、DPAPI session ledger、曖昧状態の自動再初期化拒否 | tracked backend control-plane。Studio公開UI、実OAuth接続、実uploadは未受入 |
| `tools/studio/` | production索引、schema v9 SQLite、artifact配信、run/approval、stage attempt、永続provider task／local video request claim／detailed-test content claim、告知recipeのevent由来immutable version／CAS／clone／execution link、production library state／operation ledger、append-only review event、default/GPU/browser/pipeline分離job lane、background再起動照合、`local_pipeline` continuation台帳／enqueue-only coordinator／cache-only動画checkpoint、Detailed Test Video v1 orchestrator／dedupe／same-run retry、Windows SAPI narration/cache、ElevenLabs `with-timestamps` contract／worker／課金gate／cache、固定ComfyUI contract／worker／cache／再起動照合、loopback-only Playwright capture contract／Chromium worker／FFmpeg MP4変換、FFmpegハードカットtimeline/cache、閉じたRemotion schema／Source Fidelity v2前処理／worker／cache、字幕preset付きFFmpeg assembly/cache、FFmpeg/ffprobe technical QC/cache、`test-video`直列orchestrator、DPAPI secret、audit export API | tracked |
| `tools/studio/sapi_synthesize.ps1` | UTF-8 JSON fileからSystem.Speechへ安全に入力し、segment WAVを出力するローカルhelper | tracked |
| `outputs/studio/` | schema v9 SQLite、hash chain付きevent JSONL mirror（告知recipe、production library、review actionを含む）、暗号化secret、外部送信marker、監査ZIP、`shot_projects/<project_id>/plan.json`／`state.json`／3 MP4、run別動画生成／Playwright画面収録／ナレーション／FFmpeg timeline／Remotion timeline／詳細一括のchild lineage／合成／technical QC成果物、`deliveries/`の納品ZIP＋sidecar、`youtube/`の公開state・staged source・DPAPI保護session | untracked/ignored |
| `.env` | MiniMax／ElevenLabs API key、任意MiniMax base、任意YouTube OAuth credential JSON | untracked/ignored secret |
| `outputs/` | `run-local.ps1`およびCLIの生成物。Studio作成productionは`outputs/productions/<id>/.studio-production.json`とcontent-addressed `imports/`を持つ | untracked/ignored |

現在のStudio DB schemaはv9です。以下で`schema v8`と記すprovider task、pipeline continuation、detailed-test、Windows captureの各台帳はv8で導入された契約を指し、v9でも互換のまま保持されます。v9はその上にproduction library state／operation ledgerを追加します。

## 再現性モデル

### 既定setup

`setup-local.ps1` は `runtime-lock.json` の3つのGit SHAへdetached checkoutし、PyTorch cu130の3 exact versionと `requirements-local-lock.txt` を導入します。fresh clone、既存clean mismatch、既存dirtyを区別します。3つ目は任意profileが使うTurbo custom nodeですが、ComfyUI process内で自動importされるcodeなので、利用有無にかかわらず固定・検査します。

- fresh: 通常cloneでworking treeを展開した後、固定SHAへcheckout
- clean mismatch: 必要なcommitをfetchし、固定SHAへdetached checkout
- dirty + 固定SHA一致: repository mutationをskipしwarning
- dirty + mismatch、またはdirty treeでの`-Update`: mutationせず停止
- `-Update`: clean repositoryでだけremote HEADと未固定Python依存へ明示更新

`-Update` 後はcore lockと不一致になり得ます。doctorの `Locked core runtime matches` は、3 Git HEAD、Python 3.12、torch/vision/audioだけを照合します。`requirements-local-lock.txt` 全行とinstalled distributionの完全一致を表すものではありません。

### モデル

model downloaderは `model-manifest.json` のHF revisionとremote pathを使います。取得直後はexact byte数を検査し、full SHA-256はdoctorの `--hash` で明示実行します。モデル本体はGit管理せず、`runtime/`配下に置きます。

## ローカル生成データフロー

1. operatorがprofileを選び、licenseを確認します。
2. downloaderがHugging Faceからprofileごとの4 model artifact、またはTurboを含む5 artifactを `runtime/ComfyUI/models/` へ配置します。
3. doctorがtotal/free VRAM、total/available RAM、pagefile、disk、core lock、VAE chunked I/O、custom node、モデル、workflow wiringを検査します。
4. `run-local.ps1` が開始時system metricsを取得し、`127.0.0.1` のComfyUIをforeground起動します。`--disable-all-custom-nodes`を常に付け、通常profileは`ComfyUI-GGUF`だけ、Turbo profileは固定Turbo nodeも追加して明示allowlistします。profileは検査対象を選びますが、workflowをUIへ自動ロード・切替しません。
5. operatorがlauncherの `Open manually:` 表示に従い、lowvramではtracked GGUF workflow、lowvram_turboではQ2 Turbo workflow、lowvram_q4_turboではQ4 Turbo workflow、officialではTemplate Libraryの公式T2V、official_q4ではtracked stock 20-step、official_q4_turboではtracked Turbo 8-stepを明示的に開きます。
6. ComfyUIがtext encoder、FL2VA diffusion model、任意のTurbo adapter、video/audio VAEを読み、videoとstereo audioをMP4にmuxします。
7. ComfyUI終了後、launcherが終了時system metricsと経過時間を表示します。通常の生成物出力先は `outputs/` です。

ComfyUIの公式モデル配置とloader名は
[ComfyUI MiniMax H3 tutorial](https://docs.comfy.org/tutorials/video/minimax/minimax-h3)に準拠します。

## Profileとworkflowの対応

| Profile | Diffusion / text encoder | Workflow loader | 必ず使うworkflow |
|---|---|---|---|
| `lowvram` | community FL2VA Q3_K_M / Qwen Q2_K | `UnetLoaderGGUF` / `CLIPLoaderGGUF` | tracked `workflows/minimax_h3_t2v_lowvram.json` |
| `lowvram_turbo` | `lowvram` + Larryvrh v4 step600 EMA | GGUF loaders + `MiniMaxH3TurboLoRA` / `MiniMaxH3TurboSampler` | tracked `workflows/minimax_h3_t2v_lowvram_turbo.json` |
| `lowvram_q4_turbo` | community FL2VA Q3_K_M / Qwen Q4_K_M + Larryvrh v4 step600 EMA | GGUF loaders + `MiniMaxH3TurboLoRA` / `MiniMaxH3TurboSampler` | tracked `workflows/minimax_h3_t2v_lowvram_q4_turbo.json` |
| `official` | Comfy-Org int8 convrot / nvfp4 awq | `UNETLoader` / `CLIPLoader` | Template Library → Video → MiniMax H3 T2V |
| `official_q4` | Comfy-Org int8 convrot / community Qwen Q4_K_M | `UNETLoader` / `CLIPLoaderGGUF` | tracked `workflows/minimax_h3_t2v_official_q4.json` |
| `official_q4_turbo` | official_q4 + Larryvrh v4 step600 EMA | `UNETLoader` / `CLIPLoaderGGUF` + `MiniMaxH3TurboLoRA` / `MiniMaxH3TurboSampler` | tracked `workflows/minimax_h3_t2v_official_q4_turbo.json` |

profileとworkflowを交差させません。doctorもprofileに応じて別のworkflow contractを検査します。

Turbo workflowは `UnetLoaderGGUF → MiniMaxH3TurboLoRA → BasicScheduler / BasicGuider` と `MiniMaxH3TurboSampler → SamplerCustomAdvanced` のlinkを固定します。Q2版はstrength 1.0、`low_vram=true`、0.2MP、simple / 6 steps、Q4版は同じmerge条件で0.4MP、simple / 8 stepsです。doctorは内側loaderだけでなく、実行時に優先されるtop-level subgraphのdiffusion/text/video VAE/audio VAE overrideをexact比較し、ResolutionSelectorのwidth/height linkも検査します。作者がQ3 GGUFを対応baseとして明示していないため、両経路ともexperimentalです。non-Turbo `lowvram` とQ2 Turboをfallbackとして残し、bypassはdefaultにしません。

Q4 text encoderは [`realrebelai/MiniMax-H3_GGUFs` の固定revision](https://huggingface.co/realrebelai/MiniMax-H3_GGUFs/blob/daf03b4ca652cce16dfd4fcf91e79c52ffa5c1e7/qwen3vl-32B-MiniMax-H3-Q4_K_M.gguf)から取得し、`CLIPLoaderGGUF` のtype `minimax` で読みます。固定[ComfyUI-GGUF loader](https://github.com/city96/ComfyUI-GGUF/blob/6ea2651e7df66d7585f6ffee804b20e92fb38b8a/loader.py)とcoreはQwen3VL text encoderとMiniMax H3の50層構成を扱えますが、generic Qwen3VL vision/mmproj対応は上流の[Issue #471](https://github.com/city96/ComfyUI-GGUF/issues/471) / [PR #473](https://github.com/city96/ComfyUI-GGUF/pull/473)で未統合です。このprofileはH3 T2V conditioningだけを対象とし、汎用I2V/mmproj対応を主張しません。

GGUF mergeではcustom nodeの汎用canaryが見るmodule `weight_function` ではなく、ComfyUI-GGUFの `GGMLTensor.weight.patches` にpatchが保持されます。このため `weight_patched=False` はQ3経路ではfalse negativeになり得ます。受入証拠はLoRA nodeのaccepted patch数/AdaLN injection、sampler完走、同seedでLoRAを外したA/B出力差を組み合わせます。

ComfyUI本体は[PR #15446](https://github.com/Comfy-Org/ComfyUI/pull/15446)のmerge commitへ固定しています。`MiniMaxH3VideoVAE.comfy_has_chunked_io`をcore VAE wrapperが認識し、video全体のpixel-space copyを保持せずtemporal chunk単位でencode/decodeします。モデルやworkflowの置換は不要です。これはpeak VRAM/RAM削減であり、sampling高速化とは別の責務です。

## VRAM mode

`run-local.ps1` は共通引数としてpreviewなし、pinned memoryなし、全custom node無効化とprofile別allowlistを設定し、VRAM modeを排他的に追加します。

| Mode | ComfyUI引数 | 意図 |
|---|---|---|
| 通常 | `--enable-dynamic-vram` | ComfyUIのDynamic VRAMを明示有効化 |
| Emergency | `--novram --cpu-vae` | Dynamic flagを外し、モデルoffloadとCPU VAEを優先 |

競合するVRAM modeを避けるため、引数配列では必ず排他にします。launcherは他アプリを終了しません。

## 開始・終了時のsystem metrics

`tools/system_metrics.ps1` はComfyUIの起動直前と終了直後だけsnapshotを標準出力へ表示します。連続polling、ファイル保存、外部送信はしません。CPU/RAMはWindows CIM、NVIDIA GPUは `nvidia-smi` のquery interfaceを使用します。

CPU package温度はWindowsが常に公開する情報ではありません。LibreHardwareMonitor/OpenHardwareMonitorのWMI sensorを優先し、なければfirmwareのACPI thermal zoneを「CPU packageではない」と明示して表示します。どちらも取得できない場合はtemperature unavailableと表示し、起動を妨げません。GPU queryを含むmetrics取得失敗もwarningへ縮退し、ComfyUIの実行可否からは分離します。

一次情報: [Microsoft thermal zone diagnostics](https://learn.microsoft.com/en-us/windows-hardware/design/device-experiences/examples--requirements-and-diagnostics)、[NVIDIA nvidia-smi query fields](https://docs.nvidia.com/deploy/nvidia-smi/index.html)。

## APIデータフロー

1. CLIが `.env` を読み、base/keyをローカル検査します。
2. `submit` はprompt/media/mode/ratio/sizeをpreflightし、`--confirm-billable` を必須確認します。
3. local mediaはData URLへ変換され、Bearer付きで `POST /v2/video_generation` に送られます。
4. `status` / `wait` は `GET /v2/query/video_generation/{task_id}` をpollします。
5. success responseのMP4 URLは、Bearerなしの別download requestで取得し、temporary fileからatomic replaceします。

API contractは[MiniMax V2 Create](https://platform.minimax.io/docs/api-reference/video-generation-v2-create)と
[V2 Query](https://platform.minimax.io/docs/api-reference/video-generation-v2-query)です。CLIが新規課金taskを作るのは明示的な `submit --confirm-billable` だけです。

## Studio MVPデータフロー

1. `setup-studio.ps1`がfrontend依存、exact pinされたPlaywright `1.62.1`、`remotion`／`@remotion/player`／`@remotion/renderer`／`@remotion/bundler`／`@remotion/transitions`の同一version `4.0.517`を導入します。`NODE_OPTIONS`／`NODE_PATH`／任意`PLAYWRIGHT_BROWSERS_PATH`／`REMOTION_*`を外したruntime同等環境で、対応Chromium revisionのinstall／実launchとRemotion package・browser整合性をdoctorで検査してから`studio/dist/`をbuildします。Windowsでは外部NuGet依存のない`native/windows-capture-helper`もRelease buildしますが、Core Audio doctorは自動実行せず、画面収録tabの明示操作まで待ちます。HTTP request中にbrowser、package、native helperを自動downloadしません。
2. `run-studio.ps1`が`python -m tools.studio.server`を`127.0.0.1:8765`で起動します。通常時は同じoriginからbuild済みUIを配信し、`-Dev`時だけViteを別loopback portで起動します。
3. backendがtracked `productions/`の台帳、ignored `outputs/productions/`のartifact、Studio作成案件のexact `.studio-production.json`を読み、`outputs/studio/studio.sqlite3`へ検索用索引を構築します。制御ファイルはartifactから除外し、titleとcontent-addressed importの既知SHA-256だけをIndexerへ渡します。eventはscope別hash chainとして`outputs/studio/events/`のJSONLにも追記します。起動時は各有効production配下の閉じた命名規則に一致するvideo／metadata partialだけを清掃し、未知entryやsymlinkでは起動をfail closedにします。
4. UIは制作一覧、run計画/stage、artifact、event、cost、費用approvalをHTTP APIで取得し、登録済みmediaのpreviewとA/B比較、順序付きカット編集を提供します。`新しい制作`はPOST前に安定ID／title intentをversioned `localStorage`へ保存し、応答消失時はexact ID＋title GETだけで復旧します。告知draftの破棄確認はdraftが現在のproductionに紐付いている場合だけで、初回作成時の未選択production同士を誤って同一draftと扱いません。任意の動画素材は最大16件を1件ずつraw bodyで送り、backendがproduction内partialへstreamし、SHA-256／ffprobe検証、content dedupe、atomic publish、metadata replace、Indexer refresh、`production.media_imported` eventの順に確定します。service-level intake lockが同時create／importのmetadata lost updateを防ぎます。frontendはcreate/import/cancelの201／201／202と要求identityを再照合し、別production、別artifact、別Jobまたは欠落fieldを成功表示へ採用しません。既存のFFmpegハードカットpreviewに加え、Remotion詳細previewはbrowser内の`@remotion/player`とbackend renderで同じtracked composition／schema v1を使います。`詳細一括`は登録済みclip、SAPI台本、固定字幕／音声mix／QC選択を一画面で確定し、top jobと4 childを2秒pollingします。既定の`かんたん作成`タブは同じDetailed経路をHOOK／MESSAGE／CTAの3シーンへ閉じる告知recipeを、管理名、3動画、大見出し、ナレーションという3段階の入力で扱います。15秒を基準にし、短い素材ではcompile後の実尺を表示します。内部の`かんたん作成 | 詳細設定`は同じdraftとcontrollerの表示切替で、Quick Create側は直接APIを呼びません。固定既定から外れる保存済みrecipeは詳細設定へ開き、隠れた値を上書きしません。両表示とも既存の告知recipe CAS保存、immutable version、clone、消音Player preview、一括実行を共有します。実行中はJob一覧を2秒、production detailを初回と3回ごとのおおむね6秒で取得します。汎用停止操作はexact Job IDとschema versionだけをbackendへ渡し、停止要求とworker退役を別々に表示します。worker未退役なら同じendpointを2秒間隔・最大15回だけ再照合し、停止中ID集合へ残します。全体停止は同じRunの`local_pipeline`／`detailed_test_video` topがactiveまたは停止照合中の間はchildを抑制し、topのない孤立childだけをfallbackとします。告知用の保存・複製・実行・照合requestはprivate `AbortSignal`をforwardして15秒で中断します。保存は同じCAS identityを1回再送します。複製はsource identityと名前からSHA-256先頭128-bitのclone IDを決定的に導出し、sourceごとの独立したversioned `localStorage` keyへID／作成時刻をPOST前に同期保存します。panel unmount／production切替／reload後も同じIDを再送し、複数tabの競合も同じbackend IDへ収束します。runtime validationとread-after-writeを通せない場合はPOSTせずfail closedにし、exactな成功応答またはimmutable版履歴のclone lineageでだけ自動消去します。timeout／network error／再送後4xxでは保持し、明示破棄はbrowser intentだけを消してserver recipeを削除しません。曖昧な実行POST応答では送信後に増えたexecution linkのexact Jobだけを受理証拠にし、なければ同じimmutable revisionを1回だけ冪等再送します。2回目のPOSTまたはfresh linkのexact Job照合が曖昧なら自動処理を止め、フォームの永久lockを避けて手動再照合へ戻します。production detailは切替時に旧controllerをabortし、request generationと選択IDが一致する応答だけをstateへ反映し、`detail.id === selectedId`だけを描画します。artifact内容は登録済みpathと許可rootの検査を通った場合だけ返します。safe redaction未対応の設定/markup、未知形式、外部archiveは415で拒否し、Studio自身が生成・検証した監査ZIPだけをdownload対象にします。

`かんたん作成`はfrontend presentation boundaryだけです。既存の告知save endpointから同じexact revisionを既存execute endpointへ渡し、0円`local_sapi`のDetailed topと既存pipeline／browser／default laneを使います。詳細設定と同一のRun、Job、child attempt、artifact、technical QC、execution link、event chain、監査exportへ収束し、新しいendpoint、worker、lane、claim table、DB schema、output directoryを追加しません。画面で詳細値を隠すことはsecurity boundaryではなく、session保護、exact backend schema、content claim、artifact再hash、cost／approval記録を従来どおり正本とします。

`quick-create-project` CLIはfrontend presentationではなく、既存serviceのproduction intakeとQuick Createをworkspace lock内で順次呼ぶcontrol-plane boundaryです。schema v1は安定production ID／title、request documentの論理的親directory基準のrelative regular video 1〜3件、recipe ID／expected revision、0-based `video_index`を持つexact告知recipe、任意timeoutに閉じます。全選択videoは少なくとも1 sceneから参照され、各sourceはopen file identity／size／mtime／消費bytesをimport後に再照合します。production作成とその索引更新→各videoのstream importと索引更新→artifact IDへのrecipe compile→CAS保存／Detailed実行／terminal照合を一つのmonotonic deadlineに閉じます。成功resultはproduction identity、順序index付きartifact identity／bytes／SHA-256／dedupe、既存Quick Createのredacted resultだけを持ち、source path／filenameとrecipe本文をstdout／stderrへ複製しません。途中失敗では確定済みproduction／importをrollbackせず、同じ安定ID／bytesの再実行を冪等create／content dedupeへ収束させます。この経路は新しいHTTP endpoint、worker、lane、DB schema、output directory、renderer、課金providerを追加しません。

### M1〜M4の制作支援境界

- M1 `SimpleCreateWizard`は、制作名、3つのversion固定テンプレート、動画1〜3本、主文、最終確認という約5判断を、既存のproduction create／raw import／announcement save／executeへ収束させます。production／recipe IDは最初のPOST前にversioned `localStorage`へ保存し、応答消失後も同じIDでread-before-write再開します。path、token、動画本体は保存しません。2026-09-05以降の取込は実測durationを永続化し、recipe末尾を素材尺へ制限します。10〜20秒というrecipe全体の制約は維持し、短すぎる素材で不足を埋めたり、長尺を勝手に引き伸ばしたりしません。旧素材など実尺不明の場合は後段検証も必要です。
- M2 `production_library.py`はoutput-owned productionだけにrename、archive/unarchive、取込素材付きduplicateを提供します。archiveは既定一覧から隠すだけでartifactを削除しません。client-issued operation ID、route sourceを含むrequest digest、期待状態をschema v9のimmutable operation ledgerへ束縛し、event mirrorから復元します。tracked productionと制御metadataのないoutput-only productionはread-onlyです。
- M3 `reviews.py`はartifact／revision／Run／cut／timecodeをexact identityとしてcreative／rights／public_releaseのコメント、判定、解決をappend-only eventへ保存します。technical QC passとhuman release gateは別です。cut修正planは他cutのexact artifact再利用方針を持ちますが、M4 rerun endpointには未接続で、常に`planned_not_executed`、`not_started`、`not_connected`、`job_id=null`を返します。
- M4 `shot_orchestration.py`はCodexの画像生成スキル等で先に作った3始点画像とH3 prompt skill形式の3 I2VA promptを受け、公式MiniMax H3 V2 APIへ6秒／768Pを3件だけ送信します。`confirmed_billable_task_limit=3`をexactに要求し、各送信前の`prepared`、task ID、出力bytes／SHA-256を`outputs/studio/shot_projects/<project_id>/`へatomic保存します。応答消失後は自動有料再送を行いません。3 MP4を再hashし、各trimを0〜6,000msへ閉じ、5,167／5,167／5,166msから2境界250ms fadeを差し引いた15,000msをQuick Createへ渡します。API keyはDPAPI `SecretStore`から解決し、plan/state/resultへ保存しません。local ComfyUI presetはT2VA-onlyであり、このI2VA経路をローカル実行とは扱いません。

### M5〜M6の納品・受入・安全公開境界

- M5 Delivery Packageは`POST /api/productions/{production_id}/delivery-packages`から`delivery_package` Jobを作ります。入力は成功済み`detailed_test_video`のRun／top Jobと、clean master、captioned master、SRT、technical QC、QC ffprobe、QC manifestの6 artifact IDへ閉じます。backendは同じproduction／Run／child attemptのexact lineage、物理bytes／SHA-256、captioned有効、technical verdict `pass`をqueue前とworker内で再検証します。workerは上記6点、clean masterの25／50／75%位置から作るPNG 3枚、title／descriptionの`metadata/publication.json`、production snapshot、hash-chain event JSONL、全entryのbytes／SHA-256を持つ`delivery/manifest.json`を決定的`delivery-package.zip`へまとめ、ZIP自身のSHA-256 sidecarを隣接保存します。外部送信はなく、公開結果は`network_used=false`／`billable=false`です。Studioの`納品・公開`タブはこのローカルZIP作成とdownloadだけを提供し、review gateは表示するもののDelivery作成自体は未承認でも可能です。
- M5の高品質音声準備として`voice_upgrade.py`は、すでに取得済みのElevenLabs PCM WAVと文字alignment／segment timingのhashを再検証し、exactなHOOK→MESSAGE→CTA 3 scene scheduleへ各segmentを配置します。scene 1は0ms、scene開始は単調増加、総尺は60秒以内で、発話が次scene開始または出力末尾を越える場合は`voice_upgrade_segment_overlap`で停止します。出力はローカルcache内のaligned WAV、SRT、timings、manifestです。`voice_upgrade_execution.py`は同じproduction／Runの成功済みElevenLabs narration attemptと登録済みWAV／timingsをbytes／mtime／SHA-256まで再検証し、pathを含まない`provider=local_voice_upgrade`／`actual_cost=0`の公開結果と4 artifact registration recordへ分離します。`POST /api/runs/{run_id}/execute-voice-upgrade`は`elevenlabs_tts` Runのnarration stageだけを受け、`voice_upgrade` Jobと新stage attemptを永続化して4 artifactをatomic登録します。そのstage attemptをassemblyへ指定すると、serviceは公開結果のexact key、provider、0円cost、schedule、source lineage、4登録artifactの一致を再検証してからWAV／SRTを入力にします。これらはElevenLabsへ接続せずcredentialを読み込まず、Job auditは`network_used=false`／`billable=false`です。専用execution／service／HTTP／assembly入力testと公開error allowlistはありますが、Studio UIと告知／Deliveryへの自動接続は未実装です。
- M6 Windows capture acceptanceは`POST /api/runs/{run_id}/windows-capture-acceptance`で、成功済み`local_windows_capture` Jobの8 artifactをDB／物理file／bytes／mtime／SHA-256まで再検証し、schema v1のrequest提供測定値とoperator attestationをappend-only eventへ束縛します。3〜20個のvisible／audible marker差、Integrated loudness、true peak、収録中の既定device切替、親強制終了cleanup、5 operator attestの申告値を評価して`self_reported_thresholds_met`とfailed checksを記録しますが、request提供のcalibration tool digestとattestは独立した証拠lineageではありません。登録済みcalibration Jobと、serviceがbytes／SHA-256／tool lineageを再検証できる証拠artifactが実装されるまで、schema v1は常に`blocked_unverified_calibration_lineage`、`content_sync_verified=false`、`public_release_ready=false`、`live_validation_required=true`へfail closedします。2026-08-30 smokeも合格証拠ではありません。acceptance eventは元capture resultやreview gateを書き換えず、現YouTube bindingもこのeventを自動参照しません。
- 以前のroadmapでM7と呼んでいたYouTube連携は、DeliveryとWindows受入に続く現M6の**安全公開control-plane**へ整理しました。`POST /api/productions/{production_id}/youtube-publish-preview`はDelivery ZIPと、そのZIP内で検証したclean／captioned masterの一方、title／description／tags／category／made-for-kids／synthetic-media、OAuthで解決したchannel identity、creative／rights／public_releaseの3 human gateを一つのconfirmation digestへ束縛します。各gateは`approved`、未解決0件、review 1件以上が必須です。次の`POST /api/productions/{production_id}/youtube-publish`は同じrequest／channel／digestに加え、Community Guidelines certificationとupload確認の2つのliteral `true`を要求するため、previewとexecuteの厳密な2段階です。privacyは`private`または`unlisted`だけで、`public`はschema validationで拒否します。
- YouTube credentialは最小scope `https://www.googleapis.com/auth/youtube.upload`のclient ID／client secret／refresh token JSONを既存のWindows user-scoped DPAPI `SecretStore`へ登録できます。解決順は`YOUTUBE_OAUTH_CREDENTIAL_JSON`環境変数、workspace `.env`、DPAPI storeで、interactive OAuth bootstrap自体は実装せず事前取得済みrefresh tokenを要求します。uploadはGoogle公式の[`videos.insert`](https://developers.google.com/youtube/v3/docs/videos/insert)と[resumable upload protocol](https://developers.google.com/youtube/v3/guides/using_resumable_upload_protocol)に合わせます。credential-bearing requestのHTTP redirectは`youtube_redirect_rejected`で拒否し、background Jobへ出す失敗はallowlist済み`error_code`と有界な`public_message`だけです。公開JSON ledgerはtokenとsigned session URIを含まず、session URIだけを別のDPAPI ciphertextへ保存します。session確立後はproviderが認識したbyte位置から再開しますが、session初期化responseを失った`ambiguous`状態、保護session欠損、期限切れでは別の`videos.insert`を自動開始せず`recovery_blocked`へ止めます。desktop credentialの準備はGoogle公式の[OAuth 2.0 for Desktop apps](https://developers.google.com/identity/protocols/oauth2/native-app)を参照します。backend contract／ledger／fake transport回帰は実装範囲ですが、Studioの公開操作UI、実Google OAuth credentialでのchannel確認、実upload、YouTube上のprivate／unlisted動画確認はまだ実施していません。公開済み、課金済み、YouTube受入済みとは扱いません。

Job停止のprocess所有境界はoperator cancelとJobManager shutdownで異なります。operatorがexact Jobを停止する場合、対象contextへ明示登録したroot PIDとそのprocess treeだけを終了します。この経路でserver processの全descendantを走査すると、cancel baselineより後に別laneで開始したsibling Jobを巻き込むため行いません。未登録descendantのprocess-wide fallback sweepは、全worker laneとprovider recoveryを停止するJobManager全体shutdownだけで許可します。これは登録済みrootのdescendant再帰終了を弱めず、cross-laneのprocess所有権だけを分離するboundaryです。
5. 再実行計画は、変更工程、再利用候補、追加費用、`execution_profile`を記録します。課金対象のrequested stageを含む通常runは正の見積額を必須とし、0以下または未指定ならfail closedにします。`local_sapi`はnarration/captions/timeline/assembly/qcだけを対象にした0円profile、`elevenlabs_tts`はnarrationを必須とする課金profile、`local_comfyui`はvideo_generationを必須とする0円profile、`local_playwright`はscreen_captureを必須とし、screen_captureとtimelineだけを実行可能とする0円profileです。`local_playwright` Runの`requested_stages`はscreen_capture／timelineだけに固定し、assembly／qcはgeneric rerun planの`affected_stages`へ影響工程として残しますが、このprofileでは実行しません。profileが許可する明示的な実行操作でattemptとjobを作成し、schema v8の`job_id`、provider task、pipeline continuation claim、detailed-test claim、hash-chain eventを永続化してからworker queueへ入れます。CPU／FFmpeg系のdefault lane、長時間GPU生成のGPU lane、Chromium収録とRemotion renderのbrowser lane、top-level orchestrationのpipeline laneは各1 workerのFIFOとして分離します。browser lane内でも収録と詳細timelineはFIFOで、Remotion render自体のconcurrencyは1です。同じリンクの再適用は冪等です。event mirrorからはattempt側の履歴Job IDと、厳密に検証できるdetailed-test Run claimを復元しますが、一時的なjobs検索表そのものは再構築せず、完了状態はattempt記録を正本にします。Studio生成artifactは完全metadataを持つ`artifact.created`または成功済みstage/job resultから候補を得て、`outputs/studio/`内の非symlink通常file、stable ID、bytes、SHA-256、既存ID/path衝突を再検証できたものだけ検索行を復元します。`local_pipeline`は固定workflowの動画生成、SAPIナレーション、生成動画1本を全尺1カットにするtimeline、assembly、QCを一つのimmutableな0円Runへ束ねます。requested stageは`video_generation`、`narration`、`captions`、`timeline`、`assembly`、`qc`の6段、実行stageはComfyUI動画生成→SAPI→one-clip timeline→assembly→technical QCの5段です。`POST /api/productions/{production_id}/execute-local-pipeline`は専用pipeline laneでGPU childとdefault childを協調させ、DBのcanonical pipeline keyでRun/top jobをdedupeします。詳細一括と告知動画は同じpipeline laneからbrowser／default childを協調します。告知recipeから投入する場合は、Detailed top Jobの作成／再利用とrecipe execution linkを同じSQLite transactionで確定します。
6. local narration workerは検証済みJSONをPowerShell helperへfile渡しし、Windows System.SpeechでsegmentごとのWAVを生成します。SAPI preflightと合成processはいずれもjobのcancel contextへ登録し、停止時はprocess treeを終了します。実WAV frame数から字幕時刻を求め、`narration.wav`、`captions.srt`、`timings.json`、`manifest.json`をrun/cache key配下へatomicに確定します。成功artifactのpath、bytes、SHA-256とworker metadataを再検証してから登録し、同一入力はhash検証済みcacheだけを再利用します。1 segment 32 MiB、結合WAV 128 MiB、総尺30分を上限とします。
7. external narrationは、`elevenlabs_tts` profile、narration工程、正の見積、費用上限approval、literal booleanの`confirm_billable=true`をbackendで検証した後だけcontract、secret、provider workerへ進みます。workerは固定の[ElevenLabs `with-timestamps` endpoint](https://elevenlabs.io/docs/api-reference/text-to-speech/convert-with-timestamps/)へ、固定`eleven_multilingual_v2`／`mp3_44100_128`、voice、全voice setting、seed、改行結合したsegmentを1回だけPOSTします。redirectを拒否し、応答size／deadlineを制限します。`audio_base64`をFFmpegでPCM WAVへ変換し、文字単位alignmentからsegment SRT/timingを作り、local narrationと同じ4成果物をatomic publishします。`request-id`と`character-cost`を記録しますが、API応答からUSD実費を確定できないため`actual_cost=null`を保持します。課金POST前にproduction/cache identityの永続markerを排他的作成し、成功成果物確定時だけ削除します。timeout、5xx、切断など送信結果が曖昧な場合は`external_submission_unknown`として、別Runからも自動再送しません。
8. local ComfyUI workerは、公開bodyを固定`workflow_preset`、prompt、0〜2^63−1のseedだけに限定し、tracked API graphへprompt／seed／出力prefixだけを注入します。新規POST前にworkflow file／canonical graph、公式INT8 diffusion、Q4 text encoder、video/audio VAE、FFprobe binary、2 lock file、ComfyUI／GGUF／Turboの固定HEADと非ignored clean状態を照合します。Windowsでは新しいPOST attemptごとに4 modelをwrite/delete共有なしのread handleで先に開き、その同じhandleからfull SHA-256を計算してpublish後の最終検証まで保持します。これにより実行中の書換え・削除・置換を拒否し、既にwriterが開いているmodelも送信前に拒否します。非Windowsだけは物理file identity付きprocess cacheを使います。同じloopback connectionの`/system_stats`で、`run-local.ps1 -Profile official_q4`（任意の`-NoBrowser`）が生成するmain.py、listen/port、output directory、ComfyUI／PyTorch／Python version、Dynamic VRAM、custom-node disable／exact GGUF allowlistを含む完全なargvを照合します。未知・重複・equals形式の引数、Emergency／Turbo／precision変更、model path redirectを拒否し、`runtime/ComfyUI/extra_model_paths.yaml`も存在またはsymlinkなら拒否します。環境proxyとredirectを無効化してからPOSTし、生成結果は送信時の出力prefixへ束縛します。MP4、fresh ffprobe、workflow、自己hash付きmanifestを`generated-video.mp4`、`workflow.json`、`ffprobe.json`、`manifest.json`としてatomic publishします。prompt本文はworkflow audit artifact以外のpublic result、event、SQLiteへ複製せず、SHA-256、文字数、exact seed decimalだけを記録します。

ComfyUIへの新規送信ではStudioがUUIDを事前発行し、schema v8の`provider_tasks` rowとfsync済みmarkerへ保存してから、同じUUIDを`POST /prompt`の`prompt_id`として渡します。公開APIの同一Run／cache key／payload digest要求は`local_video_generation_claims`をSQLite transaction内で獲得し、同じsingle-instance Studioへ届く同時requestを1つのactive job／attemptへ集約します。Studioの複数processをactive-activeで動かす設計ではなく、全公開entrypointが既存のworkspace instance lockで第二起動を先に拒否します。ComfyUI応答が完全一致しない場合や送信結果が不明な場合はmarkerを残して`ambiguous`へ止まり、自動再POSTしません。providerがterminal failureを返した場合はmarkerを`terminal_state=failed`へfsync置換してから例外化し、次回起動でも失敗を確定できます。promptを含むprovider再開payloadと、prompt／台本／字幕／音声設定を含む正規化済みpipeline継続requestは、現在のWindowsユーザーに紐づく別々のDPAPI暗号文としてSQLiteへ保存します。平文と暗号文は公開API、job、event、監査snapshotへ含めません。

HTTP serverは全responseへ`Connection: close`を付け、1 request／1 handlerへ寿命を限定します。終了時はlistening socketを閉じ、request-line／header／bodyの解析中socketだけを遮断します。解析済みでservice処理へ入ったnon-daemon handlerは応答完了までdrainし、その後にbackground provider recovery、job worker lane、SQLite interruption writerを停止します。`JobManager.shutdown()`が全threadの終了を確認した場合だけ`StudioService.close()`を完了し、最後にsystem-wide workspace lockを解放します。timeoutまたは例外でworkerが残った場合はcloseを失敗させ、再試行またはprocess終了までlockを保持します。これにより、旧processのHTTP handlerやwriterがSQLite／provider taskを更新したまま、新processが同じworkspaceを取得する重複稼働を許しません。Windowsでは既にblockした`makefile().readline()`が別threadからのsocket closeで直ちに解除されないため、未解析requestの無通信を1秒のinactivity timeoutでも有界化します。このtimeoutは解析済みservice処理の実行時間制限ではありません。

Studio起動時は外部HTTP照合をconstructorから分離したbackground coordinatorが行うため、ComfyUIが遅い場合もloopback HTTP serverのbindを待たせません。旧jobを`interrupted`、旧attemptを`failed(process_interrupted)`として保持したままprovider taskのownerを解放し、marker、payload digest、cache key、Run、固定runtime、`GET /api/jobs/{prompt_id}`を照合して同じRunへ新しいrecovery attempt/jobを追記します。provider IDが既知の復旧はpoll/cache回収だけを行い、`prepared`かつ未送信と証明できるtaskだけが最初のPOSTへ進めます。CAS claimの敗者は勝者の状態を変更しません。観測時刻は`last_observed_at`として実際のprovider照合時だけ更新し、UIの2秒polling時刻をprovider確認時刻として偽装しません。正常完了時はprovider task、job、attempt、4 artifact、eventを同じtransactionで成功確定し、暗号文を消去します。worker failure時もprovider task、job、attemptを同一transactionで閉じ、永続化callbackだけが失敗した場合は暗号文とmarkerを保持した`recovery_blocked`として再照合可能にします。明示cancelはjob=`interrupted`、attempt=`failed(process_interrupted)`、provider task=`cancel_requested`を同じSQLite transaction・同じ時刻で確定し、暗号文とmarkerを保持します。startup／manual再照合は同じUUIDへのGETとtargeted cancelだけを使い、生成用`POST /prompt`へは到達しません。未送信を永続記録から証明できる場合はlocal terminalへ確定し、running／404／一時的な照合不能は`cancel_requested`を保持して重複生成を遮断します。provider terminalをDBへ確定した後だけ所有markerと暗号文を削除します。
9. local Playwright workerは、`POST /api/runs/{run_id}/execute-local-screen-capture`のbodyを`url`、`duration_ms`、`settle_ms`、最大16件のscroll/click/pressだけに閉じます。対象は明示port付き`http://127.0.0.1`に限定し、userinfo、fragment、外部host、異なるoriginへのredirect／subresource、WebSocket、service worker、download、既存Cookie／storage、proxy、任意JavaScript／browser flag／output pathを拒否します。毎回新しいChromium contextをbrowser専用FIFO laneで起動し、1080×1920 viewportを1〜30秒収録します。生WebMを指定区間へtrimして1080×1920／24fps／H.264／yuv420p／video-only MP4へ変換し、full decodeとfresh ffprobeを通してから、MP4、生WebM、始点／終点PNG、sanitized report、ffprobe、自己hash付きmanifestの7成果物をdirectory renameでatomic publishします。URL全文、query、selector本文はSQLite、job、event、report、manifestへ保存せず、originとSHA-256だけを残します。live page stateは再現可能なcontent cacheではないため、実行ごとにnonce付きcapture keyを発行して`cache_hit=false`とします。このprofileで実行可能な工程はscreen_captureとtimelineだけです。assembly／qcは影響工程としてRun計画へ残りますが、このprofileでは実行しません。

Windows native captureは、non-recording capability境界と実行境界を分離します。session保護された`POST /api/capabilities/windows-capture/inspect`は厳密な`{}`だけを受け、`windows_capture.py`がrepository-owned DLLとsource、dotnet、FFmpeg、ffprobeのidentity、Core Audio doctor、`gdigrab`、物理プライマリ解像度をshellなし・stdinなし・各10秒／64KiB上限で検査します。doctorは既定render/console endpointで共有WASAPI loopback clientを固定48kHz stereo s16leへ初期化しますが、`Start`／buffer取得／device ID取得／マイク列挙を行いません。結果は既知boolean、固定reason code、解像度、pathを含まないtool digestだけで、DB、Job、Run、attempt、artifact、event、画面sample、音声sampleを作りません。readyなら`capture_execution_enabled=true`ですが、診断の`actual_capture_performed=false`は固定です。

実録は`local_windows_capture` Runの2段階routeだけです。まず`POST /api/runs/{run_id}/windows-capture-consent-intents`が60秒・単回使用・session／Run／固定設定拘束のtokenを発行し、次に`POST /api/runs/{run_id}/execute-windows-capture`が同じ設定とtokenを受けます。strict schemaはprimary display、default-render loopback、hidden cursor、1〜30秒、画面／system audioの別々のliteral confirmationだけを許し、path、HWND、window title、display／device ID、microphone、任意tool argumentを拒否します。raw tokenは永続化せず、一方向token digestとsession bindingだけをschema v8のappend-only consent intentへ保存します。token消費、attempt、Jobを1 SQLite transactionで確定するため、同じtokenの再送はterminal後も元Jobへ収束し、新しい録画には新tokenが必要です。未消費intentはrestartで無効化します。新規admissionは直前にdoctorを再実行し、同じtool identityであることをworkerでも再確認します。専用capture laneは同時1件で、別tokenまたはretiring workerを409で拒否します。成功録画は別intentへ再利用せずnonce keyを使います。

`windows_capture_worker.py`はhelperとFFmpegをsuspendedで生成し、`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`付きWindows Job Objectへ割り当てた後だけresumeして固定start gateを開きます。親の異常終了、割当失敗、FFmpeg準備失敗では録音を継続できません。子processのenvironmentはWindows／tool実行に必要なallowlistだけで、Studio session token、provider key、proxy、hookを渡しません。WASAPI helperのexact PCM stdoutを匿名pipeで単一FFmpegへ渡し、同時に`gdigrab`でprimary originをcursorなしで記録します。helperは`Start`後に同じSTA threadで`GetBuffer`／`ReleaseBuffer`を必ず対にし、全経路で`Stop`します。WASAPI位置／QPC timestampを保持して実際のgap位置へzeroを挿入し、timestamp error、overlap、過大gap、driftを成功扱いしません。`gdigrab`のwallclock PTSは0起点へshiftし、raw PCMは先頭sampleをPTS 0としてmuxします。workerはmaster packetのvideo／audio開始差を検査し、上限を超える場合はpublishしません。両入力の実内容を同じclockで観測してはいないため、構造同期と実内容同期の判定は分離したままです。

workerは固定1920×1080／24fps／H.264＋AAC combined MP4、video-only MP4、PCM WAV、始点／終点PNG、sanitized report、fresh ffprobe、自己hash付きmanifestの8点だけをstageします。raw masterは`.<capture_key>.partial`の決定的private directoryだけに置き、通常削除に失敗した場合は成功を返しません。cleanup失敗はRun配下markerと固定`outputs/studio/windows-capture-cleanup-ledger.json`へ`run_id`／`capture_key`／`target_kind`だけをatomic・fsync・read-back付きで記録し、DBのexact cleanup-error lineageにも残します。起動時は未消費consentを無効化した後、JobManagerより先にpartial、marker、fallback ledger、DB lineageのexact targetだけを再清掃します。ledger／DBの読取、parse、照合、削除の失敗はいずれも起動をfail closedにし、一般のfailed Jobや別成果物は削除しません。清掃成功後だけledger entryを解消し、markerとledgerの両方へ書けない同一processでもworkspace latchが次の録画を拒否します。combined MP4のfull decode、3媒体のstream／codec／duration、raw masterと最終MP4それぞれのvideo/audio `start_time`／duration／開始差、frame／sample境界、全fileのbytes／SHA-256をfresh ffprobeで再検証してからdirectory renameし、Job／attempt／artifactを`AtomicStageCompletion`で同時確定します。これはcontainer timestamp／durationとWASAPI packet clockの構造検証であり、gdigrab映像内容とWASAPI音声内容の同一時計による相関観測ではありません。report／manifest／Job resultは`structural_timing_verified=true`、`content_sync_verified=false`、`live_validation_required=true`を分離し、`blocked_pending_live_av_sync_validation`を公開gateとして残します。DB確定失敗、cancel、publish後検証失敗のregistered outputもexact lineageだけを補償削除します。reportは同期／sample counterだけで、device identity、path、生stderrを残しません。`local_windows_capture`はscreen_capture／timelineだけをrequested stageにする0円profileで、Windows実録だけのsingle-worker `capture` laneを使います。activeまたはretiring captureがあれば別要求をqueueせず拒否し、同じ消費済みtokenだけを元Jobへ集約します。登録済みcapture MP4は同じproductionのlocal timelineへ明示的に渡せます。自動検証はlive routeを起動していないため、実機でのA/V実内容同期、音質、収録中device切替は明示承認付きsmokeまで未確認です。
10. local timeline workerは、`local_sapi`／`local_playwright`の両profileから明示実行でき、同じproductionの登録済み・availableな動画artifactだけをbackendでpath／bytes／SHA-256再検証し、1〜32カット、各50ms以上、合計30分以内のtrimを順序どおり連結します。入力は専用一時directoryの固定名へcopyし、任意pathやfree-form FFmpeg optionを受け付けません。出力は1080×1920、24fps、H.264／yuv420p、video-only MP4、ハードカットへ固定します。24fpsへの変換では累積時間から各カットのframe予算を割り当て、カットごとにその枚数だけをconcatして境界重複や終端カット欠落を防ぎます。`timeline-preview.mp4`、`timeline.json`、`ffprobe.json`、自己hash付き`manifest.json`をatomic publishし、cache keyには順序、artifact ID、trim、入力hash／bytes、frame-budget v2を含む固定出力policy、解決済みFFmpeg／ffprobeのversion・binary hashを含めます。画面収録とtimelineのUIはジョブ状態と進捗率を2秒pollingで表示します。
11. Remotion詳細timelineは既存ハードカットを置き換えず、`POST /api/runs/{run_id}/execute-remotion-timeline`から別の`timeline` stage attempt／browser FIFO jobとして明示実行します。jobの`kind`とattemptの`provider`は`local_remotion_timeline`です。schema v1は同じproductionの登録済み動画1〜16件、各trim、素材音量0〜100%、次カットへの`fade` 50〜2,000ms、各trim内の任意テロップ1件と、任意の閉じた`visual_preset=preserve_v1 | h3_low_res_sharp_v1`だけを受け付け、出力尺を最大60秒に制限します。visual presetがない既存のRemotion／Detailed／Announcement recipeは互換既定`preserve_v1`へ正規化します。最後のclipにtransitionは置けず、fadeは隣接する両clipより短くします。テロップは最大200文字／4行、位置`top | center | bottom`、固定style `shorts_ja_large_v1`だけです。UIの`@remotion/player`とrendererは同じtracked compositionを使いますが、Playerは原素材を表示し、backendのFFmpeg前処理を再現しません。Source Fidelity v2で`h3_low_res_sharp_v1`を選べるのは幅1080未満・高さ1920未満、両辺64px以上、幅÷高さ0.50〜0.625、cover拡大後300万画素以下の低解像度縦長sourceだけです。workerは条件をFFmpeg起動前に検証し、必要frameへ先にtrimして、テロップ合成前に固定Lanczos cover 1080×1920、luma-only unsharp 5×5／0.25、chroma 0を適用します。`preserve_v1`は原sourceを固定名copyします。これは欠落detailを再生成する超解像ではなく、追加のCPU時間、一時I/O、encode時間を消費します。renderはsetup済みPlaywright Chromiumを明示再利用し、concurrency 1、PNG中間frame、H.264 CRF 16／x264 medium、1080×1920／24fpsへ固定します。`remotion-preview.mp4`、`remotion-timeline.json`、`render-report.json`、`ffprobe.json`、自己hash付き`manifest.json`の5成果物をfull decode／fresh ffprobe後にatomic publish・一括登録します。cache keyと監査summaryにはSource Fidelity v2の出力policy、各clipのpreset、固定前処理policy、schema、recipe、入力bytes／SHA-256、composition・Node script・Remotion package／browser・FFmpeg／ffprobeのtool identityを含めます。rendererのfirst-party build closureである`entry.tsx`、`TimelineComposition.tsx`、`model.ts`、`api.ts`、`status.ts`、`types.ts`も個別にhashし、cache keyとrender後の再照合へ同じ集合を使います。render reportとmanifestにはこれらに加えて、各clipへ実際に適用した前処理結果を記録します。これにより旧policyのcacheを再利用せず、exact 5成果物を再検証できた場合だけ再利用します。再現用`remotion-timeline.json`にはテロップ本文を平文保存しますが、job／event／render report／manifestへは複製せず、reportのcontent policyがrecipe側の本文有無を明示します。詳細previewの素材音声はvolume設定を反映し、後続assemblyの閉じたpresetで置換または固定比率mixを選択できます。

Remotion runtimeはsetup時に、Remotion 5 packageとPlaywrightをrootとする実`node_modules`依存closureを列挙し、通常dependency、installed optional dependency、peer dependencyを含む通常fileのbytes／SHA-256をpath非公開のattestationへ集約します。symlink、junction相当の解決先変更、special fileを拒否し、通常doctorとworker開始時にinstalled treeを再計算します。closure digest／package・file・bytes数はtool identityとcache keyへ入り、renderer終了後にも同じattestationを再照合するため、実行途中のdependency変更は成果物publish前に`tool_changed`で閉じます。attestation file自体はignored `studio/node_modules/`配下で、`npm ci`後に`setup-studio.ps1`が再生成します。
12. Detailed Test Video v1は`POST /api/productions/{production_id}/execute-detailed-test-video`を、H3生成を伴う`local_pipeline`とは独立したcontrol-plane境界として実装します。public schema v1は`schema_version`、Remotionのexact `clips`、SAPIのexact `segments`と任意`voice`／`rate`／`pronunciations`、`include_captioned`、`caption_style_preset`、`audio_mix_preset`、`variant`だけを許し、任意path、URL、CSS、React component、renderer prop、free gainを拒否します。`shorts_ja_large_v1`では固定`shorts_ja_large_preflight_v1`を適用し、1〜6 segment、1 segment表示幅38単位以内、連続ASCII 20文字以内、不可視／bidi制御文字なしをqueue前に必須化します。normalized payload、source artifact bytes／SHA-256、Remotion tool cache identity、preflight policyからrequest keyを作り、schema v8の`detailed_test_video_claims`が同一production／requestを一つのimmutableな0円`local_sapi` Runへ束縛します。内部実装世代は`detailed-test-video-v3`とし、Source Fidelity v2／visual preset互換既定を含まない旧ローカルclaimとはrequest keyを分離します。同じqueued／running topと物理再検証済みsucceeded topは再利用し、failed／interrupted／改変検知時は同じRunへ新topを追記します。`revision.created` eventはclaim identityも保持し、event mirror復元ではprofile、0円、requested stage、Run／revision、64桁request keyを厳密照合してactive jobなしのclaimだけを再構築します。top Jobの監査payloadには、公開requestを正規化してkey順でcanonical JSON化した`request_payload_sha256`を保存します。UIがdirect POSTの応答を失った場合は、POST前に存在しなかったJobのうち、production、kind、stage、profile、request key形式、このpayloadダイジェストが完全一致し、告知専用timing fieldを持たないものだけを同一送信として採用します。既知Job、ダイジェスト欠落、告知Jobとの取り違えはfail closedにします。topはpipeline laneからWindows SAPI→Remotion→assembly→QCを順次実行し、Remotion childだけをbrowser lane、他のchildをdefault laneへ送ります。各childのexact job／attempt／production／profile／Run／stage／cache resultと、受渡しartifactのID／相対path／bytes／SHA-256を検証し、Remotion recipeとassembly／QCの尺が一致した4 child成功かつQC passの場合だけmasterと3 QC文書を公開します。cancel／timeout／failureはcurrent childをjoinしてからtopをterminalにします。UIはtopを2秒pollingし、完了時の尺はJob結果を正本として表示します。この経路はComfyUI、MiniMax API、ElevenLabs、secret、費用approvalへ到達せず、既存`local_pipeline`のschema v4／one-clip hard-cut経路を変更しません。
13. Announcement Video v1は`tools/studio/announcement_video.py`で、`shorts_ja_15s_v1`、HOOK／MESSAGE／CTAのexact 3 scene、各1〜10秒、fade overlapを差し引いた10〜20秒、必須の1行ナレーション、1〜2行のsafe headlineへ閉じます。新規UIの既定trimは5,167ms／5,167ms／5,166msで、2回の250ms overlap後を360 frame／15.000秒にします。最初の2境界は250ms fade、大見出しはtrim内125ms inset、位置は中央／上／中央、styleは`shorts_ja_large_v1`固定です。告知実行は各trimと各fadeをRemotion compilerと同じ24fpsで個別にhalf-up丸めし、frame cursorへ加減算して各sceneの出力開始を内部`announcement_scene_starts_v1` policyで導出します。SAPI結合WAVへframe単位の無音を挿入してSRTも同じ時刻へ揃え、前segmentが次scene開始を越える場合はoverlapせずfail closedにします。このprivate scheduleと開始時刻はnarration cache、Detailed request key、job／attempt監査、timing／manifestへ含め、通常の公開SAPI bodyと非告知cache identityは変えません。保存APIは`expected_revision` CASで`announcement.recipe.saved` eventへimmutable versionを追記し、exact canonical JSONをbytes／SHA-256／Base64と監査summaryで保持します。複製はexact source versionをclone lineageへ記録します。実行APIは保存済みrevisionを既存Detailed schemaへcompileし、同じcompile結果とscene timingはDetailedのcontent claimとRunを再利用します。queued／runningまたは物理再検証済みsucceeded topがあれば同じJobを返し、failed／interruptedなら同じRunへ新topを作ります。recipe名だけ異なるcloneでも、各versionの`announcement.recipe.executed` linkは別に残します。top Jobの作成／再利用とexecution linkは同じSQLite transactionで確定します。UIは曖昧な応答で、fresh execution linkのexact Job GET、続いて同一immutable revisionの1回限定冪等再送を行います。既知の成功履歴だけでは解除せず、2回目も曖昧なら手動再照合までlockします。Base64は暗号化ではなく、recipe本文はevent mirror／監査exportから読めるため、秘密を入力しません。BGM、ロゴ画像、任意renderer／CSS／React component、新規H3生成はこのcontractにありません。
14. local assembly workerは、同じproductionの登録済み動画と同じRunの成功済みlocal SAPIまたはElevenLabs narration artifactをhash再検証します。FFmpegまたはRemotionのtimeline previewも登録済み動画として使用できます。音声は閉じた`narration_only_v1`（互換既定、sourceを置換）または`source_under_narration_v1`（source 25%＋narration 100%＋固定peak limiter）だけを許し、任意gain／filter／BGM／duckingは受け付けません。mix時はsource audioがちょうど1 streamあり、source／narrationを独立decodeしたpeakがそれぞれ−60 dBを超えることを必須にし、両方を48kHz stereoへ正規化して動画尺へpad／trimします。欠落・実質無音はfail closedです。短いナレーションだけを`apad`し、250msを超える尺超過を拒否します。SRTは厳密parse後にoverride不能な固定style ASSへ変換します。互換既定`studio_default_v1`に加え、YouTube Shorts向けのYu Gothic UI 80px、bold、5px outline、左右96px／下300px余白を固定する`shorts_ja_large_v1`を選べます。任意font path、ASS filter、free-form styleは受け付けません。clean版と任意のcaptioned版をH.264 / yuv420p / AAC / MP4へencodeし、`ffprobe.json`と自己hash付きmanifestとともにatomic publishします。cache keyには入力hash、字幕preset、字幕有無、音声mix preset、音声・出力方針、解決済みFFmpeg/ffprobeのversion・binary hashを含めます。現行local pipelineのhard-cut previewはvideo-onlyなので一括生成は`narration_only_v1`固定です。
15. local technical QC workerは、選択中Runの成功済みassembly attemptからbackendが導出したcleanまたはcaptioned masterだけを受け取ります。assemblyがcontent-addressed cacheを再利用した場合に限り、同じproduction内の先行Runが実fileの所有元になり得ます。その場合もsource attempt chainを循環なしで終端まで辿り、各attemptのcache key、入力hash、artifact ID/path/bytes/SHA-256が同一であることを検証します。schema v2の固定`technical-qc-mp4-v2`（implementation `local-ffmpeg-qc-v2`）は、MP4 container、video/audio各1 stream、H.264/yuv420p、AAC 48 kHz stereo、container/video/audio各尺、期待尺、full decode、全編無音に加え、Integrated loudness -24.0〜-10.0 LUFS、true peak -1.0 dBFS以下、0.5秒以上の黒画面をhard checkします。`freezedetect`で1.0秒以上の長い静止区間を検出した場合は`media_facts.long_static.warning=true`のadvisoryとして記録しますが、technical verdictには影響させません。`technical-qc.json`、`ffprobe.json`、自己hash付き`manifest.json`をatomic publishします。解析完了とpass/fail verdictを分け、fail verdictでもjobは成功として証跡を残します。tool/process failureだけをattempt失敗にし、creative、rights、public release statusは変更しません。cache hit時もmasterを再解析してreport改変を検出します。
16. runの費用上限approvalとstage attempt/eventは追記記録で、以前の判断や試行を上書きしません。technical、creative、rights、public releaseは既存台帳の独立statusとして表示します。
17. audit exportはSQLiteの単一read transactionとsnapshot一致済みevent mirror prefixを固定し、対象production/runの記録を`outputs/studio/audits/`へZIP化します。JSON/JSONLと一般textは秘密情報をredactし、安全な構造化処理を保証できない設定・markup形式は理由付きで除外します。Studio生成のSRT/timing/manifest/ffprobe/technical QC JSONは含め、WAVとMP4は`include_media=true`のときだけ含めます。package manifest自身を除く格納entryごとの実bytes/SHA-256、scope別event chain tail、除外mirrorを記録し、ZIP閉鎖後にも全entryを検証します。ZIP全体のSHA-256は外部sidecarへ保存します。DB snapshotとartifact copyの間に元fileが変わった場合、ZIP実体には`archive_entries`のbytes/hashを使用します。SQLiteは既存tracked台帳を置き換えません。告知recipeのBase64は可逆で、一般の秘密情報redactionを保証しないため、保存前に秘密を除く必要があります。

`python -m tools.studio.cli test-video`は新しいmedia workerではなく、上記の既存service contractを順番に呼ぶcontrol-plane orchestratorです。workspace lockと索引更新の後、immutableな0円`local_sapi` Runを作成し、narration、単一登録済みvideo artifactのtimeline、assembly、QCをmain threadで直列queue／waitします。各terminal jobとattempt、cache利用、相対artifact path、bytes、SHA-256、technical verdictだけをbounded JSONへ集約します。失敗時は後続stageをqueueせず、QCは`analysis_status=succeeded`かつ`technical_verdict=pass`だけをCLI成功とします。外部provider、secret、課金gateはこのコマンドから呼びません。

`python -m tools.studio.cli quick-create <request.json>`もmedia workerを追加せず、既存Announcement Video→Detailed Test Videoのcontrol planeを共有します。256 KiB以下のexact schema v1 requestを読み、duplicate JSON key／非有限数／余分なfieldを拒否します。workspace lock取得後、索引更新、recipe CAS保存、exact revision実行、2秒間隔のterminal Job照合を1つのmonotonic timeout budgetで行います。成功projectionはproduction／recipe／Run／Job identity、4 childの成功／cache hit、master／QC artifactの相対path／bytes／SHA-256だけへ閉じ、recipe本文、絶対path、provider診断を出力しません。technical QC non-passは一般worker failureと別のexit code `3`です。

Studioの階層は次です。

```text
Production
  -> Studio control metadata
    -> Title / imported relative path -> SHA-256
  -> Artifact / Artifact version
  -> Event hash chain
  -> Announcement recipe
    -> Immutable exact version / parent / clone source
    -> Execution link -> Detailed top Job / Run / Revision
  -> Revision
    -> Run
      -> Requested stages / Cost approval history
      -> Local video request claim
        -> Run / cache key / payload digest / active job
      -> Provider task ledger
        -> Pre-issued provider task ID / encrypted resume payload
        -> Origin attempt / current recovery attempt + job
      -> Detailed test video claim
        -> Content-addressed request / immutable Run + Revision
        -> Active top job / same-run retry lineage
      -> Stage attempt
        -> Background Job ID
        -> Provider/result metadata / Artifact set
```

revisionとrunはimmutableに扱い、修正時は新しい識別子を作ります。各local stageは入力、tool identity、policy、成果物hashからcache keyを作り、成功attemptの成果物を再検証できた場合だけ再利用します。ComfyUIの生成結果はprompt hash、seed、固定workflow、model/runtime/tool identityを束ね、明示retryでは同じRunの試行履歴を保ちます。

`local_pipeline`はcanonical pipeline keyをDB claimとして使い、同一production・同一入力のRun/top jobを原子的にdedupeします。現行schema v8のcontinuation stateは`unavailable | active | waiting_provider | ready | continuing | succeeded | recovery_blocked | cancel_requested | cancelled`です。正規化済みrequestはDPAPI暗号文だけをclaimへ保存し、provider/video childの成功transactionがsource job/attemptをcheckpointします。親topがまだactiveならstateを進めず、親がinterruptedでproviderがterminal成功した場合だけ`ready`へ移します。単一のbackground coordinatorは`ready`を走査してCAS勝者の新topをenqueueするだけで、GPU laneやtop完了を待ちません。source checkpointがある新topはvideo stageをcache-onlyに固定し、同じRun／cache／pipeline lineageと物理artifact chainを再検証します。欠損・改ざん・lineage不一致では`pipeline_recovered_video_unavailable`として停止し、provider task作成、marker操作、新しい`POST /prompt`へfallbackしません。その後のSAPI、timeline、assembly、QCは通常stage cacheを使って続行します。親jobの明示cancelは登録済みchild jobとprocessの終了を待ってからterminalへ遷移し、後からprovider成功が到着してもclaimを`cancelled`へ閉じて暗号文を消去し、自動継続しません。一方、Studio通常終了のshutdown intentは実行中のComfyUI childへ伝播してlocal pollingだけを停止し、provider taskをcancelしません。top success／failureとclaim、provider terminal／video checkpointとclaimはそれぞれ同じSQLite transactionで確定します。requested stageのうち`captions`はnarrationから導出され、実workerはvideo_generation、narration、timeline、assembly、qcの5段です。MVPの詳しい操作と未実装境界は[STUDIO_MVP_JA.md](STUDIO_MVP_JA.md)に分離しています。

artifact復元は1件2 GiB、合計16 GiB、10,000件を上限とします。旧`artifact.created`がIDとkindしか持たず、成功済みstage/job resultにも完全metadataがない成果物は推測で復元しません。物理fileの欠落・改変・symlink・path逸脱・ID/path衝突も復元対象外です。これは検索索引の安全な復元であり、失われたfile自体を再生成する機能ではありません。

worker-backed stageの正常完了は、リンク済みjobとstage attemptの両rowおよび`stage.attempt.succeeded`／`job.succeeded` eventをSQLiteの同一transactionで確定します。ComfyUIではprovider taskと検証済み4 artifactのartifact row、version、`artifact.created` eventも同じtransactionへ含め、成功前にproduction-visibleにしません。artifact衝突、terminal commit失敗、通常のworker error、リンク不一致、provider lineage欠落、または原子的completion envelopeを返さないworker resultは、provider taskを含む同じfailure transactionで閉じます。providerが失敗済みならmarkerをfsyncしてからDBを確定し、callback後のDB永続化だけが失敗した場合はtaskを破棄せず復旧可能状態へ戻します。停止との境界では、完了transactionが先なら両方success、停止transactionが先ならjobは`interrupted`、stage attemptは`failed(process_interrupted)`となり、片側だけ成功する状態を許しません。Studioの通常終了はComfyUI生成をprovider側でcancelせずローカルpollだけを停止し、次回起動へ引き継ぎます。ユーザーの明示cancelではjob／attempt中断と`cancel_requested` fenceをatomicに確定し、同じUUIDへのGETと固定`POST /api/jobs/{prompt_id}/cancel`だけで再照合します。FFmpeg／ffprobe／PowerShell subprocessは従来どおり子process treeごと停止します。DBがbusyでもprocess停止を先行・並行し、全workerとSQLite interruption writerが終了したことを確認します。異常終了後の次回起動や、event mirrorからactive attemptだけを復元した場合も同じ終端状態と失敗eventを補い、永続的なrunning状態を残しません。`local_pipeline`のtop jobは、登録済みchild jobのcancel／join完了後にだけ自身をterminalへ確定し、video_generation、narration、timeline、assembly、qcの各artifactとjob／attemptを同じ原子的completion境界で公開します。現行schema v8では動画child成功とsource checkpoint、provider terminalとcancel／recovery state、top terminalとcontinuation stateも同じtransactionへ含め、event追記失敗時は全rowと暗号文消去をまとめてrollbackします。Detailed Test Video topは既存childのatomic stage契約を再利用し、成功resultを4 childのexact ID／attemptと物理再hash済みartifactへ限定します。告知recipeから呼ぶ場合は、新規または再利用するDetailed top Jobと`announcement.recipe.executed` linkをjob admissionの同じtransactionへ含め、execution eventの検証・追記が失敗すればJob作成もrollbackします。

queue投入と直後のDB補償が連続失敗した場合は、当該JobManagerが観測したexact top IDだけをcoordinatorが再試行します。worker dequeueとのlock handshakeにより「未投入jobを補償する」か「実workerへcontextと未完了eventの所有権を残す」かを一意に決め、別managerのqueued rowをprivate mapからorphanと推測しません。利用者cancelが補償と競合した場合は、active topまたはexactなterminal／`ready`世代を`cancelled`へ閉じて暗号文を消去し、shutdownの継続意図ではこの破棄経路を使いません。明示cancel intentはshutdownよりstickyで、DB確定までexact job IDをworker contextとは独立してprocess内に保持します。callerとworker双方のDB書込みが一時失敗してworkerが先に退役しても、通常稼働中のcoordinatorが保留IDを公平なbounded batchで再試行し、その間は`ready`世代の自動投入を停止します。ready一覧取得後もcontinuation topのDB CAS直前に同じJobManager lock内でfenceを再確認し、cancel公開との順序を一意にします。終了writerも同じfenceを先に永続化します。shutdown進行中に到着した明示cancelは当該closeを未完了にして次writerへ渡し、DB障害が続く場合もgeneric interruptionへ進まずworkspace lockを保持します。shutdown完了は同じmanager lock内で確定し、その後の新規破棄要求は拒否します。内部childのtimeout/errorによるretireはtopの利用者cancelとして扱わず、childを停止してからtopとclaimを原子的にfailureへ閉じます。

### Windows capture restart cleanup

再起動時のDB cleanup候補は、削除前に全件をpreflightします。job／attempt／Run lineage、status／error、payload、成果物登録のいずれかが曖昧なら、先に並んだ正常候補も含め1byteも削除せずStudio起動を止めます。`available=false`の成果物登録と同一targetの重複も曖昧なpublication truthとして保存し、operatorの調査を要求します。

## セキュリティと信頼境界

### Local secret boundary

- `.env` とAPI keyはGit管理外です。
- Studio CLIで登録するprovider secretは現在のWindowsユーザーへ紐づけたDPAPI暗号文として`outputs/studio/secrets/`へ保存し、平文をSQLite、ログ、Git、監査ZIPへ書きません。
- ComfyUI再開payloadと`local_pipeline`の完全な正規化requestは、用途別のDPAPI暗号文としてschema v8 SQLiteへ保存します。prompt／台本平文と暗号文はevent、job metadata、公開provider task／continuation projection、監査snapshotへ書かず、terminal成功または確定cancel時に消去します。DPAPIが使えない環境でも初回生成自体は可能ですが、continuation stateを`unavailable`または`recovery_blocked`へ止め、平文保存へfallbackしません。Detailed Test Videoは再開用台本暗号文を持たず、eventには本文ではなくsegment hash／文字数とclaim identityだけを残します。
- 告知動画は再調整と監査を優先する明示的な例外です。`announcement.recipe.saved` eventはrecipe名、大見出し、ナレーション、発音置換を含むexact canonical JSONをBase64で保持します。Base64は暗号化ではなく、SQLite、JSONL mirror、production detail API、監査exportから復号できるため、recipeへAPI key、token、password、秘密、公開不要の個人情報を入力しません。
- provider workerはprocess環境変数、workspace `.env`、DPAPI storeの順にsecretを解決し、値をUIへ返しません。ElevenLabs keyは費用gateとpayload確認を通ったcache missの実行直前だけ解決し、`xi-api-key` header以外へ入れません。
- YouTube OAuth credentialは`client_id`／`client_secret`／`refresh_token`のexact JSONとして同じsecret解決境界に置き、access tokenはprocess memoryだけで扱います。resumable session URIは公開state／Job／event／logと分離し、current-user DPAPI ciphertextへ保存します。DPAPI round-tripが使えなければsession開始前に停止し、平文へfallbackしません。
- `.env`拡張子、`.env.*`、credential/secret directory、private key形式はartifact索引から除外します。JSON/JSONLと一般text/logはbrowser配信時にも既知patternをredactします。設定・markup形式はfail closed、その他のactive documentはattachment + CSP sandboxで同一origin実行を防ぎます。redaction後も外部共有前の人による確認を信頼境界に含めます。
- Studio serverはworkspace hashから作るprocess-lifetime lockを保持し、同じworkspaceへの二重起動を拒否します。event mirrorへの追記はこのsingle-instance境界内で直列化します。
- event JSONL mirrorは全hash chainを検査し、破損時はhealth/UIをdegradedにして監査ZIPから除外します。他scopeのmirror追記は継続します。
- doctorはnetwork requestを行わず、key値を表示しません。
- error textにkeyが含まれてもredactします。
- `MINIMAX_API_BASE` はHTTPS必須です。例外は `localhost`、`127.0.0.1`、`[::1]` のHTTPだけです。

### Redirect / download boundary

Bearer付きAPI JSON requestは専用urllib openerで全HTTP redirectを拒否します。これにより、API endpointの誤設定や侵害による別originへのAuthorization転送を防ぎます。MP4 CDN downloadは別経路で、Authorizationを最初から付けません。download URLのredirectは認証情報を持たないため許可します。

ElevenLabs TTSも固定production HTTPS endpointへの`xi-api-key`付きPOSTで全redirectを拒否します。production URLの上書きは公開request contractに存在せず、内部test注入はliteral loopback originだけです。response body、MP3、alignment、WAV、metadata、総尺、HTTP／FFmpeg時間へ上限を設け、provider bodyや生HTTP errorを公開ログへ流しません。

YouTubeも固定Google OAuth token／channel／upload endpointだけを使用し、credential-bearing requestのredirectを拒否します。resumable session URLはGoogleの固定upload host／pathへ再検証し、token、refresh token、signed session URL、生provider errorを公開response、Job、event、auditへ含めません。

### Local service boundary

ComfyUIとStudioは `127.0.0.1` のみにlistenします。LAN公開、reverse proxyはこのarchitectureの範囲外です。Studioの読取GETはloopback bindとHost検査、変更系POSTはさらに起動ごとのsession tokenとOrigin検査を使い、`0.0.0.0`へ変更しません。認証拒否するPOSTはJSON上限内の宣言済みbodyだけを破棄してから接続を閉じ、Windowsの未読TCP dataによるresetを避けてHTTP 403を確定します。不正・過大bodyを無制限に読みません。StudioからComfyUIへのHTTPもliteral loopbackだけを許し、環境proxyとredirectを無効化します。`/system_stats`では`official_q4`の標準Dynamic VRAM launcherが作る完全なargvだけを許し、未知引数、Emergency、Turbo、precision／model path変更、ignoredな`extra_model_paths.yaml`を拒否します。固定API graph、送信prefixとhistory outputの一致も新POST／resume前後で検証します。ComfyUI本体が`custom_nodes/`をGit ignoreする境界はGit clean検査だけに依存せず、稼働processの起動引数を閉じ、Windowsでは4 modelのshare-deny handleを生成完了まで保持することで補います。

動画取込POSTだけはJSON parserを通さず、認証・Host・Origin検査後にraw bodyをstreamします。`Transfer-Encoding`を拒否し、decimal `Content-Length`を必須として1 byte〜2 GiBへ閉じます。canonical percent-encoded UTF-8 filename、拡張子、MIMEを照合し、`application/octet-stream`は既知拡張子と後段ffprobeを条件に許可します。path separator、drive separator、control文字、dot name、Windows予約名、末尾dot／spaceを拒否し、公開先名をsanitiseします。未消費bodyを持つ失敗responseはconnectionを閉じ、後続requestとして再解釈しません。partial、metadata、destinationの全pathはworkspace内非symlinkを再検査し、同一processのintake lockとworkspace単一起動lockを合わせてatomic metadata truthを守ります。

### Supply-chain boundary

setup/downloaderはGitHub、PyTorch index、PyPI、npm、Hugging Faceからcode/binary/modelを取得します。Git SHA、Pythonのexact package version、frontend lock file、HF revision、file size/hashでdriftを抑えます。StudioのRemotion関連5 packageは同じ`4.0.517`へexact pinし、Playwrightとともに実`node_modules`依存closureのsetup-time attestation、通常doctor、render前後の照合、tool identityへ含めます。自動更新は行わず、更新時は`npm ci`とsetupを再実行し、lock file、attestation、composition、renderer、Player previewの互換性を再確認します。Turbo nodeの同梱time-conditioning gridはdoctorが固定SHA-256も検査しますが、外部artifact自体の安全性を証明するものではありません。

### Data boundary

- local workflow: prompt/mediaはloopback process内。依存取得時のnetwork accessは別途発生。
- API workflow: promptとmediaはMiniMaxへ送信。callbackを使えば指定serverにもtask情報が送信される。
- Studio MVP: production recordとartifact metadataはloopback内。`local_sapi`は本文をWindows System.Speech processへJSON file経由で渡し、`local_comfyui`はpromptとseedを同じworkspaceのattestation済みComfyUIへ渡します。`local_pipeline`も固定されたlocal-only routeでComfyUIとSAPIを使い、ElevenLabs、MiniMax API、費用承認へ到達しません。Detailed Test Videoは登録済みmediaとlocal SAPI／Remotion／FFmpegだけを使い、H3／ComfyUIと全外部providerへ到達しません。raw prompt/scriptはSQLite、event、job metadataへ平文複製せず、prompt hash、文字数、seed decimal、stage lineageと安全なcontinuation stateだけを公開記録します。詳細一括のjob／eventもsegment本文やoverlay本文を複製せず、hash／文字数とartifact／tool identityを記録します。ただし告知recipeだけは、保存・複製・再調整するproduct recordとしてexact JSONをBase64 eventへ明示保存します。これは暗号化ではありません。自動継続用の完全な正規化requestは現在のWindowsユーザー用DPAPI暗号文としてprivate DB accessorだけが読み、cache-only video checkpointの検証後に同じRunへ新topを投入します。ただし、明示的に生成する`workflow.json`、`timings`、`remotion-timeline.json`、`manifest`などのartifactにもcontentが含まれ得るため、監査exportや共有前に確認します。費用承認済み`elevenlabs_tts`を明示実行した場合だけ本文、voice、固定model/output、voice settings、seedをElevenLabsへ送ります。API key、生response、USD実費の推測は保存しません。返却MP3とalignmentはローカルでWAV/SRT/timing/manifestへ変換します。FFmpeg timeline／assembly／technical QCとRemotion詳細timelineは登録済みmediaだけをローカルworkerへ渡し、Remotion requestから任意path、URL、React component、CSS、font、browser flag、environment variable、free-form propsを受け付けません。SQLite、DPAPI暗号文、外部送信marker、監査ZIP、生成MP4/workflow/ffprobe/manifest、WAV/SRT/timing/manifest、両timeline preview、Remotion render report、clean/captioned MP4、technical QC JSONはignored `outputs/studio/`へ保存します。
- Delivery Packageは上記ローカル成果物と監査snapshotをZIPへcopyするだけで外部送信しません。YouTube previewだけはtitle／description／tags等とOAuth tokenをGoogleへ送りchannel identityを照合し、executeの2確認後は選択master bytesとmetadataをYouTubeへ送ります。Job payloadは本文metadata、token、session URLを保持せずhash／channel／privacy／確認済みbooleanだけを持ち、公開ledgerもdigestと進捗だけです。
- output: 著作権、肖像、privacy、適法性はoperatorが判断する。

ライセンス境界は[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)に分離しています。

Remotionは個人利用を前提に導入しています。利用主体、組織規模、用途、配布形態が変わる場合は、実行や成果物公開の前に現行のRemotion license条件を再確認します。

## 容量と制約

RemotionのPNG中間frameは、非並列encode時に最大60秒分が一時領域へ置かれ得ます。workerは開始前に、全frameのRGBA bytesへ1.25倍のPNG headroomを加え、raw出力2GiB、正規化出力2GiB、安全余白1GiBと、`preserve_v1`の実source bytesまたはsharpカットごとの最大2GiBを足した必要量を同じvolumeの空き容量と比較します。source staging後には実staged bytesを計測し、残容量をframe／出力／余白分へ再照合します。いずれかが不足すれば`insufficient_scratch_space`でNode起動前に停止します。Node／Chromiumへ渡す`TEMP`／`TMP`／`TMPDIR`は既存の大小文字aliasを除去してatomic stageの`work/scratch`へ上書きし、Node側でも3値、実効tmp、空directory、symlinkなしをbundling前にattestします。成功・失敗・cancelの全終了経路でstageごと削除し、Windowsの一時lockにはread-only属性解除と0.15／0.30／0.60秒のbounded retryを行います。それでも残る場合は黙殺せず`remotion_stage_cleanup_failed`でJobを失敗させます。`png-frame-scratch-v1`の計算値、実staged bytes、両検査の空き容量／判定、Node attestationはrender reportとmanifestへ保存し、固定policyはcache identityへ含めます。

| 項目 | lowvram / Turbo profiles | official / API |
|---|---|---|
| model artifact合計 | base 23,203,877,000 bytes（約21.61GiB）/ Q2 Turbo 23,983,726,816 bytes（約22.34GiB）/ Q4 Turbo選択profile 30,072,736,544 bytes（約28.01GiB）/ Q2+Q4累積unique 38,560,704,704 bytes（約35.91GiB） | official 42,470,585,471 bytes（約39.55GiB）/ official Q4 41,360,420,808 bytes（約38.52GiB）/ official Q4 Turbo 42,140,270,624 bytes（約39.25GiB） |
| 同梱workflow | base: 608x352、4秒、20 steps / Q2 Turbo: 608x352、5秒、simple / 6 steps / Q4 Turbo: 864x480、5秒、simple / 8 steps。Turboはmerge | official templateはComfyUI package。official Q4: 864x480、5秒、stock 20 stepsまたはTurbo simple / 8 steps。APIは768P/2K、4〜15秒 |
| local出力上限の位置付け | H3-Base nativeは短辺768px | 2K/Context-IR/RegenerateはAPI |
| VRAM | 8GiB totalをlocal gate。空き4GiB未満はwarning | officialはさらに高いmemory圧力。成功保証なし |
| RAM | 32GiB totalをlocal gate。available 12GiB未満はwarning | offload時はRAM/pagefile負荷増大 |
| disk | missing models + 2GiB未満はerror。取得後2〜20GiBはwarning | model以外にoutput/temp余裕が必要 |

Remotion詳細timelineはStudioの短尺縦動画向けに、登録済み動画1〜16件、出力最大60秒、1080×1920／24fps、render concurrency 1へ固定しています。素材1件2 GiB、入力合計4 GiB、出力2 GiBのworker上限があり、Playwright画面収録と同じbrowser FIFO laneを使うため、両jobは並列実行されません。これは処理時間や必要disk容量の保証ではありません。

APIの入力制約は、request body 64MB以下、画像/動画/音声ごとのsize/count、video/audio durationを含みます。CLIは主要なrole/count/mode/ratioをpreflightしますが、codec、画素寸法、実durationなどすべてをローカル解析するわけではありません。最終contractは
[V2 Create content仕様](https://platform.minimax.io/docs/api-reference/video-generation-v2-create#content)です。

## 検証済み範囲

2026-08-14までの確定結果:

- lowvram_turbo 5モデル: exact bytes + full SHA-256一致（LoRAは779,849,816 bytes）
- lowvram_q4_turbo 5モデル: exact bytes + full SHA-256一致（Q4 encoderは14,576,977,888 bytes）と専用workflow contract一致
- local doctor: `Ready: yes`、`Locked core runtime matches: yes`。free VRAM逼迫はwarning
- ComfyUI/ComfyUI-GGUF/Turbo nodeの3 locked HEAD、VAE chunked I/O、Turbo grid SHA-256、4 nodeの`object_info`登録を確認
- 自動テスト: 43/43合格（VAE/Turbo/Q4/official INT8のloader・配線・override・解像度・sampling・decode contract、16:9/multiple、manifest/license identity/workflow wiring、missing-object fetch、system metricsを含む）
- 1-step Emergency E2E配線スモーク: H.264 video + AAC stereo audio MP4生成成功
- Turbo Q3 merge 4-step E2E: Dynamic VRAM、416x256、4秒指定、70.35秒でH.264 + AAC MP4生成。LoRAなし同seed A/Bとの差（平均PSNR 24.06 dB）を確認
- Q2 Turboの0.4MP / 5秒 / simple 8-step job 00010が成功。Q4 workflowはこの設定を基準にencoderだけを置換
- Q4 Turboの同prompt/seed 0.4MP / 5秒 / simple 8-step A/Bが286.087秒で成功し、H.264 864x480 + AAC stereoを生成。Q2とのPSNR 26.291812 dB / SSIM 0.814451で出力差を確認
- official_q4 INT8 + Q4、Turboなし、Emergency `--novram --cpu-vae`の416x256 / 5 frames / 1-step / audioなしsmokeが324.814秒で成功。H.264 High / yuv420p MP4の全decode成功、OOM/illegal accessなし。詳細は[検証記録](verification/int8-smoke-2026-08-13.json)
- official_q4 INT8 + Q4、Turboなし、同じEmergency条件で1056x608（0.6MP）/ 5秒 / `res_multistep`・`simple` 20 stepsが3時間31分14.964秒で成功。H.264 High / yuv420p + AAC LC 32kHz stereoの全decode成功。同prompt/seedの1例ではINT8は低ノイズ・安定した窓グリッド、Q3はより細かなtextureという観察であり、一般的な品質優越は示さない。詳細は[検証記録](verification/int8-quality-2026-08-14.json)

2026-08-23のStudio MVP確定結果:

- `setup-studio.ps1`: backend import、Vite 8に合うNode.js 20.19+の20系または22.12+ gate、`npm ci`、TypeScript / Vite production buildが成功
- `run-studio.ps1`: 通常modeの静的UI / healthと停止、Dev modeのVite proxy経由GET / session-protected POSTと停止を確認
- 実制作データ: 3 production / 3,513 available artifactを索引し、safe-format/media除外監査ZIPの10 entryを閉鎖後再読込してbytes/SHA-256一致、ZIP sidecar一致、mirror除外0件を確認
- Studio backend自動テスト: 25/25合格（従来のartifact配信、redaction、audit snapshot、event mirror、課金・approval・immutable recordに加え、`local_sapi` profile、HTTP実行、attempt/cache、job永続リンク、cache改変・metadata改変時の再生成、不正worker metadataの登録前拒否、再起動時active attemptの失敗確定、v1/v2→v3 SQLite移行、attempt/job linkのevent mirror復元を含む）
- Studio narration自動テスト: 5/5合格（WAV連結とframe基準timing、SRT/manifest/hash、発音置換、cache hit、artifact改変時の再生成、入力上限、巨大・長時間WAVの拒否を含む）
- Studio frontend契約テスト: 4/4合格（status分類、job/run正規化、duration変換、ナレーション入力の空行除去と上限を含む）
- repository Python自動テスト: 73/73合格（既存43件 + Studio backend 25件 + narration 5件）
- Windows SAPI実機確認: 日本語2 segmentを`Microsoft Haruka Desktop`で8.251秒のWAVへ生成し、WAV/SRT/timing/manifestの整合、2回目のcache hit、queue投入前のStudio job↔attempt永続リンク、artifact登録→監査ZIPまでのE2Eを確認

2026-08-24のStudio local assembly／technical QC／停止制御確定結果:

- repository Python自動テスト: 142/142合格（既存runtime/API 43件、Studio backend 40件、narration 9件、assembly 19件、technical QC 23件、job/shutdown 8件）
- Studio assembly／QC実FFmpegテスト: 42/42合格。clean/captioned、字幕焼き込み、cache改変、tool binary置換、各stream尺、full decode、短尺を含む全編無音、diagnostics上限、reader failure、timeout/cancel時のprocess tree停止を含む
- shutdown境界: process登録とcancelの競合、DB busy中のkill先行、Windows `taskkill`非0 fallback、psutil process消滅競合、callback開始境界、job/stageのatomic terminal transactionを回帰確認
- Studio frontend契約テスト: 12/12合格、production build成功、npm audit 0件
- 実サービスE2E: 一時workspaceの5秒MP4を索引し、実Windows SAPI 2.377秒→clean/captioned local assembly→technical QC 10項目pass→2回目QC cache hit→mediaなし監査ZIPまで成功。masterはH.264 / yuv420p + AAC 48 kHz stereo、5.000秒で、narration／assembly／QC 2試行のstageとjobはすべてsucceeded

2026-08-24のStudio local timeline／artifact復元確定結果:

- repository Python自動テスト: 163/163合格（既存runtime/API 43件、assembly 19件、Studio backend 47件、job/shutdown 9件、narration 9件、technical QC 23件、timeline 13件）
- Studio frontend契約テスト: 18/18合格、production build成功、npm audit 0件。空欄／非数値時刻、終了時刻の絶対上限、exact snake_case payload、clip操作、job選択を含む
- timeline実FFmpegテスト: 13/13合格。3素材のhard cut、video-only固定出力、cache改変・余分file・tool identity・unsafe cache key・cancel・fixed argv・bounded diagnosticsに加え、50ms×32カットの24fps累積丸め、赤・緑・青の50ms境界での順序と終端保持、1秒×2カットの各24frame保持を検証する回帰を含む
- 実サービスE2E: 3本の2秒sourceから各1.5秒を切り出した4.500秒timeline→実Windows SAPI 1.644秒→clean/captioned assembly→technical QC 10/10 pass→2回目timeline cache hit→mediaなし監査ZIPまで成功。timeline 2試行、narration、assembly、QCの全job／attemptがsucceeded
- SQLite再構築: 成功済みnarrationの4 artifactをevent mirrorと物理fileのbytes／SHA-256一致から復元。byte数を維持したhash改変artifactは復元せず、完全metadataのない旧`artifact.created`も安全にskipすることを確認

2026-08-24のStudio ElevenLabs external TTS確定結果:

- repository Python自動テスト: 184/184合格。外部TTS contract／adapter／費用gate／HTTP route／mock E2Eの18件、secret解決の3件を含む
- Studio frontend契約テスト: 27/27合格。固定modelとexact snake_case payload、literal課金確認、profile／工程／見積／approval gate、provider metadata、`actual_cost=null`表示、Assembly／QC導線を含む。production build成功、npm audit 0件
- mock provider E2E: `elevenlabs_tts` Run作成→正のUSD見積→上限approval→job／attempt成功→WAV/SRT/timing/manifestの4 artifact登録→同一payloadの2回目cache hit→ローカルassembly入力検証まで成功。2回目はsecret解決とprovider callを再実行せず、初回だけの1 callであることを確認
- 安全境界: approval前はexternal contract／secretへ到達しない、固定production HTTPS endpoint、redirect拒否、loopback限定test注入、応答size／総deadline、5xx／timeoutの曖昧送信停止、production/cache markerによる別Run再送防止、API key／本文のDB audit summary非保存を回帰確認
- 実ElevenLabs credentialを使うpaid smokeは意図的に実施していない。実際の日本語音質、provider account上の請求、USD実費照合は未確定

2026-08-24のStudio `test-video` CLI確定結果:

- repository Python自動テスト: 199/199合格。one-command orchestrationとCLIの15件で、工程順序、attempt引渡し、timeout／失敗時の後続停止、source変更拒否、QC fail、workspace lock、cleanup、中断、secret／path非漏洩を追加確認
- Studio frontend契約テスト: 27/27合格、production build成功、npm audit 0件
- 実制作E2E: `SHORT_20260823_claude_md_15s`の登録済み15秒clean masterを入力に、実Windows SAPI 11.104秒、1カットtimeline、captioned assembly、technical QCを1コマンドで完走。初回86.315秒、全4 job／attempt成功、QC 10/10 pass
- 完成master: `outputs/studio/runs/run_b6892f69bb6b40c8b1b1cca0edcadd9d/assembly/64AF016E65AFBCFCACDA5BE93AE0E923C721437E8B900403B0E1B1439B0ABCDF/master-captioned.mp4`、4,524,600 bytes、SHA-256 `3A4A4EDB170F2A1D826231772BD56D1F998B7B31A1DA03C6D8C6A898C1F4A92E`。1080x1920／24fps／15.000秒、H.264／yuv420p + AAC 48kHz stereo、full decode／非無音を確認
- 同一recipeの2回目は11.893秒。narration、timeline、assemblyはhash検証済みcacheを再利用し、QCは新しいassembly attemptのmasterを再解析してpass。外部通信、API key、課金処理は未使用

2026-08-25のStudio local ComfyUI／Shorts字幕preset確定結果:

- repository Python自動テスト: 247件実行、246件合格＋non-Windows専用race test 1件をWindowsでskip。内訳はruntime/API 43件、Studio backend 57件、ComfyUI contract/adapter 30件（platform skip 1件を含む）、assembly 23件、job/GPU lane/shutdown 13件、narration 9件、technical QC 23件、timeline 13件、external TTS 18件、secret 3件、test-video/CLI 15件
- Studio frontend契約テスト: 30/30合格、production build成功、npm audit 0件。固定workflowのexact body、0〜2^63−1 seedのlossless request/response、multiline prompt、再読込metadata、active jobの重複送信抑止を含む
- ComfyUI worker: 固定API graph、GPU worker内でのcache key再束縛、4 model／2 lock file／3 repositoryの来歴、完全なcanonical argv、`extra_model_paths.yaml`拒否、Windowsの毎POST full-hash＋share-deny handle、proxy無効、redirect拒否、送信prefixへの出力束縛、marker-linked resume、production-wide cache lineage、manifest/ffprobe/artifact検証を回帰確認
- GPU lane: ComfyUI jobを1 workerでFIFO直列化し、default laneと並行できること、両laneの停止／中断、無効laneの永続化前拒否を確認
- terminal transaction: ComfyUIの4 artifact row/version/eventとjob/stage successを同一transactionで確定し、通常worker error、リンク不一致、completion envelope欠落／不一致、強制rollback時にもartifact露出や片側runningを残さないことを確認
- Shorts字幕: `studio_default_v1`互換既定と`shorts_ja_large_v1`をcache／manifest／public resultへ含め、任意ASS/font/filter入力を拒否するcontractと実FFmpeg経路を確認。font familyは固定するが、OS側font binary自体はまだhash固定していない
- 実稼働ComfyUIへのread-only照合ではComfyUI 0.31.0、PyTorch 2.13.0+cu130、Python 3.12、`127.0.0.1:8188`、workspace内main/output、3 repository HEAD/clean一致を確認した。ただし現在のlistenerは安全引数導入前に起動され、完全なcanonical argvを満たさないため`invalid_comfyui_runtime`として意図どおり拒否された。生成POSTと実GPU完走はこの変更の受入では行っていない

M5／M6の新しい自動回帰は、Delivery ZIPの13 entry＋外部SHA-256 sidecar、入力改変とQC不合格の拒否、voice-upgradeのHOOK／MESSAGE／CTA配置、exact source binding、atomic stage／artifact登録、登録済み結果のassembly入力再検証とscene overlap拒否、Windows受入閾値と5 operator attest、YouTubeのDelivery／3 human gate／channel binding、public拒否、2段階確認、resumable offset、DPAPI session、credential-bearing redirect拒否、曖昧状態の再初期化拒否を対象にします。これはローカル契約とfake transportの検証範囲です。実Google OAuth／YouTube API、実upload、外部公開、請求、Windows実機受入の成功を示すものではありません。

未確定:

- tracked 20-step low-VRAM workflowの完走、品質、所要時間
- tracked Turbo既定の0.2MP / 5秒 / 6-step完走、品質、再現性とbypass経路
- Q4の一般的な品質・速度優越、複数promptでの比較、`lowvram_q4_turbo` の0.6MPへの段階的拡張
- official profileに残るNVFP4 AWQ text encoder（15,687,142,551 bytes）の導入と実生成
- official_q4 tracked 0.4MP / 5秒 / 20-step既定、official_q4_turbo、複数promptでの品質・prompt追従・時間的一貫性の比較
- 768p/2Kのこのマシンでの性能
- community量子化と公式ウェイトの品質比較
- 実ElevenLabs credentialを使う人承認付きpaid smokeとprovider請求情報とのUSD実費照合、voice upgradeのStudio UIと既存告知／Deliveryへの自動接続、Windowsネイティブ収録acceptanceの全閾値と5 operator attestを満たす実機証跡、実Google OAuth credentialでのchannel preview／privateまたはunlisted upload／YouTube側read-back、Studioの公開操作UI、実ComfyUI taskをStudio強制終了後に回収して同じpipelineを完走する復旧E2E
- 実ComfyUIを動かしたStudio process強制終了→再起動→同一task回収のGPU E2E、ComfyUI自体が再起動してtaskを失った場合の人による判断UI、旧schema由来のIDなしmarkerの手動解決

## Windowsネイティブ収録の実機検証状態

2026-08-30に、正式な単回consent routeと実装`windows-native-primary-display-loopback-v4`で6秒のprimary display＋default render loopbackを収録しました。job `job_514c37d437874a39a8802c032e5bdb02`が成功し、8成果物、full decode、fresh ffprobe、288,000 PCM frame、video/audio start 0ms、構造timingを確認しました。成果物は`outputs/studio/runs/run_a52191aa20d748098a814946639be41c/screen_capture/044534001E8E081C036BD74C6F046B3CA8960E1F61740B591CC46971F2EF0444/`です。実機で判明した先頭WASAPI transition discontinuity、loopback先頭device position、Matroska PCM duration丸め、raw PCMへのwallclock PTS強制、`.png.partial`のcodec推論を、QPC基準padding、exact packet bytes、audio PTS 0、明示PNG codecへ修正しました。

既知の同期markerでは音開始が映像開始より約27〜111ms遅れ、endpoint音量も低めだったため、これは機能完走の証拠であって公開品質のA/V同期証明ではありません。automation pointer overlayが収録されたためcursor非表示もこの試験では判定せず、device切替と親強制終了も未確認です。`content_sync_verified=false`と公開gateは維持します。

## Source Fidelity v2の15秒実レンダー検証

2026-08-29に、480×864の既存H3実写系素材3本を各5秒、全カット`h3_low_res_sharp_v1`、日本語テロップ3件で処理する実Remotion試験を最終コードで行いました。360 frame／15.000秒を131.891秒で完走し、1080×1920／24fps、H.264 High／yuv420p＋AAC-LC 48kHz stereo、9,360,318 bytes、SHA-256 `C61E4376FE4F5F546BA360FC897DD65010CB2C76FF7C014BBBA3727C5D6ECC66`のMP4を生成しました。独立ffprobe、video／audio全decode、Node scratch containment attestation、終了後temporary stage 0件を確認しています。開始前必要量15,543,640,064 bytes／空き459,701,411,840 bytes、staging後必要量9,101,189,120 bytes／空き459,691,950,080 bytesで両方passし、現行validatorによる5成果物の完全再検証も`cache_hit=true`で成功しました。成果物は`outputs/studio/runs/run_source_fidelity_15s_v2/remotion_timeline/FC152CB19676FC698114F3B2AF8076FCD56C5933E508D4DCAC51B2D47FB2A018/`です。最大60秒は実レンダー未検証で、1,440 frameの計算境界とfail-closed testまでが現時点の証拠範囲です。

## 現行local_pipeline検証状態

2026-08-25 root最終検証では、Python全344件を実行して343件合格＋non-Windows専用race test 1件をWindowsでskipし、frontend 42/42、production buildも成功しました。fake-backed統合で`local_pipeline` request schema v4（SQLite schema v6）、`POST /api/productions/{production_id}/execute-local-pipeline`、専用pipeline lane、6 requested／5 executed stage、DB-level dedupe、same-run retry、parent-child cancellation wait、外部TTS非到達、atomic artifact確定、QC pass、Studio UIの2秒pollingを確認しました。自動継続回帰では、Studio再起動後のprovider成功から同じRunへ新topを一度だけ投入し、8件の同時再送をdedupeすること、source job/attemptを固定したcache-only動画再利用、cache欠損・改ざん・lineage不一致でprovider task／marker／ComfyUI `POST /prompt`へ進まないこと、明示cancel後は継続しないこと、暗号文改ざん、queue投入＋補償の二重失敗、enqueue後例外、worker退役中のDB一時障害、ready CAS、shutdown中のlate cancel競合を安全側に処理することを確認しました。終了・復旧回帰では、atomic `cancel_requested`、未送信／running／404／terminalの同一UUID再照合、解析済みHTTP handlerのdrain、未解析partial requestの有界遮断、`Connection: close`、終了しないworker時のworkspace lock保持と再試行、worker lane／SQLite interruption writerを残りshutdown deadline内でdrainし、期限超過時はlockを保持することを確認しました。成功topの再利用時は5 childのexact lineageと、captioned既定では全19件（clean-onlyでは18件）のartifactをDB metadata・物理bytes・SHA-256で再検証し、最終または中間artifactの欠損／改変／I/O raceを同じRunの新top jobで自己修復します。この検証ではComfyUIへ新規promptをPOSTしていないため、実GPU一括完走時間、強制終了→再起動→同一task回収からpipeline完走までの実機E2E、完成映像の目視品質は未確認です。

2026-08-26には、公式INT8 ConvRot＋Q4 text encoderの固定`official_q4`経路で実GPU `local_pipeline`を完走しました。H3 rawは480×864／24fps／124 frames／5.167秒、H.264＋AAC 32kHz stereoで、H3生成7分06秒、一括pipeline全体7分24秒でした。Windows SAPI、one-clip timeline、captioned assembly、technical QCまで同じRunのartifact／job／attemptとして残り、外部API keyと課金は未使用です。これは通常完走の実機証拠であり、Studio強制終了→再起動→同一ComfyUI task回収の実機E2Eや一般的なcreative品質を保証しません。

## 告知UIの曖昧応答と別tab同期境界

告知実行が2回目も曖昧な場合、「自動処理停止」は追加POSTと同じ候補へのexact Job GETを止めることを意味します。Jobとproduction detailのbounded pollingは継続し、後からfreshなexact execution linkが現れた場合だけ再POSTなしで復旧します。idle時のproduction detail background pollingは行わず、別tabの新revisionは手動再読込または実行／曖昧応答中のdetail再取得後に検出します。cleanかつidleなら最新版を読み込み、dirty／busyなら内容を上書きせず保存・実行を止めます。複製intent用`localStorage`をruntime検証できない場合は、安全なclone IDを保持できないため告知フォーム全体を明示破棄または環境復旧までfail closedにします。

## Playwright画面収録の検証状態

2026-08-25にPlaywright `1.62.1`／Chromium `151.0.7922.34`で実Web収録E2Eを行いました。Studio自身の`http://127.0.0.1:8765/`を描画待ち500ms、1秒時点の720px scroll、指定尺3秒で収録し、job `job_1decf170bbc341f49ff1b4f3e423819b`／attempt `attempt_7e150e65276d4471a42847f4fa100f7b`が成功しました。最終MP4は1080×1920、24fps、H.264／yuv420p、video-only、3.000秒でfull decodeとfresh ffprobeを通過し、MP4 389,197 bytes、生WebM 762,325 bytes、始点／終点PNG、sanitized report、ffprobe、manifestの7 artifactを`outputs/studio/runs/run_cbaa1ead33fb4d02be586dcc48cc75be/screen_capture/4021F9F3CA5A228EC8F22456234A9C80853AAA85277B9525CC85ED9C8DF1B73E/`へ登録しました。始点／終点画像を目視し、縦viewportとscroll差分も確認しています。その収録MP4をartifact `art_000a10a0154c74149153d57e0190524b`として同じRunのtimelineへ渡し、job `job_47286fd1eef8480f86e4520289632ac7`／attempt `attempt_6a0bb3b50d934d55bc9336837eebd43a`も成功しました。3.000秒の`timeline-preview.mp4`（362,527 bytes、SHA-256 `17B9FD76E1170BB88A2EC64E66ACA88FF75F0FFD777596E8FA6E4273E5B6B25C`）と3文書を`outputs/studio/runs/run_cbaa1ead33fb4d02be586dcc48cc75be/timeline/F45A9955F5A7AA8FCD4F1A2B3241E4FA1166470015C15A732C661AD9110982BB/`へatomic登録し、画面収録からカット編集までの実素材連携を確認しました。実Playwright回帰テストでは別loopback portへのsubrequest遮断、絶対path／raw URL token非漏洩、output policy改ざん拒否、publish後のcancel／検証失敗cleanup、収録・変換・検証のprogress通知も確認しています。Python全359件は358件合格＋Windows上のnon-Windows専用1件skipを確認し、その後追加したbrowser lane実行中progress可視性、DB atomic commit失敗cleanup、publish後cancel cleanupの3件も個別合格しました。関連するbackend／実ブラウザ統合123件も再実行して全件合格しています。frontend 50/50、production build、`setup-studio.ps1 -SkipBuild -SkipBrowserInstall`のbrowser doctorも成功しました。最新版serverでの再受入ではjob `job_be88c3cb938e4166aef35eb8a873ea83`が`preflight`→`recording`→`transcoding`→`verification`→`publishing`→`registration`→100%完了をAPIへ返し、7成果物を登録しました。

Run契約修正後の再受入では、run `run_c0745a922f814b67b1c45f7fbac8fd80`が`requested_stages=[screen_capture,timeline]`、rerun planの`affected_stages=[screen_capture,timeline,assembly,qc]`を返しました。同Runのjob `job_66c8ae62688044a59cb3ca0a14207aec`も2.000秒、1080×1920、24fps、H.264、video-onlyのMP4と7 artifactを登録し、manifestに絶対pathを残していません。

この受入はWeb viewport収録の証拠です。Windowsデスクトップ／ネイティブアプリ、system audio、microphone、既存ログインsession、外部Webサイト、複数page／popup、30秒超の収録は対象外です。収録MP4は既存timelineのvideo artifact候補として利用できますが、screen captureだけのRunでnarration／assemblyまで自動完走することは保証しません。


## 2026-10-23 編集改訂

Docs共同編集とdots先回り提案・実行前判断の案件用改訂を `productions/SERIES_20261023_editorial_revision/` に分離した。既存のStudio音声・レンダリング処理を再利用し、詳しい構成と検証範囲は同フォルダーのARCHITECTURE.mdに記録する。動画・音声・非公開共有URLはGitHubに保管しない。
