# 素材出典・利用状態 — CM_20260815_genai_mastery_15s

## 1. 方針

ユーザーはこのCMのためのプレゼンターreferenceを提供し、本CM制作を明示的に依頼した。そこからCUT1/CUT2のfirst frameを生成し、CUT1 wideを編集してCUT3のfirst frameを作成した。first frameは視覚レビュー済みである。加えてCUT1のFL2VA V3実験用に終点画像を生成したが、独立endpoint QCでproduction no-goとした。これは本タスク内の制作許可の記録であり、公開、広告出稿、人物肖像、素材の二次利用、**model outputの公開・配信**の権利を独立して確認したものではない。

人物・ロゴ・UI・固有の会場・資料を、提供・派生した範囲を超えて推測または模倣して補わない。CUT3のAI visualは、同じプレゼンター・着席者・会議室を保ちつつ、投影面をtext-freeの抽象AI visualへ変更する。読める文字、ロゴ、実在製品UI、商標を含めない。

## 2. 素材台帳

| Asset ID | 用途 | 予定path | 出典 / 権利状態 | hash | 現在状態 |
| --- | --- | --- | --- | --- | --- |
| `PRESENTER_REFERENCE` | CUT1/CUT2 keyframeの人物reference | `outputs/productions/CM_20260815_genai_mastery_15s/00_source/presenter_reference.jpg` | 2026-08-15にユーザーが本CM用に提供。公開・人物肖像・二次利用・model output公開の権利は独立未確認 | `64b7819b8d9ec9ef7a143ed9b7fce832f04a43ebc8990b5c578de8029e841263` | user-provided / task-use requested |
| `PRESENTER_01_WIDE` | CUT1のI2VA first frame。プレゼンターと会場のwide | `outputs/productions/CM_20260815_genai_mastery_15s/01_keyframes/CUT01_head_864x480.png` | `PRESENTER_REFERENCE`を用いた画像生成後、ffmpegで864x480へcrop/scale。公開・人物肖像・二次利用・model output公開の権利は独立未確認 | `e9b230be961a5ab20047610283d61bb554811c7ac09558fc1f2304c1d09a4e27` | generated and visually reviewed |
| `PRESENTER_01_CLOSE` | CUT2のI2VA first frame。同じプレゼンター・衣装・照明を維持する | `outputs/productions/CM_20260815_genai_mastery_15s/01_keyframes/CUT02_head_864x480.png` | `PRESENTER_REFERENCE`を用いた画像生成後、ffmpegで864x480へcrop/scale。公開・人物肖像・二次利用・model output公開の権利は独立未確認 | `a65b2af7f19112a90c7c39e92ac861b25ded4a9c2c357fbc0f604919faac5efe` | generated and visually reviewed |
| `AI_VISUAL_WIDE` | CUT3のI2VA first frame。同じプレゼンター・着席者・会議室を維持したtext-free AI visual | `outputs/productions/CM_20260815_genai_mastery_15s/01_keyframes/CUT03_head_864x480.png` | CUT1 wideをOpenAI image editし、投影面をtext-free abstract AI visualへ変更後、ffmpegで864x480へcrop/scale。公開・人物肖像・二次利用・model output公開の権利は独立未確認 | `59acf4dcb9a5df36a47d78c2e3bf653221ab4ced4241bd81a8d05591382442e8` | generated and visually reviewed |
| `CUT01_FL2VA_V3_TAIL` | CUT1 FL2VA V3実験のlast-frame endpoint | `outputs/productions/CM_20260815_genai_mastery_15s/01_keyframes/CUT01_FL2VA_V3_tail_864x480.png` | built-in identity-preserve image editの第3反復後、864x480へcrop/scale。rawは1,739,214 bytes / SHA-256 `EF7D8C971AC8D9994615F583893335A892CC86393A9E8E1CA3E02014A237A171`、runtimeは513,616 bytes / SHA-256 `93499A89053546FD0BA45216D12560ECE647D70B28AD293C86F360DA4CCB812C`。公開・人物肖像・二次利用・model output公開の権利は独立未確認 | `93499A89053546FD0BA45216D12560ECE647D70B28AD293C86F360DA4CCB812C` | experimental-only / production no-go（bar edge、人物位置の不整合、table/handsの縦方向変化、face difference） |
| `DIALOGUE_01` | CUT2の唯一の台詞 | 計画本文と`prompts/CUT02_H3.md` | ユーザー指定文言。faster-whisper smallのtop 1と独立dictationのtop 2（近接confidence）で確認。人間による聴取、公開時の表現承認・model output公開は主張しない | N/A | generated / technically audited / independently unapproved for publication |

raw keyframe、runtime keyframeの両方の相対path、byte数、SHA-256、派生方法は `manifests/source-hashes.json` に固定する。本表はruntime keyframeを代表pathとして示す。

## 3. 表示コピー・ブランド資産

| 要素 | 計画上の扱い | 状態 |
| --- | --- | --- |
| ロゴ / wordmark | 使用しない。必要になった場合は正規の元データと使用規定を登録する | 未使用 |
| 製品UI / スクリーンショット | 使用しない。未許可の模倣UIも使わない | 未使用 |
| 画面内テキスト / CTA | 使用しない。CUT3はtext-free、logo-free、UI-freeを必須とし、同じプレゼンター・着席者の表示は許容する | 未使用 |
| 数値・性能主張 | 使用しない。検証できない主張を生成しない | 未使用 |
| 台詞 | CUT2でのみ `あなたも生成AIをマスターしませんか？` | 承認待ち |

## 4. 生成承認前の確認

- [x] ユーザーがreferenceを提供し、本CM制作を明示的に依頼した。reference・3枚のraw/runtime keyframeのpathとhashを `source-hashes.json` に記入した。
- [x] CUT1/CUT2/CUT3のruntime keyframeを視覚レビューした。これは動画品質・人物継続性の最終合格ではない。
- [x] CUT3 first frameがtext-free、logo-free、UI-freeであり、同じプレゼンター・着席者・会議室を意図して維持することを確認した。
- [x] CUT1 FL2VA V3用の終点画像のraw/runtime path、bytes、SHA-256、派生方法を記録した。bar edge、人物位置の不整合、table/handsの縦方向変化、face differenceによりexperimental-only / production no-goとし、canonical素材には採用しない。
- [x] `CUT01_LATERAL_DOLLY_FL2VA_V3` の候補MP4を確認した。full decode PASS、blackなし、speechなし、anchor PSNR 31.51 / 31.22、4人／8 bars安定だったが、12.89% zoom-in+vertical drift、homography 76.6%、正しくないdepth parallax/occlusion reveal、face/hand/desk morph、rightmost bar clipping、4.416秒以降のnear-freezeによりindependent production rejectとし、canonical素材・masterには採用しない。
- [x] CUT2のnative audioで指定台詞をfaster-whisper smallのtop 1と独立dictationのtop 2（近接confidence）により確認し、masterではCUT2 local 0.62–3.90秒に配置した。これは人間による聴取や公開用の表現承認ではない。
- [ ] 公開先・対象者・人物肖像・素材二次利用・モデル出力公開に必要な権利を独立確認する。
- [ ] 実生成した各MP4のpath、hash、probe、品質確認結果を制作記録に追記する。

この台帳は出典を記録するものであり、単独で公開・商用利用の権利を付与するものではない。
