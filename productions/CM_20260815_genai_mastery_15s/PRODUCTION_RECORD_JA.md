# 制作記録 — CM_20260815_genai_mastery_15s

## 1. 記録の目的と状態

このファイルは、採用した素材・生成設定・artifact・編集判断・QCを記録する制作台帳である。CUT1/CUT2/CUT3のrawと15秒masterは生成・組立済みで、artifact hashとfull decodeを記録した。独立master監査はGREEN / blockerなしで完了し、ステータスは `complete_independently_reviewed` である。これは公開、権利許諾、人間による聴取を主張しない。

| 項目 | 予定値 / 状態 |
| --- | --- |
| Production ID | `CM_20260815_genai_mastery_15s` |
| 最終設計 | 16:9、864x480、24fps、15.000秒、3 cuts × 5.000秒、hard cuts、BGMなし |
| 実行状態 | CUT1/CUT2/CUT3: 生成完了。master: 組立完了・full decode PASS。独立master監査 GREEN / blockerなし。公開権利確認は未完了 |
| 構成 | `official_q4`、official INT8 ConvRot + Q4 GGUF、no-Turbo、`res_multistep` / `simple` / 20 steps、denoise 1.00 |
| 入力方式 | CUT1–3ともFL2VA diffusion modelを使うI2VA first-frame-only。last frame入力は使わない。first frameは生成・視覚レビュー済み |
| 既存設計文書 | [CUT_PLAN_JA.md](CUT_PLAN_JA.md)、[ASSET_PROVENANCE_JA.md](ASSET_PROVENANCE_JA.md)、[source-hashes.json](manifests/source-hashes.json)、[制作プレイブック](../../PRODUCTION_PLAYBOOK_JA.md) |

## 2. 実行環境（実行後に確定）

| 項目 | 実測値 |
| --- | --- |
| profile / workflow revision | `official_q4`。CUT1/CUT2/CUT3 graph SHA-256はcut別台帳に記録 |
| diffusion / text encoder SHA-256 | INT8 ConvRot `e889202c41dafb67b10d67b97f0d8541508036a6090af23425a5c2615d03c47a` / Q4 `1bf75e038c5895b97b6ea16cc1e3d32076254b06ec3df10657650d86dc82279e` |
| VRAM mode / server flags | `--novram --cpu-vae --disable-pinned-memory --preview-method none` |
| ComfyUI / custom node revision | ComfyUI `2a68ce33b4c9ea6ee4283e618a74560cefb32694` / ComfyUI-GGUF `6ea2651e7df66d7585f6ffee804b20e92fb38b8a` / torch `2.13.0+cu130` |
| GPU / RAM / pagefile / peak metrics | この制作記録では未採取。実測がなければ補完しない |

## 3. Cut別生成台帳

