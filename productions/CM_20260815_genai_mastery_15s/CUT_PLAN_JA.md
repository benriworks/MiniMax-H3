# CUT PLAN — 生成AIをマスターする 15秒CM

## 1. 制作メタデータ

| 項目 | 内容 |
| --- | --- |
| Production ID | `CM_20260815_genai_mastery_15s` |
| ステータス | 3 cutのrawと15秒masterを生成・組立済み。独立master監査はGREEN / blockerなしで完了した `complete_independently_reviewed`。公開権利確認は別途未完了 |
| 目的 | 「生成AIをマスターする」ことへの参加を促す、15秒・3カットの短尺CM |
| 言語 | 会話は日本語。H3 prompt本文は `h3-prompt-writing` の規約に従い英語で別ファイルに確定する |
| 画面比 | 16:9 |
| 最終尺 | 15.000秒、24fps、360 frames |
| 編集 | 3 cutをhard cutで接続。クロスディゾルブ、フェード、BGMは使わない |

## 2. 固定した技術方針

各cutは、FL2VAのdiffusion modelを使う**I2VA（first-frame-only）**として生成する。これはFL2VAというモデル名・重みを使うだけであり、first/last frameを両方拘束するFL2VA入力モードではない。

| 項目 | 固定値 |
| --- | --- |
| Profile | `official_q4` |
| Diffusion model | Comfy-Org official `minimax_h3_fl2va_pruned_int8_convrot.safetensors` |
| Text encoder | `qwen3vl-32B-MiniMax-H3-Q4_K_M.gguf` |
| Turbo | 使用しない |
| Sampler / scheduler / steps | `res_multistep` / `simple` / 20 |
| Denoise | 1.00 |
| Raw生成指定 | 864x480、24fps、5秒 |
| 編集上の採用範囲 | rawの先頭120 frames（0–119）を各cutに採用し、5.000秒へ統一 |
| Rawの余り | 5秒指定の既知実績は124 frames（約5.167秒）。末尾4 frames（120–123）はハンドルとして残すか破棄し、採否を制作記録へ残す |
| Audio | BGMなし。CUT2の指定台詞だけを唯一の会話とし、CUT1/CUT3には会話を入れない |

実行時のVRAM mode、ComfyUI server flags、workflow JSON revision、raw frame数・codec・audio streamは `PRODUCTION_RECORD_JA.md` と[素材ハッシュ台帳](manifests/source-hashes.json)に固定した。CUT1/CUT2/CUT3はいずれも124 frames / 約5.1667秒のrawから先頭120 framesを採用し、360 frames / 15.000秒のmasterを組み立てた。独立master監査はGREEN / blockerなしで、exact spec、full decode、blackdetect、1秒超freeze、hard-cut境界を確認した。これは技術・監査記録であり、公開権利の承認を意味しない。既存の `ARCHITECTURE.md` と `ARCHITECTURE_DIAGRAM.md` は本CMの制作記録追加では変更しない。

`CUT01_LATERAL_DOLLY_FL2VA_V3` は、`PRESENTER_01_WIDE` と専用の終点画像を同時に拘束するFL2VA（二終点）実験であり、上記のcanonicalなI2VA 3 cut方針の例外として隔離する。候補MP4は完了後に独立評価されproduction rejectとなったため、CUT1・masterへの採用対象ではない。

## 3. 生成前ゲート

このCMについて、ユーザーはreferenceを提供し、このCM制作を明示的に依頼した。CUT1/CUT2/CUT3のfirst frameは生成・視覚レビュー済みで、H3 promptも確定済みである。これらは本タスク内の制作開始根拠であり、公開・広告出稿・人物肖像・素材の二次利用・モデル出力の公開についての独立した権利確認を意味しない。

以降の生成・採用前に守る条件は次のとおり。

1. 表示コピー、ブランド名、ロゴ、CTAは本計画では使わない。追加する場合は正規素材と正確な文言を別途確認する。
2. CUT2の唯一の台詞は `あなたも生成AIをマスターしませんか？` とし、ほかの会話・ナレーション・BGMを入れない。
3. CUT3は同じプレゼンターと着席者・会議室の連続性を保持する。**text-free / logo-free / UI-free**であり、人物を排除する指定ではない。
4. 各cutの実生成結果、hash、codec、編集判断と独立master監査は制作記録へ追記済み。masterの公開・配信前には、権利・出典・モデル利用条件を確認する。

## 4. タイムラインとカット表

