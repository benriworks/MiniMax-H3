# 制作記録 — SHORT_20260828_ai_content_15s

## 1. 現在状態

| 項目 | 状態 |
| --- | --- |
| technical status | `complete_technical_pass`。3 rawと15秒masterは媒体、全復号、frame数、音声、black / freeze QCにPASS |
| creative status | `independent_visual_pass`。3 rawの4点contactとmasterの9点contact、2秒 / 7秒 / 12秒の原寸frameに加え、独立レビューで人物、手指、動作、fade、見出し、字幕、safe areaを確認 |
| public release status | `blocked_pending_rights_review` |
| final target | H.264 High / yuv420p / bt709、1080x1920、24fps、360 frames、15.000秒 + AAC-LC 48kHz stereo、BGMなし |

## 2. 内容

| Cut | 大見出し | ナレーション | 動作 |
| --- | --- | --- | --- |
| CUT01 | `その発信、届いてる？` | `その発信、本当に届いていますか？` | 横方向の視線をレンズへ移し、軽く眉を上げる。slow push-in |
| CUT02 | `生成AIで、伝わる企画へ` | `生成AIなら、企画をすぐ形にできます。` | 空いた手を一度だけ上げて右側を示す。slow truck right |
| CUT03 | `アイデアを、成果へ。` | `アイデアを、次の成果につなげよう。` | フォルダーを閉じ、手を下ろして笑顔になる。slow push-in |

ナレーションは`shorts_ja_large_preflight_v1`の表示幅上限38 unitsを事前検証し、16 / 19 / 17文字で通過した。正確な日本語はH3へ描画・発話させず、Studioで見出し、字幕、SAPIナレーションとして追加した。

## 3. H3 I2VA

| 項目 | 固定値 |
| --- | --- |
| Mode | FL2VA diffusion modelを使うI2VA first-frame-only |
| Runtime | ComfyUI 0.31.0、標準Dynamic VRAM、RTX 3070 Ti 8GiB |
| Model | official INT8 ConvRot diffusion + Q4 GGUF text encoder、no Turbo |
| Sampling | `res_multistep` / `simple` / 20 steps / denoise 1.0 / seed `529716596879763` |
| Native media | 480x864、24fps、124 frames、5.167秒、H.264 High + AAC-LC 32kHz stereo |

| Cut | prompt ID / elapsed | prompt / graph SHA-256 | raw / SHA-256 | 判定 |
| --- | --- | --- | --- | --- |
| CUT01 | `2337fa78-af40-4403-aaee-4ad57c400516` / 480.213秒 | `7527F86D51632D98424B9F711293AD69FDA8433D30438757FF25BB1D63FF007A` / `1560C6F1541D42CD3611C2D72866D4EECBF7C9781279C1EB49B36790E4379FE3` | `CUT01_00001_.mp4`、645,982 bytes / `CBAE760AA3995446A244A612CD2B70301A396DE69801784B40D8D62964F2E305` | full decode / visual contact PASS |
| CUT02 | `2460a022-d9b4-4af6-9861-18ac02c0f00e` / 450.147秒 | `BF3B94F7FAE6B38F27B4C4CDF906E783E4181BE48BC8BB0E5177D3B84FB6142C` / `A1AFFFD0DA14679975B0766B88D03BB892ED01D3D158758610FC7785AAA009CB` | `CUT02_00001_.mp4`、605,678 bytes / `9E79440CF5E47F116217D880E459BA568703B56C357BA0367AA1F10F92B7913A` | full decode / hand / visual contact PASS |
| CUT03 | `14a737de-b08e-4597-8a67-5fde39356a19` / 420.155秒 | `3FB21ED1E0C4440D5DD80343A111DB1E406C3F193B079BAD89CBEBCD68201E7D` / `475FC1A92681CBE03729DDB29C696D5E903C661E49FDB820BE3DE4EDAA962C83` | `CUT03_00001_.mp4`、863,045 bytes / `035AFEABF88EE0A4513AAD6397F0D6784C7AF34BBF2ED0C6440D053FA43CC716` | full decode / visual contact PASS |