| Cut | 予定入力 / 音声 | 予定promptパス | prompt ID / seed / prompt SHA-256 | raw artifact / probe / SHA-256 | 採否・理由 |
| --- | --- | --- | --- | --- | --- |
| CUT1 | `PRESENTER_01_WIDE` first frame、無言、BGMなし。keyframe生成・視覚レビュー済み | `prompts/CUT01_H3.md` | prompt ID `f228d949-9024-4b11-84ed-00e507048718`、seed `529716596879763`、submitted prompt SHA-256 `0977e9818d215a4a44302c134ed72f4a7939d524018a0e0e97144d3d4408f8cc`、graph SHA-256 `18d8cdba7d8d23a805c8f9fd47affd6d67b1751e7bd7f4e0eb27c5eaf41eea92`、1:48:03.883 | `outputs/productions/CM_20260815_genai_mastery_15s/02_cuts/CUT01/candidate/CUT01_00001_.mp4`、456,965 bytes、SHA-256 `F369C9EE3A887D6B255F707904A01CA92065E83B58F74FA5C06EBEEE7A75BA2E`、864x480 / 24fps / 124f / 5.1667秒 / H.264 + AAC 32k、full decode PASS | masterへ採用。minor hand/face softnessを記録。独立master監査 GREEN / blockerなし。公開権利確認は別途未完了 |
| CUT2 | `PRESENTER_01_CLOSE` first frame、唯一の日本語台詞、BGMなし。keyframe生成・視覚レビュー済み | `prompts/CUT02_H3.md` | prompt ID `714eaf57-e1df-4900-9d0f-4698606de953`、seed `529716596879763`、submitted prompt SHA-256 `d0b0623bc13b5273040d75bb77f9ce5ce612e4ef05e146ed1ef19c6b2fc51e01`、graph SHA-256 `f0fd96d7e7165eac433ab824a56ae0f1b34c6240b28d613f630a4e0e074a4e68`、45:49.030 | `outputs/productions/CM_20260815_genai_mastery_15s/02_cuts/CUT02/candidate/CUT02_00001_.mp4`、581,174 bytes、SHA-256 `22503A6947C47B4B050015D9DF22D2C120EEADCB48F9C41878545351E720E854`、864x480 / 24fps / 124f / 5.1667秒 / H.264 + AAC 32k、full decode PASS | visual pass。rawのmild face/dental fluctuationを記録。native audioの指定台詞をfaster-whisper smallで確認 |
| CUT3 | `AI_VISUAL_WIDE` first frame、同じプレゼンター・着席者・会議室を維持したtext-free / logo-free / UI-free visual、会話なし、BGMなし。keyframe生成・視覚レビュー済み | `prompts/CUT03_H3.md` | prompt ID `a1a71279-1133-4e14-9fc8-23b4c8237da2`、seed `529716596879763`、submitted prompt SHA-256 `1a908f6f1c0f73b3ea470b1eb7016d413ec64ffc7a26253c3f9758af4b6633a7`、graph SHA-256 `882a6a2914af4568d5fabd77842aa5f80b2ae227baceea7a64d61303824bb099`、43:35.198 | `outputs/productions/CM_20260815_genai_mastery_15s/02_cuts/CUT03/candidate/CUT03_00001_.mp4`、595,143 bytes、SHA-256 `7E17B4E69C34B54AF77E427EF616CEA4EC99CA63C8C7A6B14D431EFFFC489D44`、864x480 / 24fps / 124f / 5.1667秒 / H.264 + AAC 32k、full decode PASS | visual pass。最終秒のprojection screenのminor deviationを記録。masterではdigital silence |

### CUT1代替候補（canonical masterは変更しない）

| Candidate | prompt / 実行 | raw artifact / probe | 独立評価 / 採否 |
| --- | --- | --- | --- |
| `CUT01_LATERAL_DOLLY_V1` | `prompts/CUT01_LATERAL_DOLLY_H3.md`。submitted embedded UTF-8 promptは末尾LFなし2,405 bytes / SHA-256 `74b3ad174d69c314d0be462ebb4409d9f01bf4fef5df2832802a409e3200e3db`、追跡ファイルは同一本文+末尾LFの2,406 bytes / SHA-256 `841179fcfadbf80f5e8f0e3c8b0a5b506be58dd0cbf932705c4a4c4d7bfd359b`。prompt ID `96a023dc-431d-4517-bb52-61f8e3d02b8c`、graph SHA-256 `461d451ad526ea136cd60dc2c64b1810239d609773eedb3da1945e1c8423884c`、seed `529716596879763`、2:57:25.974 | `outputs/productions/CM_20260815_genai_mastery_15s/02_cuts/CUT01/candidate/CUT01_LATERAL_DOLLY_V1_00001_.mp4`、742,273 bytes、SHA-256 `F8C568A374F9B4E275944CD81839826C8545B0BCBAC5324CE4E376EC60794710`、H.264 High / yuv420p / 864x480 / 24fps / 124f / 5.166667秒 + AAC-LC stereo 32k、full decode / blackdetect / freeze PASS、audio I `-61.2 LUFS` / TP `-51.3 dB` / voice・musicなし | `rendered_reviewed_unselected`。video/media stability PASS。Truck Rightはwhole imageが約20–25 px左へ単調移動し、near/farのparallaxが弱いまたは逆転、明確なocclusion revealがないためFAIL。独立評価はPARTIALで、gentle pan-like代替としてのみ採用可能。masterには組み込まない。 |

