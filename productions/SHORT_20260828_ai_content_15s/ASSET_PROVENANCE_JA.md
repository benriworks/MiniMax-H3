# 素材来歴 — SHORT_20260828_ai_content_15s

| Asset ID | 種別 / path | 出典 / 派生 | SHA-256 | 状態 |
| --- | --- | --- | --- | --- |
| `PRESENTER_PERSONA_PRIVATE` | `outputs/private-sources/SHORT_20260828_ai_content_15s/PERSONA_SHEET_ORIGINAL.jpg` | user-provided attachment。1078x1280、167,025 bytes。外見だけを参照 | `1C9AF56E8C1514257430913FF10ED8AB9D831BC2DE597B31183E5D397BCA5D7C` | private。公開権利未確認 |
| `CUT01_KEYFRAME_RAW` | `01_keyframes/CUT01_HOOK_RAW.png` | persona sheetからimagegenで生成 | `8066570DB5FE2E1CEDE9978276F04B207E606CA5F058D99659B2832CC8B74B66` | 941x1672 RGB、文字なしを目視確認 |
| `CUT01_KEYFRAME_RUNTIME` | `01_keyframes/CUT01_START_480x864.png` | RAWをLanczos scale-to-fill + center crop | `4271FC0F650EA69ED7C860603943EB3E3C6CFBAC3EB3B4A43E1CBAE669C4B7CF` | 480x864 RGB、H3 input |
| `CUT02_KEYFRAME_RAW` | `01_keyframes/CUT02_MESSAGE_RAW.png` | persona sheet + CUT01を参照してimagegenで生成 | `00B4515094649B731607613B6830D95A32994C095FE0F6FFA6C0EE27272772A9` | 941x1672 RGB、文字なしを目視確認 |
| `CUT02_KEYFRAME_RUNTIME` | `01_keyframes/CUT02_START_480x864.png` | RAWをLanczos scale-to-fill + center crop | `41E8147AEAFC3CA33DFCC0143DD34AA87A8A50D3A5F3E4967AB2BE1EB78BDC04` | 480x864 RGB、H3 input |
| `CUT03_KEYFRAME_RAW` | `01_keyframes/CUT03_CTA_RAW.png` | persona sheet + CUT01を参照してimagegenで生成 | `26E7C3F45FC6536B3BFC97F546982242FD187A19A72ED1A938B57D45425E936C` | 941x1672 RGB、文字なしを目視確認 |
| `CUT03_KEYFRAME_RUNTIME` | `01_keyframes/CUT03_START_480x864.png` | RAWをLanczos scale-to-fill + center crop | `D10C1CBC76707383EF839E8615B1DF142DBEE73DDAC313E844C5D15E5B6006D7` | 480x864 RGB、H3 input |
| `CUT01_H3_RAW` | `02_cuts/CUT01/candidate/CUT01_00001_.mp4` | CUT01 runtime画像からofficial INT8 + Q4 / Dynamic VRAM I2VA | `CBAE760AA3995446A244A612CD2B70301A396DE69801784B40D8D62964F2E305` | 645,982 bytes、480x864 / 24fps / 124f / 5.167秒、full decode / visual contact PASS |
| `CUT02_H3_RAW` | `02_cuts/CUT02/candidate/CUT02_00001_.mp4` | CUT02 runtime画像から同条件I2VA | `9E79440CF5E47F116217D880E459BA568703B56C357BA0367AA1F10F92B7913A` | 605,678 bytes、480x864 / 24fps / 124f / 5.167秒、full decode / visual contact PASS |
| `CUT03_H3_RAW` | `02_cuts/CUT03/candidate/CUT03_00001_.mp4` | CUT03 runtime画像から同条件I2VA | `035AFEABF88EE0A4513AAD6397F0D6784C7AF34BBF2ED0C6440D053FA43CC716` | 863,045 bytes、480x864 / 24fps / 124f / 5.167秒、full decode / visual contact PASS |
| `DELIVERY_CAPTIONED` | `03_assembly/master/SHORT_20260828_ai_content_15s_delivery_captioned_1080x1920_24fps_bt709.mp4` | 3 raw → Studio告知recipe → SAPI / Remotion / assembly / QC。Studio masterのH.264 VUIを無再圧縮でbt709明示 | `3BCE7BB08EED7AF3E88EC916933EFB593EB4F123CCE6084CD2DB7E3BF191B27A` | 6,100,462 bytes、1080x1920 / 24fps / 360f / 15秒 + AAC 48kHz、technical / visual contact PASS |
| `DELIVERY_CLEAN` | `03_assembly/master/SHORT_20260828_ai_content_15s_delivery_clean_1080x1920_24fps_bt709.mp4` | 同じraw / fade / SAPIナレーションから見出し・字幕だけを除外 | `B105CA02BE0609CA5F383082BDBC6A92C8334DCFC9C23B489D4E7083BC49C1B1` | 5,869,119 bytes、1080x1920 / 24fps / 15秒、full decode PASS |

imagegenの内部model/version/request IDは結果に公開されなかったため推測せず記録しない。source、生成画像、raw、QC素材、masterは`outputs/`配下のignored artifactとし、Gitへ追加しない。