| Cut | 編集タイムコード / frames | 画・演出 | I2VA first-frame anchor | 音声 | 接続と合格条件 |
| --- | --- | --- | --- | --- | --- |
| CUT1 | 00:00.000–00:05.000 / 0–119 | プレゼンテーション会場のwide。人物と会場の関係が一目で分かる導入。話者は無言で、主動作は一つに絞る。 | `PRESENTER_01_WIDE`。人物、会場、投影面・机などの空間配置をfirst frameから維持する。 | 会話なし、BGMなし。必要最小限の会場環境音だけを許容し、音声が不要なら編集で無音化する。 | 5.000秒でhard cut。人物・会場が不自然に崩れず、未承認のロゴ・読める文字・製品主張がないこと。 |
| CUT2 | 00:05.000–00:10.000 / 120–239 | 同じプレゼンターの正面close-up。視線と口元を安定させ、訴求を一つに絞る。 | `PRESENTER_01_CLOSE`。CUT1と同一人物にする場合は髪型、服、照明方向、会場の色温度を一致させる。 | 唯一の台詞: `あなたも生成AIをマスターしませんか？`。ほかの会話・ナレーション・BGMは入れない。 | 10.000秒でhard cut。台詞が日本語で一度だけ明瞭に聞こえ、口形・話者・音声が一致し、画面内に未承認の文字を生成しないこと。 |
| CUT3 | 00:10.000–00:15.000 / 240–359 | wideで締める、text-freeのAI visual。CUT1の会議室、同じプレゼンター、着席者の連続性を保ち、投影面だけを非表象のAI visualへ切り替える。具体的な製品UIやブランド資産を模倣しない。 | `AI_VISUAL_WIDE`。同じプレゼンター、着席者、会議室、抽象形状、色、空間の最初の配置をfirst frameから維持する。 | 会話なし、BGMなし。必要最小限の非言語SFXのみ検討可。 | 最終frameで安定して終わること。**読める文字、ロゴ、模倣UIを含めない**こと。人物・着席者は意図した連続要素として維持する。 |

## 5. Prompt確定の予定パス

promptファイル、ファイルhash、submitted prompt hash、3件のprompt IDとgraph hashは[素材ハッシュ台帳](manifests/source-hashes.json)に記録する。3 cutとも生成済みである。

| Cut | 予定パス | mode | 必須内容 |
| --- | --- | --- | --- |
| CUT1 | `prompts/CUT01_H3.md` | I2VA | 最初の行で `<Picture 1>` と0.00秒の対応を明記し、無言wide、会場配置、hard-cut直前の安定状態を英語で記述する。 |
| CUT1 alternative | `prompts/CUT01_LATERAL_DOLLY_H3.md` | I2VA | `CUT01_LATERAL_DOLLY_V1`。Truck Rightを意図した代替rawだが、独立評価ではgentle pan-likeに留まり未選択。canonical masterは変更しない。 |
| CUT1 FL2VA V3 experiment | `prompts/CUT01_FL2VA_V3_H3.md` | FL2VA（二終点） | `CUT01_LATERAL_DOLLY_FL2VA_V3`。`PRESENTER_01_WIDE` と `CUT01_FL2VA_V3_TAIL` を始終点に使う。候補MP4は独立評価でproduction rejectとなり、実験記録としてのみ保持しcanonical masterへは採用しない。 |
| CUT2 | `prompts/CUT02_H3.md` | I2VA | 同じI2VA alignmentに加え、唯一の日本語台詞を原文のまま `<d>[Japanese] …</d>` に置き、BGMを指定しない。 |
| CUT3 | `prompts/CUT03_H3.md` | I2VA | 同じI2VA alignmentに加え、同じプレゼンター・着席者・会議室を維持したtext-free、logo-free、UI-freeのAI visual wideを英語で明記する。 |

各promptは以下の順序を厳守する: first-frame alignment文、空行、`integrated_multimodal_description`、`overall_soundscape`、`non_diegetic_music`。`non_diegetic_music: N/A` を用いてBGMなしを明示する。カットは別々に生成するため、CUT2/CUT3のpromptには前cutの画を参照しているかのような未解決ラベルを書かない。`CUT01_LATERAL_DOLLY_V1` は、投入時のembedded UTF-8 prompt（末尾LFなし、2,405 bytes、SHA-256 `74b3ad174d69c314d0be462ebb4409d9f01bf4fef5df2832802a409e3200e3db`）と、追跡中ファイル（末尾LFあり、2,406 bytes、SHA-256 `841179fcfadbf80f5e8f0e3c8b0a5b506be58dd0cbf932705c4a4c4d7bfd359b`）を区別して記録する。本文差はなく、末尾LFを除いたbytesは一致する。

