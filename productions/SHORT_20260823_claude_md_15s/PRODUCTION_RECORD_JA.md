# 制作記録 — SHORT_20260823_claude_md_15s

## 1. 現在状態

| 項目 | 状態 |
| --- | --- |
| technical status | `complete_independently_reviewed`。3 rawと15秒masterは媒体・全復号・PTS・black / freeze / hard-cut・音声QC PASS |
| creative status | 3 cutの人物・眼鏡・口元・手指・動作、post overlay、Shorts safe areaを独立確認しPASS。ASRは3台詞を正順に各1回検出しphonetic semantic PASS |
| public release status | `blocked_pending_rights_review` |
| final target | 1080x1920 delivery master、24fps、360 frames、15.000秒、H.264 High / yuv420p + AAC-LC 48kHz、BGMなし。映像は480x864 native rawからのupscale |

## 2. 実行環境

| 項目 | 実測 / 固定値 |
| --- | --- |
| ComfyUI | 0.31.0、`http://127.0.0.1:8188` |
| server flags | `--novram --cpu-vae --disable-pinned-memory --preview-method none` |
| GPU | NVIDIA GeForce RTX 3070 Ti 8GiB |
| runtime revisions | ComfyUI `2a68ce33b4c9ea6ee4283e618a74560cefb32694`、ComfyUI-GGUF `6ea2651e7df66d7585f6ffee804b20e92fb38b8a` |
| base graph | 日本語発話成功履歴 prompt ID `714eaf57-e1df-4900-9d0f-4698606de953` を複製し、入力画像・prompt・縦解像度・出力prefixだけを変更する |
| model / sampling | official INT8 ConvRot + Q4 GGUF、no-Turbo、`res_multistep` / `simple` / 20、denoise 1.00 |
| resolution / duration | 480x864、24fps、5.0秒指定、raw 124 frames見込み |

実行開始時はhost free RAM約8.2GiBで、ComfyUI private memory約18.6GiBだった。生成は必ず1件ずつ直列化する。過去の同条件0.4MP実績は約3時間/cutであり、3 cut合計は約9時間を見込む。

## 3. Cut台帳

