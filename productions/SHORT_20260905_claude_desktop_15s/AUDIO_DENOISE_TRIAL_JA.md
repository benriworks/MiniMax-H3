# Harukaの発話中ノイズ — 非破壊の音声処理比較

実施日: 2026-09-05

## 依頼と診断の境界

利用者の聴取で「すべての発話中にジリジリ音がする」「声がクリーンに聞こえない」と報告された。前回のtechnical QC / visual PASSは、聴感上の無ノイズや公開品質を保証しない。声はMiniMaxではなくWindows SAPIのMicrosoft Haruka Desktopである。

元PCMの区間とscheduled WAVは一致し、編集継ぎ目はゼロ同士、数値上のクリッピングも見つからなかった。固定した50/60Hzハムや発話中に持続する狭帯域線の強い根拠もない。音声合成の倍音・ざらつきとノイズの分離は未確定であり、Haruka一般に必ず生じる不具合とは断定しない。

無音区間はデジタルゼロなので、それを「ジリジリ音のノイズ見本」として学習させない。単発クリックの除去ではなく、控えめなFFTノイズ低減と高域EQを試す。フィルターのnoise floorは試聴用の仮定であり、測定されたノイズ床ではない。

## 原本を守る処理

`denoise.py`は既存の未圧縮`narration.wav`を入力にし、元MP4のAACから音を作り直さない。既知のWAV・MP4 SHA-256に一致しない場合は停止し、出力はtimestamp付きの別ディレクトリへ作成する。

1. 元WAVを48kHz monoへ変換し15秒へ無音padding。
2. 対照版、軽め、強めを独立に処理。
3. PCM相互相関で固定処理遅延を測定・補正。今回軽め1197sample / 24.9375ms、強め1199sample / 24.9792ms。単語単位の位置合わせやリップシンクではない。
4. 動的コンプレッサーは使わず、一定gainで3版のIntegratedを-18.0 LUFSへ揃える。単に音量が小さいから良く聞こえる比較を避ける。
5. 元字幕版の映像は`-c:v copy`でコピーし、処理WAVからAAC 192kbpsへ1回だけ圧縮する。映像・テロップ・タイミングは変更しない。
6. 元ファイルのhash不変、映像payload同一、15秒・360frame・全decode・音量・peakを検証する。

既存Studioの標準音声workerや字幕assemblyは変更しない。試聴前に全制作の既定値へ採用しない。新しい通常Run / Job / 承認履歴も作成しない。インターネット、有料API、新しい音声生成は使わない。

## 比較レシピ

| 版 | 目的 | 固定処理 |
| --- | --- | --- |
| control | 原音の対照。ノイズ除去なし | resample、padding、音量揃えのみ |
| mild | まず試す軽めの候補 | 60Hz highpass、`afftdn=nr=6:nf=-45:tn=0:gs=8`、3.5kHzの高域shelf -2dB |
| strong | 効果と声質のトレードオフを確認 | 60Hz highpass、`afftdn=nr=10:nf=-38:tn=0:gs=12`、3kHzの高域shelf -4dB、6.5kHz lowpass |

完全なfilter文字列、入力・出力hash、FFmpeg version、波形の遅延・音量・帯域energyは実行manifestへ保存する。`afftdn`の`gs`は周波数binごとのgainを平滑化する設定、`tn=0`はnoise trackingを無効にする設定。[FFmpeg公式のFFTノイズ低減](https://ffmpeg.org/ffmpeg-filters.html#afftdn)、[高域EQ](https://ffmpeg.org/ffmpeg-filters.html#treble_002c-highshelf)、[lowpass](https://ffmpeg.org/ffmpeg-filters.html#lowpass)を参照。

## 出力と確認

実行先: `outputs/productions/SHORT_20260905_claude_desktop_15s/denoise/20260905T064901801559Z/`

| 成果物 | 内容 |
| --- | --- |
| `ClaudeCode_desktop_15s_mild.mp4` | 軽めの処理、字幕付き15秒 |
| `ClaudeCode_desktop_15s_strong.mp4` | 強めの処理、字幕付き15秒 |
| `ClaudeCode_desktop_15s_control.mp4` | 同じ音量とAAC条件の原音対照版 |
| `narration_control.wav` / `narration_mild.wav` / `narration_strong.wav` | 各15秒の非圧縮音声 |
| `comparison_original_mild_strong.wav` | 同じ結びの2文を「原音対照 → 軽め → 強め」で聴き比べる約13.6秒 |
| `manifest.json` / `probe-*.json` | 完全な条件・計測・hash・来歴 |

聴き比べは0〜4.30秒が原音対照、4.65〜8.95秒が軽め、9.30〜13.60秒が強め。各回の間は350msの無音。比較用抜粋の端だけ10ms fadeを追加し、抜粋によるクリックを避ける。対照版も音量揃え・resampleをしており、元WAVと同一bytesではない。

3動画すべて15.000秒、1080×1920、24fps / 360frame、H.264映像copy＋AAC音声、全decode成功。Integrated -18.0 LUFSで一致、true peakはcontrol -5.0 / mild -5.1 / strong -5.0 dBFS。元MP4の映像payload hashは3版とも同一。

別担当の独立検査でも、360個すべての映像packet payloadとPTS／DTS／duration／size／flags、H.264 extradataが原版と完全一致した。AACのfloat PCMに非有限値・クリッピングはなく、原executionのcaptioned／clean／WAV／manifestおよび元納品captionedのhash不変を確認した。

音声の独立検査では全体と6発話区間ごとの残差ずれが両候補とも0ms。対照音声で-40dBFSを超える10ms窓613個のうち、候補で-60dBFS未満または20dB超低下した窓は0だった。比較WAVの3区間は元候補sliceと一致し、区間間gapはゼロ。ただし、これらも単語の明瞭さやノイズ消失の聴感保証ではない。

4〜8kHzの帯域energyは音量揃え後の対照比で軽め約-3.12dB、強め約-8.91dB。**これは声とノイズを合わせた帯域の減少であって、ジリジリ音だけを除去できた証拠ではない。** 低〜中域の倍音由来であれば、この処理で十分改善しない可能性がある。

状態: 処理と技術検査は成功。ノイズ軽減の聴感・発音の明瞭さは利用者によるA/B確認待ち。音声を実際に聴取した、ASRで検証した、ノイズが完全に消えた、とは扱わない。強めは子音や声の明るさが減り、こもって聞こえる可能性がある。

再実行:

```powershell
.venv\Scripts\python.exe productions/SHORT_20260905_claude_desktop_15s/denoise.py
```

MP4 SHA-256:

- mild: `7D9BB776097943E9C12E96072D59FBF3362A0A716991269C4F7D2A30B7EAFB5A`
- strong: `AE55695FDAD0F4529A2140CC4511E010D5E12C0089828E76F585298F810BE8CF`
- control: `3E6CC4A17CB751BD1750D0288B90304147FCA7365238F38F40C37F0D2B60A4C0`
