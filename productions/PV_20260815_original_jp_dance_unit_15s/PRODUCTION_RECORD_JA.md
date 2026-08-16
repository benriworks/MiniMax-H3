# 制作記録 — PV_20260815_original_jp_dance_unit_15s

## 1. 記録の目的と状態

このファイルは、完全合成人物による15秒PVの素材、生成、編集、QC、権利確認の台帳である。技術状態は `complete_independently_reviewed` で、3本のH3 rawと15秒映像masterは独立監査GOである。一方、創作状態はCUT03後半が `needs_improvement`、公開状態は権利確認待ちのblocked、人による試聴は未実行である。これらを技術GOから推測で昇格しない。

| 項目 | 計画値 / 状態 |
| --- | --- |
| Production ID | `PV_20260815_original_jp_dance_unit_15s` |
| 最終設計 | 864x480、24fps、15.000秒、D/V/Sの3 cuts × 5.000秒、hard cut、96 BPM |
| 入力人物 | 成人日本人女性3名の完全合成人物。実在人物・提供referenceなし |
| 音楽 | 15秒song master audioはmasterへ使用済み。ASRは目標歌詞を1回検出し、0–5秒・10–15秒にspeechなし。公開権利と人による試聴は未確認 |
| H3 raw | D/V: I2VA、S: FL2VAはいずれも候補GO |
| Master | 技術監査GO。技術仕様・hash・full decode・ASR・視覚監査を記録済み。CUT03後半は創作上 `needs_improvement`。公開権利と人による試聴は未実行 |
| 関連文書 | [CUT_PLAN_JA.md](CUT_PLAN_JA.md)、[ASSET_PROVENANCE_JA.md](ASSET_PROVENANCE_JA.md)、[source-hashes.json](manifests/source-hashes.json)、[制作プレイブック](../../PRODUCTION_PLAYBOOK_JA.md) |

## 2. 実行環境

| 項目 | 実測値 |
| --- | --- |
| profile / workflow revision | 生成は完了済み。cut別のaccepted graphとprompt IDは記録したが、launcher profile名とlive workflow revisionは追跡証拠へ保存していない |
| diffusion / text encoder | cut別graphの監査ではofficial INT8 diffusion + Q4 text encoder、no-Turbo、`res_multistep` / `simple` / 20 stepsを確認。root runtime欄のモデル名・hashは未記録のため、ここから推測して補完しない |
| server flags / VRAM mode | 生成は完了済みだが、実行時flagsを追跡証拠へ保存していない |
| ComfyUI / custom node revision | repo lockは存在するが、実行中プロセスのrevisionを本制作台帳へ保存していない |
| GPU / RAM / pagefile / peak metrics | 進行中の部分観測はあったが、cut別の正確なpeakを追跡証拠へ保存していない |

artifact、cut別graph、prompt ID、seed、開始・終了時刻、媒体仕様、hash、QCは追跡できる。一方、launcher profile、live revision、server flags、正確なresource peakが欠けるため、この台帳はartifact照合には使えるがbit-for-bit再現には十分ではない。次回は生成前にこれらを固定し、実行時に保存する。

## 3. Cut別生成台帳

