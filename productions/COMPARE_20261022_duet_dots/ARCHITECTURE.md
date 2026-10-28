# 比較動画の制作構成

このフォルダーは60〜90秒の比較動画1本を扱う独立した制作単位。既存CreatorShortの30秒制作と完成済みdots／Claude動画を保持する。比較用フロントエンド、独立production wrapper、実素材レンダーを実装済み。実音声14区間は68.113秒、無加工PCMを配置した実尺は75秒。公開用検査・利用者採用は別状態である。

公式一次資料 → 主張と根拠の対応 → 台本とカット案 → 引用画像の実撮影・新人物動画の確認 → 音声生成と長さ計測 → 独立した比較用composition → 全画面・音声・公開用パッケージ検証、の順で進める。取得済みの事実、架空例、編集上の解釈、未検証事項は別フィールドで管理する。

`script-draft.json` が日本語文言と暫定尺の入力、`evidence-table.json` が主張の根拠、`sources.json` が引用上限、`image-quote-candidates.json` が撮影対象を定義する。公式画面の例はorigin official、架空カフェの動図は自作解説、森川遥は架空人物として明確に分ける。

描画は `studio/src/remotion/comparisonEntry.tsx` から `ProductComparison` を登録し、`comparisonMotion.ts` の専用検査を通して `ComparisonComposition.tsx` で行う。原稿の14カット82秒は仮配分として保存し、実音声では14カット75秒へ配分した。比較だけ1440〜2160フレームを受け入れ、1〜8秒のカットで全尺を埋める。旧CreatorShortの1440フレーム上限・人物配置条件・公式URL許可条件は変更しない。比較用だけ正確な `https://learn.chatgpt.com/docs/dots` を追加で受け入れる。

比較図は `fictional_case / signal / workspace / availability / decision` の閉じたレイアウトと最大2つの上下パネルを使う。製品名・条件・主張は台本データ側に置き、描画コンポーネントに製品能力を固定しない。公式画像は実PNGをcontainで表示し、画面内に公式資料の引用表示を付ける。公開用準備処理では、画像のhash・日時・URL・矩形・私的な原本を既存proof検査へ渡す必要がある。フロントエンドのURL検査だけを来歴検証の代わりにしない。

人物は `presenter` の opening / insight / closing。productionでは実MP4を必須とし、`mediaStart + mediaPlayFrames <= mediaDurationInFrames` を検査する。素材が場面より短い場合は動画区間終了後に自作まとめカードへ切り替え、最終フレームの静止延長やループを行わない。人物未取得のfixtureは「動画素材 待機中」と明示し、productionへ流用できない。人物の生成証跡・実動画尺・目視合格の照合は外側の準備処理が行う。

画面は1080×1920・24fps。主な文字は54px以上、見出し10表示単位×2行、字幕12表示単位×2行。比較字幕は62px・行高1.18、上端1300pxで2行を1490px以内に収める独立表示を使う。固定日本語フォントの読み込み後、各フレームで実際の文字矩形と横方向のはみ出しを検査する。既存字幕コンポーネントは変更しない。

`render-fixtures.mjs` は元台本を変更せず、独立フォルダーに14場面のPNGとprops、確認記録を作る。`caption-phrases.json` は元ナレーションと連結一致を検査した短句。このfixture出力のタイミングだけは仮配分で、実音声との同期検証には使わない。production出力は実音声に基づく75秒の配分であり、fixtureの暫定尺とは別である。fixtureには画面下部の内部確認表示があり、公開用パッケージへは使用しない。TTS/API送信はこの処理にない。

