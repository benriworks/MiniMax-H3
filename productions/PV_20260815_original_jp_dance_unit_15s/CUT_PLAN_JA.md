# CUT PLAN — オリジナル日本人ダンスユニット新曲PV 15秒

## 1. 制作メタデータ

| 項目 | 内容 |
| --- | --- |
| Production ID | `PV_20260815_original_jp_dance_unit_15s` |
| ステータス | 技術: `complete_independently_reviewed`。創作: CUT03後半は `needs_improvement`。公開: 権利確認待ちでblocked。人による試聴は未実行 |
| 目的 | 完全合成人物による、日本人女性3人組ダンスユニットのオリジナル新曲PVの15秒試作 |
| 画面 | 16:9、864x480、24fps |
| 音楽 | 96 BPMのprocedural instrumentalとCUT02 H3 native isolated vocalから、15秒のsong master audioを作成済み。native vocalの正式windowは5.74–9.88秒で、旧5.625–9.125秒は不採用。H3 native instrumentalは使わない |
| 編集 | raw各124 framesから先頭120 frames（各5.000秒）を採用し、frame 120 / 240でhard cut。最終360 frames / 15.000秒 |

## 2. 人物・権利の固定境界

出演者は、いずれも**成人の日本人女性3名として創作する完全合成人物**である。実在人物、提供写真、既存アーティスト、既存グループ、特定の振付・衣装・ロゴ・楽曲・歌詞・MVをreferenceまたは模倣しない。

音楽、歌詞、歌唱、振付、衣装、背景素材、商標、公開・配信、model outputの利用条件は、別途の権利確認が完了するまで公開用素材ではない。組立済み映像masterはあるが、公開・商用利用の可否および人による試聴は確認済みとみなさない。

## 3. 固定した生成・編集方針

| 項目 | 固定値 |
| --- | --- |
| Start image | image generationでcutごとに1枚、合計3枚を作成済み。3人のidentity・人数・基本衣装・色設計を共通のcharacter bibleで維持した |
| CUT D | Dance。I2VA（first-frame-only）で、主役Dのみが明確にactiveに踊る。CUT01 startはproduction GO、終点試行は不採用 |
| CUT V | Vocal。I2VA（first-frame-only）で、主役Vのみが歌唱・表情演技を行う。ほか2名は主役化しない |
| CUT S | Synth。FL2VA（二終点）で、主役Sのみがシンセ演奏を行う。ほか2名は背景で静止または最小限の自然動作 |
| Raw実測 | 3 cutとも864x480、24fps、124 frames。codec・audio stream・hash・full decodeは制作台帳へ記録済み |
| Master音声 | `PV_15s_song_master_f32.wav` を使用。CUT02 native vocalはASR正規化で目標歌詞と1回一致し、5.420–9.440秒に検出。0–5秒および10–15秒はspeechなしのmusic-only。人による試聴は未実施 |

「各cut主役1人のみactive」は、人物数を1人へ減らす指定ではない。3人の連続性を保ちつつ、主役以外は視線・身体・手足の大きな動き、歌唱、演奏を抑える。

## 4. タイムラインとカット表

| Cut | タイムコード / frames | mode | 主役と画 | 音声 | 合格条件 |
| --- | --- | --- | --- | --- | --- |
| D | 00:00.000–00:05.000 / 0–119 | I2VA（first-frame-only） | Dがwideで短いダンスフレーズを担当。V/Sは同一ユニットの背景メンバーとして維持する | 完成song masterの0–5秒（music-only）。CUT raw native audioは不採用 | 3人のidentity・人数・衣装連続性、主役Dのみの明確なactive motion、人体・手足・背景の安定。終点拘束は使わない |
| V | 00:05.000–00:10.000 / 120–239 | I2VA（first-frame-only） | Vがmedium/closeで歌唱する。D/Sは主役化しない | 完成song master内でnative vocalは5.74–9.88秒。伴奏のみの音声を別途重ねない | 主役Vの口形と5.74–9.88秒native vocalの同期、D/Sの抑制、顔・歯・手・衣装・背景の安定 |
| S | 00:10.000–00:15.000 / 240–359 | FL2VA（二終点） | Sがシンセ演奏で締める。D/Vは背景で連続性を維持する | 完成song masterの10–15秒（music-only）。CUT raw native audioは不採用 | 主役Sのみが演奏動作、鍵盤・手指・機材・端点・背景の安定、最後のframeが終了ポーズへ収束。実作では約11.83秒で動作が終わり、後半が静的になりすぎたため次版ではtimingを再設計する |