### CUT1 FL2VA V3実験候補（canonical masterは変更しない）

| Candidate | 入力endpoint / prompt / 実行 | 状態・採否境界 |
| --- | --- | --- |
| `CUT01_LATERAL_DOLLY_FL2VA_V3` | first frame `PRESENTER_01_WIDE`、last frame `CUT01_FL2VA_V3_TAIL`。`prompts/CUT01_FL2VA_V3_H3.md` のsubmitted embedded UTF-8本文は末尾LFなし2,902 bytes / SHA-256 `961d0cbad0f027d0d649579a2e2f0bda354917ddd09f2dc68a67607f4ad44081`、追跡ファイルは同一本文+末尾LFの2,903 bytes / SHA-256 `9412e8767d81530ec07214ed94f07bc96f7f8aa507e5ae3a82b05c7d4d6ac83e`。prompt ID `6ffb6af0-ec84-4894-939e-e8bfcfc8393d`、graph SHA-256 `3369191d76d1354843263f33f207235c670b89278353159b3f657c09cb44d38e`、seed `529716596879763`。`official_q4`、official INT8 + Q4、no-Turbo、`res_multistep` / `simple` / 20、864x480 / 24fps / raw 124f指定。開始 `2026-08-15T20:58:42.669+09:00`、成功 `2026-08-15T23:55:46.201+09:00`、2:57:03.532。 | `outputs/productions/CM_20260815_genai_mastery_15s/02_cuts/CUT01/candidate/CUT01_LATERAL_DOLLY_FL2VA_V3_00001_.mp4`、923,395 bytes、SHA-256 `7062BA522984DA2E30F27FD8718565CA82564697CFE9A54A5A5E73CC99BDDEB7`、H.264 High / yuv420p / 864x480 / 24fps / 124f / 5.166667秒 + AAC-LC stereo 32k / 5.167秒、full decode PASS、blackなし、speechなし。anchor PSNR 31.51 / 31.22、4人／8 barsは安定。`rendered_reviewed_unselected`。12.89% zoom-in+vertical drift、homography 76.6%、正しくないdepth parallax/occlusion reveal、face/hand/desk morph、rightmost bar clipping、4.416秒以降のnear-freezeにより独立評価でproduction reject。canonical CUT1・masterは不変で、比較用masterへの採用も行わない。 |

実行した各rowには、次を追記する。

- first frameのasset ID、ローカル相対path、SHA-256、権利・出典状態
- prompt全文のSHA-256、ComfyUI prompt ID、seed、各model名、profile、workflow SHA-256、実サーバーflags
- raw MP4の相対path、bytes、SHA-256、ffprobeのcodec / pixel format / fps / frame数 / duration / audio stream
- raw 124 framesのうち採用した120 framesと、余り4 framesの処置
- 生成開始・成功・失敗時刻、sampling時間、総時間、OOM/illegal access等の有無

## 4. 編集決定記録