| Cut | first frame / prompt | prompt ID / graph hash / 時間 | raw artifact / probe / hash | 採否 |
| --- | --- | --- | --- | --- |
| CUT01 | `CUT01_START_480x864.png` / `prompts/CUT01_H3.md` | prompt ID `0ed57604-3e45-4661-922b-2ccccf74fc37`、number 13、seed `529716596879763`、submitted prompt SHA-256 `2DF6A249C8DE9CD515200116869AC9CA2A51757B514A48A7FA951FE1FC2ECE4C`、graph SHA-256 `8FCBFB31061BB9FC60C36903860145D1187E9208DE2A901271E2BD9EF4930D09`、`2026-08-23T01:56:32.963+09:00`–`04:50:39.270+09:00`、2:54:06.307 | `CUT01_00001_.mp4`、693,470 bytes、SHA-256 `C2E7861FFD0327D3475F23C5DE18BB48506D302E533751784902DDD3B6FEF209`、H.264 High / yuv420p / 480x864 / 24fps / 124f / 5.166667秒 + AAC-LC 32kHz stereo、full decode PASS | technical / visual / ASR PASS。顔・眼鏡・衣装は安定し、slow push-in成立。faster-whisper smallは1.26–4.24秒に`クロードコードの重要ファイル 知ってる?`を1回検出。mouth差分とaudio envelopeの相互相関はaudioが3–6f遅れたため、masterでは保守的に3f / 0.125秒だけ前倒しする。上部大見出しは3.25–3.70秒でfade-outして髪との接触を防ぐ |
| CUT02 | `CUT02_START_480x864.png` / `prompts/CUT02_H3.md` | prompt ID `65eed5d3-7343-4766-8ae5-beaaa58295be`、number 14、seed `529716596879763`、submitted prompt / file SHA-256 `30D2B60E95D89C3F8F08C19F884BAD4B9A34BB73814ABD3A5BEDC92969A26DC9`、graph SHA-256 `B07FF70BA97B3BD6E1F313C2FD87792B34DC84333F0D06F1B89167108BC7A7F2`、`2026-08-23T04:51:57.435+09:00`–`07:43:57.771+09:00`、2:52:00.336 | `CUT02_00001_.mp4`、570,088 bytes、SHA-256 `7A773C44F1D4FAEDE285FB4FB651BF12E0FAEF365775F041D4C00C3DCE55BF64`、H.264 High / yuv420p / 480x864 / 24fps / 124f / 5.166667秒 + AAC-LC 32kHz stereo、full decode PASS | technical / creative / ASR PASS。faster-whisper smallは0.34–3.96秒に`クロードMD 開始時に読む指示です。`を1回検出。手指5本、open-palm回転、袖/手首、眼鏡は安定。lip-sync lag 0f、audio shiftなし。CUT01よりactive speechが4.02dB大きいためfixed gain -4.0dB |
| CUT03 | `CUT03_START_480x864.png` / `prompts/CUT03_H3.md` | prompt ID `f01de037-d13b-4010-bd18-651f07efd327`、number 15、seed `529716596879763`、submitted prompt / file SHA-256 `F725BA5168639659EC1A890C5FED15B7EE80E5D05D3CE0B1F10BA2ABA5F085F0`、graph SHA-256 `04715FED0795820F3A0D4D76355CCC07BC144BBFBD32BDF09391CEC63D9870AE`、`2026-08-23T07:45:53.284+09:00`–`10:37:57.058+09:00`、2:52:03.774 | `CUT03_00001_.mp4`、550,054 bytes、SHA-256 `1245C1204E122535959A7609450D37E13A3D94AB37764D7D9E48044633D059A6`、H.264 High / yuv420p / 480x864 / 24fps / 124f / 5.166667秒 + AAC-LC 32kHz stereo、full decode PASS | technical / creative / phonetic semantic PASS。顔・眼鏡・衣装・5本指・袖/手首は安定し、単一の提示arcと終盤の笑顔が成立。ASRは0.02–3.92秒に目標文を1回検出したが`企薬/規約`、`かけば/書けば`は同音異表記のためstrict orthographic FAIL / phonetic PASS。lip-syncはaudioを5f / 0.208333秒前倒し、固定gain -1.6dB |

3 rawはすべて実在artifact、prompt file / submitted prompt / accepted graph hash、prompt ID、seed、開始/終了時刻、所要時間、bytes / hash、媒体、full decode、ASR、顔・手・lip-sync・motion coverage、採否理由まで固定した。生成は1件ずつ直列化し、CUT03の高メモリ段階ではfree RAM最小観測1.24GiBだったが、OOM / exceptionなしで完了し、直後は約29.13GiBまで回復した。

## 4. 編集結果

- 各rawの先頭120 framesを採用し、hard cutをmaster frames 120 / 240に置いた。
- H3 native speechはCUT01を3f / 0.125秒、CUT03を5f / 0.208333秒前倒し、CUT02はshiftなしとした。active speechを揃える固定gainはCUT01 0dB、CUT02 -4.0dB、CUT03 -1.6dB。
- 3 cutを各240,000 samplesへそろえ、15秒 / 720,000 samplesのPCM f32 audio masterを作った。`SHORT_20260823_claude_md_15s_audio_master_f32.wav`は5,760,092 bytes、SHA-256 `75FCED3EE9F13B3E8FB201AE7131378B9A426028A6569F360AEDFB55009C383E`、48kHz stereo / 15.000秒。2-pass loudnorm後のPCMは-16.0 LUFS-I / true peak約-3.3dBTP、NaN / Inf / clipなし。
- 480x864 rawを1080x1920へLanczos拡大後、`CLAUDE.md`、フォルダ図、説明、CTA、字幕を1080x1920 post overlayとして合成した。CUT03は図解 / 通常字幕をlocal 2.92秒までに消し、CTAを2.72–4.82秒でfadeした。約0.20秒の情報crossfadeはあるが独立creative QCでPASS。
- final masterは`outputs/productions/SHORT_20260823_claude_md_15s/03_assembly/master/SHORT_20260823_claude_md_15s_master_1080x1920_24fps.mp4`。
- ASRは補助証拠であり、最終的な日本語の自然さ・声質連続性を人が通し試聴したとは主張しない。