3本の成功run合計は1,350.515秒、約22分31秒。最初に安全側のEmergency `--novram --cpu-vae`でCUT01を試したが、sampling完了後のCPU VAEが支配的だったため、MP4公開前の23分03秒時点でinterruptし、標準Dynamic VRAMへ切り替えた。Dynamic版は同じprompt / seed / modelで3本すべてOOMなしに完走した。中断attemptから採用artifactは作っていない。

## 4. Studio告知一括

| 項目 | 値 |
| --- | --- |
| recipe | `announcement_e7e70c73304a42a7a67e94ad84024f8e` revision 1 / `annv_20928281e8eb4708895b51e4f18edb20` |
| top job / run | `job_99fcc3f223324833979903438a0d0527` / `run_84988f2a370548b1b7011a7bc96239d1` |
| 実行 | 2026-08-28 17:44:18〜17:46:14 JST、約116.8秒 |
| pipeline | Windows SAPI → Remotion 3 clips / 250ms fade → FFmpeg assembly → technical QC |
| mix | `narration_only_v1`。3素材ともvolume 0%、BGMなし |
| caption | `shorts_ja_large_v1`、headlineはHOOK / CTA中央、MESSAGE上部、ナレーション字幕は下部safe area |
| result | child 4工程すべてsucceeded、cost 0、technical verdict PASS |

Studio masterは`master-captioned.mp4`、6,100,462 bytes、SHA-256 `7747400B9EF0F225A79233B66E6D9994A144810EF07AA4418F499DED83BEE3AF`。配信用copyでは画素・音声を再圧縮せず、H.264 VUIだけをbt709へ明示した。decoded video / audio hashがStudio masterと一致することを確認した。

## 5. Final master監査

| 項目 | 実測 / 判定 |
| --- | --- |
| delivery | `SHORT_20260828_ai_content_15s_delivery_captioned_1080x1920_24fps_bt709.mp4`、6,100,462 bytes、SHA-256 `3BCE7BB08EED7AF3E88EC916933EFB593EB4F123CCE6084CD2DB7E3BF191B27A` |
| media | H.264 High / yuv420p / bt709 / 1080x1920 / 24fps CFR / 360f / 15.000秒 + AAC-LC 48kHz stereo / 15.000秒 |
| decode / image | full decode PASS、black event 0、1秒超freeze 0、3 cuts / fades / identity / hands / headlines / subtitles / safe area independent visual PASS |
| audio | 非無音PASS、-17.48 LUFS-I / -3.81 dBTP / LRA 10.40。BGMなし、H3素材音なし |
| clean alternate | `SHORT_20260828_ai_content_15s_delivery_clean_1080x1920_24fps_bt709.mp4`、5,869,119 bytes、SHA-256 `B105CA02BE0609CA5F383082BDBC6A92C8334DCFC9C23B489D4E7083BC49C1B1`。見出し・字幕なし、同じSAPIナレーション |
| human gate | 人による通し試聴と公開権利確認は未実施 |

独立レビューでは、各rawを最大8fps相当、完成版を2fps相当のcontactで確認した。人物の顔・髪・衣装は3カットで一貫し、フォルダー保持、片手提示、フォルダーを閉じる動作にも明白な破綻や停止した後半はなかった。字幕は現行presetの左右96px安全域に収まる。ただし最長字幕は右端に比較的近いため、YouTubeの操作UIまで保守的に避ける場合は文言短縮または160px相当の再折り返しを推奨する。

`MASTER_FFPROBE.json`はbt709明示前のStudio中間masterを対象にするためbt470bgを報告する。配信用copyの実測色タグは`MASTER_INDEPENDENT_QC.json`に記録したbt709を正とし、画素・音声のdecoded hashは中間masterと一致している。

## 6. 境界

添付人物設定シートは外見参照だけに使い、氏名・年齢・居住地などの文字情報をID、prompt、recipe、masterへ複製していない。本タスク内の派生生成は依頼済みだが、人物が実在か合成か、被写体本人の同意、肖像・二次利用・YouTube公開権利は推測しない。技術完了と公開可否を分離する。
