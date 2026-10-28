# Claude 資料作成シリーズのアーキテクチャ

## 責務

本フォルダーは5本の30秒動画だけを所有する制作層です。`produce.py`がdots finaleドライバーを独立したPython名前空間へ読み込み、Claude用ID、入力フォルダー、出典検査、保存済み動画の保持、納品名を差し替えます。dotsのソース・原稿・音声・状態を編集しません。実描画・音声処理は既存の共通実装を再利用します。

`build_story_drafts.py`は事実を伴う撮影台本と、確認済みcapture proof・MiniMax動画から新しい草稿を作ります。欠損素材を仮の公式画面で補わず、未取得状態を明示します。公式の一般説明、こちらの架空業務の実出力、番組用の生成人物を別のprovenanceとして保持します。

## 証拠と画像

原本は`outputs/evidence/claude-work-20261022/_private/`、公式引用は`official/`、公開用実演cropは`demonstration/`、実ファイルは`exports/`です。PNGの矩形切り出しは元座標、原本・meta・cropのSHA-256、日時、製品、phase、架空素材のみ・個人情報除外の宣言で束ねます。画素の再描画やAI編集は行いません。古いJPEG原本は残し、PNG変換時も復号画素一致を記録します。

公開画像の検査と完成動画の検査は別です。`capture_review_passed`は読みやすさ・プライバシーのAI支援チェックで、親による最終構成確認やユーザー採用を意味しません。`render_review_frames.mjs`は仮の時間配分で静止画を作るだけです。字幕と台詞は連結一致を検査し、発話時刻は実音声生成後に決定します。

実DOCX/PPTXは読み取り専用でZIP CRCとXMLを調べます。数値・未定事項・書体指定の検査結果と、実アプリで開いた画面の証拠を分けます。PPTXのsource file hashを外部ビューアのcrop proofにも記録し、別ファイルの外観と取り違えないようにします。

## 人物素材と音声

人物動画は`outputs/characters/explainer-motion-20261022/claude-shiori/verification.json`を使います。provider、生成成功、目視状態、動画hash、元人物PNGのpath、I2VAキー画像のhashを検査します。ComfyUI runtimeへ置いたキー画像のコピーは、レビューしたoffice keyframeとhashが一致する場合だけ許可します。冒頭と締めに本物の生成MP4を配置し、素材内の音声はミュートします。

人物はMP4を全面に配置し、顔を避けた下部のテロップで説明します。共通`prepare`が実probeから`mediaDurationInFrames`と`mediaPlayFrames`を決め、editorial場面で素材が先に終わる場合は背景とまとめへ切り替えます。素材のループ・静止延長・音声の再生成は行いません。他の場面種別の厳密な媒体尺検査は維持します。

`preflight`は公式引用、実演baseline（beforeまたはfirst-output）、後段の実演（revision/after/export）、新人物動画を要求します。初回履歴を比較前の証拠に使える一方、afterだけの画像群は比較として受け付けません。

有料処理は`generate`に限定します。台本全体hashを開始時に固定し、Aoede/モデル/場面別テキスト/音声hashを検証してキャッシュを再利用します。22秒の共通cadenceと排他ロックで同時送信を防ぎます。未完了やunknownの送信は停止し、履歴を消して黙って再送しません。明確なinvalid-key拒否の明示的置換は`rejected-attempts.json`へ元request/submissionのhashを保存し、検証済み件数と拒否件数を別集計します。キーの値はproofや成果物へ保存しません。

## 状態と納品

各`NN/`が固定入力・state・deliveryを持ち、`outputs/productions/SHORT_20261022_claude_NN_work/`へ音声世代と描画世代を保存します。`prepare`が実発話長から720フレームへ構成、`render`がRemotion描画と音声合成・全デコード検査、`review`が実画面を確認した記録、`package`が10メンバーZIPと全hash/CRCを作ります。生成中の回と同じstateを並行更新しません。全体の描画枠は1本ずつです。

`refresh-prepare`は旧state、旧出力全ファイルのhash、元台本と音声sourceを`renderer-revisions/`へ保管したうえで別の描画世代を作ります。旧出力は変更せず、元台本hashとキャッシュ済み音声を再検証します。`render_prepared_review.mjs`はそのpropsと素材を別の確認用フォルダーへコピーして、実時間配分の人物画面と素材終端を検査します。`render`の失敗時は専用の`render-*.log`に診断を残し、黙って描画や有料要求を再試行しません。

既存dots納品物は生成開始時にhashを固定し、変更がないことを検査します。プライベート原本・APIの履歴・アカウントURLは公開ZIPから除外します。最終試聴、ユーザー承認、YouTube公開、S3共有は別々の状態であり、本ドライバーはYouTube投稿を行いません。

独立の`finalize.py`は全5本の`packaged`状態を前提に、現ファイルのffprobe、公開ZIP全メンバーのCRC/hash、固定音声と送信履歴、25引用場面のprovenance、10人物場面、旧動画と旧描画世代の保持を再照合します。成功するまでは集約納品を作りません。公開用URLや秘密情報は集約記録に保存せず、利用者承認・最終試聴は未実施のまま分離します。