| 項目 | 決定 / 実測 |
| --- | --- |
| 編集タイムライン | 24fps、360 frames、15.000秒 |
| 採用範囲 | CUT1 raw 0–119 → 00:00.000–00:05.000、CUT2 raw 0–119 → 00:05.000–00:10.000、CUT3 raw 0–119 → 00:10.000–00:15.000 |
| Transition | hard cutのみ。フェード、クロスディゾルブ、BGMなし |
| 台詞 | CUT2のみ `あなたも生成AIをマスターしませんか？`。native audioをfaster-whisper smallで確認し、masterではCUT2 local 0.62–3.90秒へ0.84秒前倒しで配置 |
| CUT1代替候補 | `CUT01_LATERAL_DOLLY_V1` は未選択。canonical CUT1およびmasterのartifact/hash/編集範囲は変更しない |
| CUT1 FL2VA V3実験 | `CUT01_LATERAL_DOLLY_FL2VA_V3` は完了後の独立評価でproduction reject。候補MP4はassembly対象外で、canonical CUT1およびmasterのartifact/hash/編集範囲は変更しない |
| Master artifact | `outputs/productions/CM_20260815_genai_mastery_15s/03_assembly/master/CM_20260815_genai_mastery_15s_master_864x480_24fps.mp4`、1,331,000 bytes、SHA-256 `CCB949E0D729B9AB5DE7D974EDB284CC0F69672DDEB607AC7851BE6317C9429D`、H.264 High / yuv420p / 864x480 / 24fps / 360f / 15.000秒 + AAC-LC 48kHz stereo、full decode PASS |

## 5. QC結果（実行後に記入）

| 確認項目 | 結果 / 根拠 |
| --- | --- |
| CUT1 wide・無言 | masterへ採用。minor hand/face softnessを記録。独立監査でvoice/musicなし |
| CUT01_LATERAL_DOLLY_V1（代替raw） | video/media stability、full decode、blackdetect、freezeはPASS。Truck RightはPARTIAL評価でFAIL（whole image約20–25 px左方向、弱い/逆転したnear/far parallax、occlusion revealなし）。gentle pan-like代替としてのみ記録し、未選択・master不変 |
| CUT01_LATERAL_DOLLY_FL2VA_V3（始終点実験） | full decode PASS、blackなし、speechなし、anchor PSNR 31.51 / 31.22、4人／8 bars安定。ただし12.89% zoom-in+vertical drift、homography 76.6%、正しくないdepth parallax/occlusion reveal、face/hand/desk morph、rightmost bar clipping、4.416秒以降のnear-freezeによりproduction reject。未選択・master不変。 |
| CUT2 close-up・唯一の指定台詞 | visual pass。faster-whisper small top 1と独立dictation top 2（近接confidence）で指定台詞を確認。audioを0.84秒前倒し後の残存lip sync差は概ね±0.25–0.3秒。rawのmild face/dental fluctuationを記録 |
| CUT3 wide・同じプレゼンター/着席者/会議室を維持したtext-free / logo-free / UI-free | visual pass。screenは終端まで動き続け、最終秒のprojection screenのminor deviationを記録。独立監査上blockerなし |
| BGMなし、CUT2以外の会話なし | masterのCUT1/CUT3はvoice/musicなし、CUT2は指定台詞のみ。BGM/room toneなしの意図的に静かなCM |
| 120 frames × 3、master 360 frames / 15.000秒 | PASS。hard cutはframe 120 / 240 |
| full decode / blackdetect / freeze / hard cut | raw 3本とmasterのfull decode PASS。独立監査でblackdetectなし、1秒超freezeなし、hard-cut境界はnatural。人間による聴取は主張しない |
| 素材の出典・権利・表示コピー承認 | ユーザー提供referenceと本CMの制作依頼は記録済み。公開・人物肖像・素材二次利用・モデル出力公開の独立確認は未完了 |

## 6. 成果物と境界

| 区分 | path / 状態 |
| --- | --- |
| 追跡する計画・記録 | `productions/CM_20260815_genai_mastery_15s/` |
| ignored raw / review / master | `outputs/productions/CM_20260815_genai_mastery_15s/` |
| 既存のarchitecture docs | 本計画では未変更 |
| 未検証 | 人物継続性・台詞品質・時間的一貫性の一般化、公開利用権 |

実生成を始める前に、`CUT_PLAN_JA.md` の生成前ゲートと `ASSET_PROVENANCE_JA.md` の未解決項目を承認する。