## 5. Promptと入力素材

| Cut | Start image asset ID | prompt path | mode | 実行状態 |
| --- | --- | --- | --- | --- |
| D | `UNIT_D_START` | `prompts/CUT01_H3.md` | I2VA（first-frame-only） | start imageはproduction GO。H3 rawはproduction candidate GO。3件の終点edit試行はrejected-not-used |
| V | `UNIT_V_START` | `prompts/CUT02_H3.md` | I2VA（first-frame-only） | start imageはproduction GO。H3 rawはproduction candidate GO。master独立監査でASR・視覚監査はGO、人による試聴は未実施 |
| S | `UNIT_S_START` / `UNIT_S_END` | `prompts/CUT03_H3.md` | FL2VA（二終点） | start/end pairはproduction GO。H3 rawは独立candidate GO（手・3鍵・背景・identity・両端anchorを確認） |

各H3 promptは、実在人物・既存作品の模倣禁止、3人の固定identity、主役1人のみactive、96 BPMに合わせた動作時間を明記した。CUT02だけはH3 native isolated vocal（伴奏なし）を生成し、CUT01/CUT03のH3 native audioおよびH3 native instrumentalはfinal mixに使わない。CUT01はI2VAのstart imageのみを使い、Picture 2・終点・last frameへの依存を持たない。prompt file / submitted promptのhash、graph、seedは制作台帳へ記録済みである。

## 6. 編集・出力仕様

1. 各rawの実測frame数が124であることを確認後、先頭120 framesだけを採用する。異なる場合は採用frame範囲を制作記録へ明記する。
2. masterは24fps / 360 frames / 15.000秒とし、D→V→Sをhard cutで接続する。
3. 15秒song master audio（`PV_15s_song_master_f32.wav`）は作成済みである。native vocalの最終契約windowは5.74–9.88秒とし、旧5.625–9.125秒は使わない。音源のpath、hash、作者・許諾・歌詞・歌唱・同期の権利状態が揃うまで、公開用masterを作らない。
4. raw、keyframe、review、assembly成果物は `outputs/productions/PV_20260815_original_jp_dance_unit_15s/` に置く。`outputs/` はignoredで、追跡対象は計画・記録・hashである。

## 7. 生成ゲートとQC