| Cut | 入力 / 主役 / 音声 | prompt / graph / seed | raw artifact / probe | 採否・QC |
| --- | --- | --- | --- | --- |
| D | `UNIT_D_START`、主役Dのみactive dance、完成song masterの0–5秒（music-only）。start imageはproduction GO、終点edit 3件はrejected-not-used | `prompts/CUT01_H3.md`、I2VA。prompt ID `d9ad471d-9bfb-4029-a729-134699d7278f`、graph SHA-256 `81a6b8510ef8e4e3e04ed951581f9775fb0159486e163670caee9eabcd9f4f55`、number `10`、seed `529716596879763`。00:37:13.300–03:34:05.003 JST（02:56:51.703） | `outputs/productions/PV_20260815_original_jp_dance_unit_15s/02_cuts/CUT01/candidate/CUT01_00001_.mp4`、452,964 bytes、SHA-256 `7DEFD2DAE0E75144B6E0A18D0CB5613D03C9167DF48E0282ECDDDB3117DFF9A3`、864x480 / 24fps / 124f / 5.166667秒、H.264 High yuv420p + AAC-LC 32 kHz stereo、full decode PASS | `production_candidate_go`。独立master監査で腕・手、motion continuity、cut境界を再確認し、採用済み |
| V | `UNIT_V_START`、主役Vのみactive vocal、完成song master内のnative vocalは5.74–9.88秒。start imageはproduction GO | `prompts/CUT02_H3.md`、I2VA。prompt ID `c5f88d7b-32e1-4634-9383-8294ba4e6225`、graph SHA-256 `d38370aa9ac68f2ce28eb3a5799cf808acfc5b1ecc4d0439da7604f07fbbe6b7`、number `11`、seed `529716596879763`、submitted prompt SHA-256 `aaf1c8483eaedf0e7907e7a556976f7eea82feee9ab2a464ae4ccf66c7837ecd`、`UNIT_V_START` runtime SHA-256 `59333D68EEA8CAEC5CC82FDFA42044FC7F61A3B0F137DFD79058672DE6F3BD90`、03:48:14.275–06:43:39.938 JST（02:55:25.663） | `outputs/productions/PV_20260815_original_jp_dance_unit_15s/02_cuts/CUT02/candidate/CUT02_00001_.mp4`、470,580 bytes、SHA-256 `EF8019A2D510DF7650FF5035F9DA12F26BDF16844C6846606854355F2A2B26BB`、864x480 / 24fps / 124f / 5.166667秒、H.264 High yuv420p + AAC-LC 32 kHz stereo、full decode PASS | `production_candidate_go`。visual review PASS、ASR正規化歌詞は「まだ見ぬ明日へ、いま走り出そう」と完全一致、a cappella・音楽なし。正式native vocal windowは5.74–9.88秒（旧5.625–9.125秒は不採用）。映像masterの独立ASR・視覚監査はGO、人による試聴は未実施 |
| S | `UNIT_S_START` / `UNIT_S_END`、主役Sのみactive synth、final song master 10–15秒。start/end pairはproduction GO | `prompts/CUT03_H3.md`、FL2VA。prompt ID `aab50222-1d94-42c3-a817-f93452c583ec`、graph SHA-256 `6e29fc773ab5a65017faca6cbcae8fe6254c2e3ef4d2314e53358fb52b3e12f8`、number `12`、seed `529716596879763`、submitted prompt SHA-256 `d669a895b3970774c0f450f15c01b0f22cee222b1bcf3d89ae84669ff946bef7`、`UNIT_S_START` / `UNIT_S_END` runtime SHA-256を固定。07:06:26.785–10:09:27.378 JST（03:03:00.593） | `outputs/productions/PV_20260815_original_jp_dance_unit_15s/02_cuts/CUT03/candidate/CUT03_00001_.mp4`、435,562 bytes、SHA-256 `3BF131A3153D1D0681D7F2EB2BF312D7A94D45277DEC01D7B2EC5377778C89A4`、864x480 / 24fps / 124f / 5.166667秒、H.264 High yuv420p + AAC-LC 32 kHz stereo、full decode PASS | `independent_candidate_go`。手・3鍵の操作、背景、identity、first/last anchor fidelityを確認 |

各rowには、実行後に次を記録する。

- start/end image asset ID、raw/runtime相対path、bytes、SHA-256、派生方法、視覚レビュー。CUT01はstart imageのみを入力に使い、reject済み終点editは入力に使わない
- prompt全文とsubmitted promptのSHA-256、ComfyUI prompt ID、seed、model、profile、workflow graph SHA-256、server flags
- raw MP4の相対path、bytes、SHA-256、video/audio codec、pixel format、fps、frame数、duration、full decode
- 主役1人のみactiveというmotion gate、人数・identity・人体・手指・機材・端点の品質確認
- 生成時刻、sampling時間、総時間、OOM/illegal access等の有無

## 4. 編集決定記録