Overlay layoutの静止確認とtiming検証用として、始点3枚だけを使った`SHORT_20260823_claude_md_15s_storyboard_1080x1920.mp4`を生成した。これは1,273,423 bytes、SHA-256 `6A80FFA7555747CFD746EBCAE009327A4DE91BACCF09BEF9FB681DAC68AABA4B`、360 frames / 15.000秒 / H.264 High + silent AACのpreviewであり、H3 raw未使用のためfinal masterではない。

独立creative QCの初回指摘では、字幕帯がShorts下部UI領域に近いことをblockerとした。字幕を`x=72–928 / y=1390–1540`へ上げ、CUT01上部copy、CUT02 cardをsafe areaへ調整した。storyboardではCUT03の13.25秒で図解と通常字幕を消し、`x=150–900 / y=1200–1430`の2行CTAだけを残す案を検証した。更新後storyboardの1秒刻み確認でsafe-area blocker解消 / PASSを確認し、final masterでは同じ座標を維持して実発話にtimingを合わせた。

finalでは発話と手の実測に合わせ、CUT03の図解 / 通常字幕はglobal 12.92秒までにfade-out、CTAはglobal 12.72–14.82秒でfadeした。図解とCTAは約0.20秒crossfadeするが、顔・口・手を隠さずsafe area内で、独立creative QCはPASSとした。

## 5. Final master監査

| 項目 | 実測 / 判定 |
| --- | --- |
| artifact | `SHORT_20260823_claude_md_15s_master_1080x1920_24fps.mp4`、5,805,862 bytes、SHA-256 `BE62CC00B76DE0398638184D47DFF326E2C30BF96B051B6FFCF2FD08939D2055` |
| clean alternate | `SHORT_20260823_claude_md_15s_clean_no_overlays_1080x1920_24fps.mp4`、5,931,492 bytes、SHA-256 `1BDD0C4937A76E56E2F417545CA8ADA45763EB4BA559DA29ED7243DA28E95893`。全post overlay（見出し、字幕、カード、図解、CTA）を外し、同じraw 120f x 3、hard cut、補正済みaudio masterを使用 |
| media | H.264 High / yuv420p / bt709 / 1080x1920 / SAR 1:1 / 24fps CFR / 360f / 15.000秒 + AAC-LC 48kHz stereo / 15.000秒 |
| decode / timing | full decode PASS。frame PTSは0–359で全delta 1/24秒。VFRなし。AAC priming後のaudible startは0、最終packet end 15.000秒 |
| image QC | black event 0、1秒超freeze 0、flash / corruption 0。hard cut f119→120 / f239→240にgap・黒・混在frameなし |
| creative QC | identity、眼鏡、口元、歯、5本指、袖/手首、3種の動き、overlay可読性、Shorts safe area、CTAを独立確認しPASS |
| audio QC | -15.86 LUFS-I / -3.24dBTP / LRA 2.40、NaN / Inf / denormal / clipなし。5秒 / 10秒境界にclick兆候なし |
| lip-sync | master上の口元差分とaudio envelopeはCUT01/02/03すべてpeak lag 0f |
| ASR | 3論理台詞を正順に各1回検出、余計な発話なし。CUT01 exact、CUT02はcut単独exact / 通しで`開始時期`と揺れ、CUT03は同音異表記。総合phonetic semantic PASS、strict orthographic exactとはしない |
| remaining gate | 人による通し試聴、人物画像と派生物、model output、ブランド表現、YouTube公開の権利確認 |

clean alternateも1080x1920 / 24fps CFR / 360f / 15.000秒、映像・音声ともfull decode PASS、black event 0、1秒超freeze 0。1秒刻みcontactで生成文字・post overlayがないことを確認した。音声はoverlay版と同一のため、lip-sync、ASR、loudnessの監査結果を共有する。

## 6. 境界

ローカルpreview生成の依頼は確認済みだが、添付人物が実在か合成か、被写体本人の同意、肖像・二次利用・YouTube公開権利は推測しない。`Claude Code` / `CLAUDE.md`は説明上の文字だけを後編集し、Anthropicロゴや製品UIは使わない。technical / creative / public releaseの判定を分離する。