- [x] 3名の完全合成人物のcharacter bible、衣装・背景・色設計を制作方針として固定し、実在人物・既存アーティストのreferenceを入力へ使っていないことを台帳化した。偶発的類似、肖像、公開権利の独立確認は別の未完了gateである。
- [x] UNIT_01 identity lineup、D/V/Sのstart image、Sのend imageのraw/runtime path、bytes、hashを台帳へ記録した。CUT01/CUT02 startとCUT03 start/end pairはproduction GO。Dの終点edit 3件はbackground-hand overlapとidentity driftによりrejected-not-usedである。
- [x] CUT01 H3 rawは `CUT01_00001_.mp4`（452,964 bytes、SHA-256 `7DEFD2DAE0E75144B6E0A18D0CB5613D03C9167DF48E0282ECDDDB3117DFF9A3`）として生成され、864x480 / 24fps / 124 frames / 5.166667秒、H.264 High + AAC-LC 32 kHz stereo、full decode PASSを確認した。独立master監査でDの腕・手、motion continuity、cut境界を再確認し、採用した。
- [x] CUT02 H3 rawは `CUT02_00001_.mp4`（470,580 bytes、SHA-256 `EF8019A2D510DF7650FF5035F9DA12F26BDF16844C6846606854355F2A2B26BB`）として生成され、864x480 / 24fps / 124 frames / 5.166667秒、H.264 High + AAC-LC 32 kHz stereo、full decode PASSを確認した。visual review PASS、ASR正規化歌詞は「まだ見ぬ明日へ、いま走り出そう」と完全一致、a cappellaで音楽なしを確認した。production candidate GOだが、5.167秒raw内のnative vocalは最終5.000秒timelineへの配置とlip-syncをassembly reviewで確認する。
- [x] CUT03 H3 rawは `CUT03_00001_.mp4`（435,562 bytes、SHA-256 `3BF131A3153D1D0681D7F2EB2BF312D7A94D45277DEC01D7B2EC5377778C89A4`）として生成され、864x480 / 24fps / 124 frames / 5.166667秒、H.264 High + AAC-LC 32 kHz stereo、full decode PASSを確認した。独立candidate GOとして、手・3鍵の操作、背景、identity、first/last anchor fidelityを確認した。
- [x] 完成song master audioは `PV_15s_song_master_f32.wav`（5,760,092 bytes、SHA-256 `50147D850DADC94394586D9BEAE2B3E5FA3BC637D5AC1545CC11EA0918E15215`）として生成済み。48 kHz stereo float32 / duration_ts 720,000 / 15.000秒、full decode PASS、loudnorm I -16.00 LUFS / TP -1.87 dB / LRA 2.70、no clip・no NaN。ASR hookは1回のみ、0–5秒・10–15秒はvoiceなしのmusic-only、native vocalの正式windowは5.74–9.88秒。旧5.625–9.125秒はfinal契約から外した。
- [ ] 完成song masterを含め、作者・歌詞・歌唱・音源・同期・公開・配信の権利状態を記録する。未確認なら公開用masterを作らない。
- [x] H3 rawごとのprompt ID、graph hash、seed、codec、pixel format、fps、frame数、duration、audio stream、full decodeを記録した。launcher profile、live workflow revision、server flags、正確なresource peakは追跡証拠へ保存できておらず、未記録境界として残す。
- [x] 人物identity、人数、主役以外のmotion抑制、人体・手指・楽器、端点、black/freezeをcutおよびmasterで独立確認した。CUT02はASR、音響上のvocal activity、rawの口動き区間を照合したが、人による試聴とframe-accurateなmaster lip-syncの独立確認は未実施である。CUT03はtechnical freezeではないが、約11.83秒で実動作が終わり約3.17秒の静的tableauとなるため、ユーザー評価では創作上 `needs_improvement` とする。
- [x] 映像masterは独立監査GO。`PV_20260815_original_jp_dance_unit_15s_master_864x480_24fps.mp4`（1,482,624 bytes、SHA-256 `5EB581C4427C9CC0EEBD37299C4D0B34EBC204095ECF0E6644F2342EEC624392`）。H.264 High / yuv420p、864x480 CFR 24fps / 360 frames / 15.000秒、AAC-LC 48 kHz stereo、full decode PASS、blackなし、VFR 0、NaN/Inf/clipなし。frame 119→120（5.000秒）と239→240（10.000秒）のhard cutにblack/flash/corruptionなし、identity・衣装・stageは連続。音声は-16.06 LUFS-I / -1.79 dBTP / LRA 2.8、ASR歌詞は正規化で1回一致。CUT03は約11.83秒で鍵盤動作を完了し約3.17秒のsustain tableauとなる静的outroが創作上の留意点。人による試聴と公開権利確認は未実施。
- [ ] 公開前に、人物肖像、音楽・歌詞・振付、衣装・ロゴ・背景、model output、配信先の利用条件を独立確認する。

## 8. 次版へ持ち越す改善点

CUT03後半の静止感は、今回のmasterを技術的に不合格にするものではないが、次版では現在のmotion timingを再利用しない。主要動作を4秒台まで配分し、最終holdを短くすること、FL2VAの終点拘束へ早く収束していないかを人物ROIのmotion coverageで測ること、経路の自由度を優先する場合はI2VA start-onlyとのA/Bを行うことを次回検証とする。これらは現時点では改善仮説であり、一般的なFL2VAの性質として断定しない。共通の判断基準は[制作プレイブック](../../PRODUCTION_PLAYBOOK_JA.md)へ記録する。

既存の `ARCHITECTURE.md` と `ARCHITECTURE_DIAGRAM.md` は、この制作台帳の追加だけでは変更しない。