| 項目 | 決定 / 実測 |
| --- | --- |
| 編集タイムライン | 実測24fps、360 frames、15.000秒 |
| 採用範囲 | D/V/Sのrawはいずれも124fで、各cutのframe 0–119を採用。余り4fはmasterへ入れていない |
| Transition | frame 120 / 240でhard cutのみを使用 |
| 音源 | 完成song masterは `outputs/productions/PV_20260815_original_jp_dance_unit_15s/03_assembly/audio/PV_15s_song_master_f32.wav`。5,760,092 bytes、SHA-256 `50147D850DADC94394586D9BEAE2B3E5FA3BC637D5AC1545CC11EA0918E15215`。PCM float32 / 48 kHz stereo / duration_ts 720,000 / 15.000秒、full decode PASS。映像master実測は-16.06 LUFS-I / -1.79 dBTP / LRA 2.8、NaN/Inf/clipなし。ASRは5.420–9.440秒に「まだ見ぬ明日へ 今走り出そう」を1回検出し、正規化目標と完全一致、0–5秒・10–15秒にspeechなし。人による試聴・権利は未確認 |
| Master artifact | `outputs/productions/PV_20260815_original_jp_dance_unit_15s/03_assembly/master/PV_20260815_original_jp_dance_unit_15s_master_864x480_24fps.mp4`。1,482,624 bytes、SHA-256 `5EB581C4427C9CC0EEBD37299C4D0B34EBC204095ECF0E6644F2342EEC624392`。H.264 High yuv420p / tv / bt709、864x480 CFR 24fps / 360f / 15.000秒、AAC-LC 48 kHz stereo / 15.000秒、full decode PASS、blackなし、VFR 0、-16.06 LUFS-I / -1.79 dBTP / LRA 2.8。hard cutは119→120（5.000秒）/ 239→240（10.000秒）でblack/flash/corruptionなし、CUT raw native audioは破棄し完成song masterのみを使用。独立監査GO、ただしCUT03の約3.17秒の静的outroは創作上の留意点 |

音源権利が未確認の間は、組立済み映像masterがあっても公開用・商用masterではない。人による試聴も未実施である。

## 5. QC結果

| 確認項目 | 結果 / 根拠 |
| --- | --- |
| 3名の完全合成人物・実在人物reference不使用 | 制作方針と生成assetの由来として記録済み。ただし実在人物への偶発的類似、肖像、公開可否は独立確認していない |
| CUT Dのdance / CUT Vのvocal / CUT Sのsynth | 3 cutは候補GO。master独立監査はGOだが、CUT03の約3.17秒静的outroは創作上の留意点 |
| 各cut主役1人のみactive | 独立監査GO。identity・衣装・stageの連続性を確認。CUT03の主役Sは約11.83秒で鍵盤動作を完了し、以後約3.17秒の静的sustain tableauとなる |
| 3 start imageとD/S end imageの連続性 | CUT03のfirst/last anchor fidelityを確認。masterでもidentity・衣装・stageの連続性を確認 |
| 96 BPM song masterとCUT02 native isolated vocalの同期・権利 | ASRは5.420–9.440秒に目標歌詞を1回検出し、正規化で完全一致。0–5秒・10–15秒はspeechなし。公開権利と人による試聴は未確認 |
| raw 124f→120f、master 360f / 15.000秒 | masterは360f / 15.000秒。CUT rawはいずれも124f |
| full decode / blackdetect / freeze / hard cut | full decode PASS、blackなし、VFR 0、exact duplicate adjacent frames 0。freeze detectorのholdは意図的でCUT01 holdは許容、hard cutは119→120 / 239→240でblack/flash/corruptionなし |
| 公開・配信・model outputの権利 | 未確認 |

## 6. 納品後の創作フィードバック

ユーザー評価では、CUT03は後半の動きが少なすぎる。これは媒体破損やfreeze detector上のtechnical failureではないが、PVとしてのmotion coverageが不足した創作上の `needs_improvement` である。現masterの技術監査GOは変更しない一方、次版で現在のCUT03 timingをそのまま再利用しない。

次回は、主動作をcut後半まで配分し、最後の静止を0.3–0.5秒程度に抑える案、4秒台に鍵を離す・次の和音へ移る・視線や上体でaccentを付ける案、I2VA start-onlyとFL2VAのA/Bを試す。いずれも未検証の改善仮説であり、technical freezeとは別にcreative motion coverageをQCする。詳細は[制作プレイブック](../../PRODUCTION_PLAYBOOK_JA.md)を参照する。

## 7. 成果物と境界

| 区分 | path / 状態 |
| --- | --- |
| 追跡する計画・記録 | `productions/PV_20260815_original_jp_dance_unit_15s/` |
| ignored image / raw / review / master | `outputs/productions/PV_20260815_original_jp_dance_unit_15s/` |
| 既存CM production | 変更しない |
| architecture docs | 制作台帳追加のみのため変更しない |

statusは `planned` → `ready_for_generation` → `generating` → `candidates_ready` → `selected_for_assembly` → `assembled_pending_independent_review` → `complete_independently_reviewed` と進める。各遷移は実測artifact・QC・権利境界に基づき、未実行の生成や公開可否を推測しない。