## 6. 編集・出力仕様

1. 各raw MP4をffprobe等で確認し、frame rate、frame数、video/audio codec、durationを制作記録に残す。
2. 各cutはrawの先頭120 framesを採用し、24fpsの編集タイムラインで 00:00 / 00:05 / 00:10 にhard cutを置く。
3. CUT2の台詞が5秒の採用範囲に完全に収まることをASRで確認する。CUT1/CUT3の不要な会話・音楽・文字は採用しない。
4. Masterは15.000秒・360 framesのMP4とし、実際のcodec、pixel format、audioの有無・構成、hashを制作記録に固定する。
5. raw候補・first frame・検査画像・master MP4は `outputs/productions/CM_20260815_genai_mastery_15s/` に置く。`outputs/` はignoredであり、追跡対象は計画・記録・ハッシュだけである。
6. `CUT01_LATERAL_DOLLY_V1` はCUT1の未選択代替rawとして記録する。canonical masterには組み込まない。将来採用比較を行う場合は、別名のcomparison masterと独立監査を新たに記録する。
7. `CUT01_LATERAL_DOLLY_FL2VA_V3` は始終点を拘束する実験として完了した。full decode、blackdetect、speechなし、anchorのPSNRと人数／bar数の安定は確認したが、zoom/vertical drift、正しくないparallax、morph、bar clipping、終盤near-freezeのためproduction rejectとし、canonical masterには組み込まない。

## 7. QCチェック

- [x] 3 rawがそれぞれ `official_q4` / no-Turbo / `res_multistep` / `simple` / 20 stepsで生成され、prompt ID / graph hash / seedを記録した。
- [x] 各cutのI2VA first frame、promptファイルSHA-256、submitted prompt SHA-256、artifact SHA-256を記録した。
- [x] CUT1は無言wideとして採用したが、minor hand/face softnessを記録した。CUT2はvisual passで、rawのmild face/dental fluctuationを記録した。CUT3はvisual passで、最終秒のprojection screenのminor deviationを記録した。
- [x] CUT2のnative audioはfaster-whisper smallのtop 1と独立dictationのtop 2（近接confidence）で指定台詞を確認し、assemblyでは0.84秒早めてCUT2内0.62–3.90秒に置いた。残存lip sync差は概ね±0.25–0.3秒。CUT1/CUT3はvoice/musicなし、BGM/room toneなしの意図的に静かなCMである。
- [x] CUT3に読める文字、ロゴ、模倣UIがなく、意図したプレゼンター・着席者・会議室の連続性を保つ。CUT1/CUT2にも未承認の文字・ロゴ・製品主張がない。
- [x] 採用範囲はcutごとに120 frames、最終masterは360 frames / 15.000秒 / 24fpsである。hard cutはframe 120/240に置いた。
- [x] rawとmasterのfull decodeを通過し、独立master監査でexact spec、blackdetectなし、1秒超freezeなし、naturalなhard-cut境界を確認した。CUT3のscreenは終端まで動き続けることを記録したがblockerではない。
- [x] `CUT01_LATERAL_DOLLY_V1` はfull decode / blackdetect / freezeをPASSしたが、Truck Rightはwhole imageが約20–25 px左へ単調移動し、near/farのparallaxが弱いまたは逆転、明確なocclusion revealがないためFAIL。gentle pan-like代替としてのみ記録し、未選択・master不変とした。
- [x] `CUT01_FL2VA_V3_TAIL` は終点画像として実体hashを記録したが、bar edge、人物位置の不整合、table/handsの縦方向変化、face differenceにより独立endpoint QCはexperimental-only / production no-go。`CUT01_LATERAL_DOLLY_FL2VA_V3` はfull decode PASS、blackなし、speechなし、anchor PSNR 31.51 / 31.22、4人／8 bars安定を確認した一方、12.89%のzoom-in+vertical drift、homography 76.6%、正しくないdepth parallax/occlusion reveal、face/hand/desk morph、rightmost bar clipping、4.416秒以降のnear-freezeによりproduction rejectとした。canonical masterは不変である。
- [ ] 公開前の権利・出典・モデル利用条件の確認を完了する。
