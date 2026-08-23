# CUT PLAN — CLAUDE.md 解説 15秒YouTube Short

## 1. 制作メタデータ

| 項目 | 内容 |
| --- | --- |
| Production ID | `SHORT_20260823_claude_md_15s` |
| 状態 | `complete_independently_reviewed`。3 rawと15秒masterはtechnical / creative PASS。ASRは3台詞を正順に各1回検出しphonetic semantic PASS。人による試聴と公開権利は別gate |
| 目的 | Claude Codeのプロジェクト指示ファイル`CLAUDE.md`を15秒で説明する縦型Short |
| 画面 / 尺 | native生成480x864。配信用masterは1080x1920へ拡大後に高解像度overlayを合成。9:16、24fps、3 cuts x 5.000秒、360 frames、hard cut |
| 音声 | H3 native Japanese speech、BGMなし。正確な表記は編集overlayで付ける |

## 2. 内容上の決定

元案の「一番大事」「ルートに置くだけで毎回自動で読む設定ファイル」は、短尺のフックと公式仕様を両立するため、次の表現へ調整する。

- フック: `Claude Codeの重要ファイル、知ってる？`
- 核心: `CLAUDE.md。開始時に読む指示です。`
- 利点 / CTA: `規約を書けば、指示が減る。フォローしてね。`

`CLAUDE.md`は強制設定ではなくClaudeへ与えるプロジェクト指示として扱う。プロジェクト指示は`./CLAUDE.md`または`./.claude/CLAUDE.md`に置け、起動時に読み込まれる。親ディレクトリの指示も対象となり、子ディレクトリの指示は必要時に読み込まれる。出典はAnthropic公式ドキュメント `https://code.claude.com/docs/en/memory` とする。

## 3. 固定した生成設定

| 項目 | 値 |
| --- | --- |
| Mode | 3 cutともFL2VA diffusion modelを使うI2VA first-frame-only |
| Profile | `official_q4` |
| Diffusion | `minimax_h3_fl2va_pruned_int8_convrot.safetensors` |
| Text encoder | `qwen3vl-32B-MiniMax-H3-Q4_K_M.gguf` |
| Turbo / last frame | なし / なし |
| Sampler / scheduler / steps | `res_multistep` / `simple` / 20 |
| Denoise / seed | 1.00 / `529716596879763` |
| Resolution | `9:16 (Portrait Widescreen)` / 0.4MP / multiple 32 = 480x864 |
| Raw | 5.0秒指定、24fps。17-frame gridにより124 frames / 約5.1667秒を見込む |
| 採用範囲 | 各rawのframes 0-119を採用し、3 x 120 = 360 framesへ統一 |

縦型official INT8 + Q4は、CUT01をvalidation renderとして確認後にCUT02/CUT03を直列生成した。3 rawとも480x864 / 24fps / 124 frames / 約5.1667秒、H.264 High + AAC-LCでfull decode PASSとなった。

## 4. カット表

| Cut / master frames | 画・動き | 台詞 | Overlay |
| --- | --- | --- | --- |
| CUT01 / 0-119 | 中央正面。小振幅slow push-in、軽い眉上げ、1回の小さな首傾げとblink | `クロード・コードの重要ファイル、知ってる？` | `Claude Code`、`重要ファイル、知ってる？` |
| CUT02 / 120-239 | 女性は画面左、右手のopen palmで空き領域を1回紹介。終盤に小さく頷く | `クロード・エムディー。開始時に読む指示です。` | 大見出し`CLAUDE.md`、補足`セッション開始時に読み込み` |
| CUT03 / 240-359 | 女性は画面右、左手のopen palmで図解領域を1回紹介し、終盤は穏やかな笑顔 | `規約を書けば、指示が減る。フォローしてね。` | フォルダ図、`コーディング規約`、`設計方針`、`続きはプロフィールから` |

生成文字・ロゴ・UIはH3へ描かせない。Overlayは編集で正確に合成し、字幕はShortのUI safe area内へ置く。

## 5. 合格条件

- [x] ユーザー提供画像を保存し、bytes / SHA-256 / 寸法を記録した。
- [x] imagegenで同一人物の縦型始点3枚を作り、480x864 RGBへ正規化・視覚確認した。
- [x] 3 rawがofficial INT8 + Q4 / no-Turbo / 20 stepsで成功し、各124 framesある。
- [x] 台詞が各cutで一度だけ発話され、余計な発話・音楽がない。faster-whisper smallは3台詞を正順に各1回検出した。CUT03冒頭は同音異表記となるため、厳密文字一致ではなくphonetic semantic PASSとする。
- [x] 顔、眼鏡、歯、唇、手指、袖に重大なmorph / flickerがない。
- [x] 各raw先頭120 framesを1080x1920へ拡大し、高解像度overlayを合成した24fps / 360 frames / 15.000秒masterを作った。native生成ではないupscaleである。
- [x] masterのfull decode、blackdetect、1秒超freeze、音声、字幕safe area、hard-cut境界を独立確認した。
- [ ] 公開前に人物画像、派生物、ブランド表現、YouTube公開の権利を確認する。

CUT01 rawのfaster-whisper small発話窓は1.26–4.24秒だった。最初の微小な口動きだけにonsetを合わせず、正しいmouth cropの24fps差分と48kHz / 24fps RMS envelopeを相互相関した。audioはvisualより3–6 frames遅く、masterでは保守的に3 frames / 0.125秒だけ前倒しする。音声だけのstretchは行わない。slow push-inにより上部大見出しが髪へ近づくため、大見出しだけを3.25–3.70秒でfade-outし、`Claude Code`タグは終盤まで残す。発話字幕は0.95–1.08秒でfade-in、4.22–4.42秒でfade-outし、末尾0.58秒は表情だけを残す。

CUT02 faster-whisper small発話窓は0.34–3.96秒で、`クロードMD 開始時に読む指示です。`を1回検出した。mouth差分とaudio envelopeの相互相関は4/5 cropでlag 0 framesのため、audio shiftは0とする。active speechはCUT01より4.02dB大きいためCUT02へ固定`-4.0dB`を適用し、cut別dynamic処理は行わない。Cardはlocal 0.12–0.32秒fade-in / 4.55–4.75秒fade-out、字幕は0.22–0.34秒fade-in / 4.08–4.30秒fade-outとする。

CUT03はtechnical / creative PASS。顔・丸眼鏡・衣装・5本指・袖/手首を維持し、後半に単一の提示arcと柔らかい笑顔が成立した。faster-whisper smallは目標文を1回だけ検出し、`企薬/規約`、`かけば/書けば`が同音異表記となったためphonetic semantic PASS、厳密文字一致はFAILと記録する。口形相関に基づきaudioを5 frames / 0.208333秒前倒しし、active speechを揃えるため固定`-1.6dB`を適用した。

完成masterは`SHORT_20260823_claude_md_15s_master_1080x1920_24fps.mp4`。1080x1920 / 24fps CFR / 360 frames / 15.000秒、H.264 High yuv420p bt709 + AAC-LC 48kHz stereoで、full decode、blackdetect、1秒超freeze、PTS、hard-cut、字幕safe area、人物・手指、ASR、音声境界を独立確認した。AAC後は-15.86 LUFS-I / -3.24dBTP / LRA 2.40、clip / NaN / Infなし。人による通し試聴と公開権利確認は未実施である。