境界テストは `studio/tests/comparison-motion.test.mjs`。比較だけの尺拡張、旧上限の維持、不正な時刻・レイアウト・URL・欠落素材・動画範囲を確認する。実行前に `comparisonMotion.ts` と `shortsMotion.ts` を `.comparison-test-dist` へCommonJSとしてコンパイルする。型検査は `npx tsc --noEmit -p tsconfig.app.json`。最終状態では型検査、frontend境界7テスト、production・証跡7テストが合格。実素材による1800frameの描画と文字安全域検査、完成MP4の全decode、75秒の実尺、-16.02 LUFS／-2.15 dBTPの音量、全14場面と人物切替の目視を確認した。S3の再生用・保存用MP4もHEADと全体GETのhash照合まで合格。聴感と利用者採用は未確認であり、YouTube投稿は行っていない。

Aoede生成は実行時に既存の送信間隔・検証済みcache・不明送信停止を維持する。H3人物動画は元キー画像・生成証跡・全decode・目視に結び付ける。保存済み音声を視覚修正のたびに再生成しない。最終的な可読性、試聴、利用者承認、YouTube投稿は別状態で記録する。

公式撮影の実データは`captures/manifest.json`を入口とする。独立Chromeのviewport PNGをprivateへ保存し、DPRを反映した整数矩形で公開PNGを無加工cropする。原本・metadata・公開PNG・proofをSHA-256で結び付け、別の読み取り専用検証で画素一致と既存`load_capture`読み込みを照合する。C08は公式サイト内のインタラクティブな説明例を押した状態であり、実アカウントの製品実証とは分ける。公開cropから名前と第三者サイトを除き、ページ単位の引用総数を25語以内にする。子の画像確認と親の最終確認は別フィールドで保持し、private原本とCLIログは納品物に含めない。


## 実素材の制作経路（2026-10-23）

`produce.py` は `generate / prepare / stills / render / assemble / review / package` を分離する。Gemini送信は明示したgenerateだけ。既存の `gemini_voice_trial.py` を読み取り再利用し、Aoede・22秒間隔・排他lock・hashと原稿一致のキャッシュを維持する。不明・不完全な送信は自動再送せず停止する。今回14要求の音声は検証済みで、再実行テストでも追加要求は0。APIキーやHTTP応答の機密headerは保存しない。

prepareは承認済み14カットの原稿、captions短句、公式manifestの親確認3画像、実MiniMax人物の親確認proofを検査する。公式画像は原本との画素一致、撮影日時、URL、crop座標、hash、引用語数を照合する。人物は768×1376・24fps・124frameの実MP4をfull decodeし、0〜35frameを冒頭、36〜83frameをひらめき、84〜123frameを締めに各1回割り当てる。全124frameを重複使用しない。場面の残尺は自作カードへ切り替わる。

各発話の元PCMを速度・ピッチ変更せず1000samples/frameとして配置し、3frameの開始余白と終端余白を保証する。1〜8秒のカットと60〜90秒の比較全尺を保ち、余剰フレームだけを均等に配る。字幕は実発話区間で短句の表示文字量に応じて配分し、単語レベルの強制アラインメントとは区別する。`timings.json` に元発話と実時刻を記録する。

`studio/comparison-render.mjs` は準備・描画ソースのhashを開始時と終了時に照合し、production素材の欠落を拒否する。14場面のPNG、人物からまとめへの3切替、ガイド画面を作る。全1800frameの文字安全域検査を伴うH.264映像を音声なしで出力する。assembleは共通finishの2パス音量正規化と完全decodeを再利用し、ナレーションと自作BGM・効果音だけを48kHz stereo AACへ合成する。人物MP4に元音声があっても使わない。

試聴を含むreviewは別証拠を必須とする。モデルが音声入力に対応していない場合は、decodeやPCM一致を聴感確認と呼ばず、聴感待ちのレビュー候補として渡す。利用者承認・S3送信・YouTube投稿を技術合格と混同しない。配布ZIPは動画・見出し・説明文・字幕・公開引用PNGと公開来歴だけをallowlistで同梱し、private原本とAPI要求を含めない。各memberのbytesとSHA-256を圧縮後に再検証する。

検証：TypeScript型検査、frontend境界7テスト、production側7テスト。productionテストは実PCM一致、発話の切断防止、60〜90秒と8秒境界、公式URLのnear-match拒否、3画像の画素一致、人物区間の非重複、不明送信停止、追加API0のcache再利用を扱う。

今回の環境ではaudio入力が非対応と明示されたため、`package_review.py` で聴感未確認のレビュー候補を作る。確認不能を合格にせず、元PCM・全decode・音量と目視を確認した範囲で配布する。公開ZIP13memberをhash/CRC照合済み。S3upは既存AllowedRootsへコピーした4,569,806 bytesの同一MP4を再生用inline／保存用attachmentに分け、dry-run後のHEADと全体GET、SHA-256を検証する。S3結果はURLなしのreceiptsだけを保存し、署名URLは返信で渡す。

公開ZIP内の `verification-public.json` は包装時点のスナップショットで、`s3_uploaded: false` は送信前の状態を表す。共有後の最新状態はZIP外側の `delivery-manifest.json` とURLを含まない `s3-receipts.json` を正本とする。包装時点と現在の共有状態を外側manifestに明記し、動画・ZIPのbytesとSHA-256を維持する。

## 人物の全画面改訂（2026-10-23）

ユーザー指定の全画面人物版は比較専用propsの `presenterTreatment: immersive` で選ぶ。未指定とcardは従来描画を保持する。人物MP4を縦画面全面へcover表示し、顔が見える中央部分を避けて上端と下端の暗いgradient上に見出し・要点を置く。見出しは顔の下のy850、字幕は既存y1300を維持し、人物の表情を小窓でなく大きく見せる。

`presenterTransition` は動画区間の最終6frameで背景を下から上へ移し、最終実frameまでに切替を完了する。終端の最後3frameから見出しと要点を段階表示し、実動画終了後はまとめだけを表示する。停止画面の延長や同じ素材のループはしない。C01/C10/C14の既存124frameを非重複で使う区間、14カット75秒、全字幕時刻は変えない。

`revise_presenter.py` は旧版と別の出力に音声・字幕・引用画像・人物MP4をhash照合してコピーする。propsの差分はpresenterTreatmentのみ。旧版のMP4・ZIPと共有URLを保持し、追加TTS/MiniMax生成は0。最終AACは旧MP4からstream copyし、音声packet hash一致を要求する。聴感未確認はそのまま引き継ぐ。`preview_presenter_revision.mjs` は顔の見え方と3区間の終了境界を実動画から静止画で確認する専用処理で、full renderを勝手に開始しない。

再stage時は旧prepareに記録された実データと完成MP4のhashを照合する。過去の実装ソースhashは履歴として残し、新prepareは現在の共通コードと改訂用driverへ結び付ける。旧実装のhashを現在のコードと偽って一致扱いせず、実素材・音声の来歴検査は維持する。改訂状態はpresenter-revision-state.jsonに分離し、従来state.jsonを上書きしない。

全画面改訂の完成出力は `outputs/productions/COMPARE_20261022_duet_dots/20261022T191503600528Z-immersive`。全1800frameの安全域検査と完全decode、完成MP4からの14場面・15切替境界の目視を確認した。人物以外11場面の確認PNGは旧版とbytes単位で一致。元PCM・BGM・効果音・字幕・場面時刻もhash一致、AAC packet hashも完全一致。完成MP4は7,360,098 bytes、75秒、-16.02 LUFS／-2.15 dBTP。新規TTSと人物生成は0。人物映像を大きくする改訂だけで、聴感と利用者採用は引き続き未確認である。

全画面改訂の再生用・保存用S3共有は、既存AllowedRoots内へのコピー照合、各dry-run、HEADと全体GET/hash検証が合格。両URLは24時間で、期限は2026-10-24 04:25 JST台。URLはファイルに保存せず、ID・期限・hashをs3-receipts.jsonへ保存した。ZIP内の共有前スナップショットは不変で、外側delivery-manifestが共有後の状態を示す。
