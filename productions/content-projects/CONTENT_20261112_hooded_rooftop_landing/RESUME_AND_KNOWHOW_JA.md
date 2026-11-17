# 「灰の街」制作の再開記録

2026-11-17更新。案件IDは `CONTENT_20261112_hooded_rooftop_landing`。

## 現在地

2026-11-17更新。

- **最新版は v08（科学者の最期版）** `review/full-179s-v08-lastwords/haino-machi-full-179s-v08-lastwords-score.mp4`（2分59秒＝179.000秒、4,296フレーム、−17.1 LUFS）。ユーザーの依頼で2026-11-17にS3へアップロード済み（ArtifactId 6103365eb81a4ffeb68a5144ea4a257a、保存7日）。YouTubeの設定案は `youtube-v08-lastwords.txt`。投稿はユーザーが行う。
- 別版のメール版v08 `review/full-179s-v08-email/haino-machi-full-179s-v08-email-score.mp4` と、それ以前の版（v01〜v07）もすべて残してある。
- 採用済み: 題名と設定、ニュースのアナウンサー音声、時間のテロップ（1:00「3日前」、2:00「現在」）、ユーザーが用意したスコア `audio/score-full-v01/hai-no-machi-full-score-v01.wav`、2-7はフードのずれを直さない。
- 作り方と学びは [静止画から作る短編アクションドラマのノウハウ](../../../docs/video-production/H3_ACTION_DRAMA_KNOWHOW_JA.md)。時系列の詳しいログは同じフォルダーの `RESUME_JA.md`、全カットはメディアルートの `CUTS_CATALOG_JA.md`（110本）。
- v08の再出力: `assemble_sequence.py --version <名前>-raw --cuts <36個のID>`（並びは `review/full-180s-v06-raw/render.json`）→ `add_news.py --start 90 --bed-levels 0,0.3,0.3` → `add_titles.py --title 60.3 3日前 --title 120.3 現在` → 科学者の台詞（`audio/s4-lastwords/part1.wav` を161.2秒、`part2.wav` を165.3秒）とスコアを重ね、160〜170秒の元の音は0 → 160〜161秒の1秒を抜く。コマンドの全文は `RESUME_JA.md` の v05〜v08 の項。
- 下のループBGM v01は試作に使っただけで、最終版には入っていない。
## ループBGM v01

低い弦、まばらな弱音ピアノ、心拍のような低音を指定した、歌のないサスペンス曲。配下のパスはメディアルート `outputs/content-projects/CONTENT_20261112_hooded_rooftop_landing/` からの相対位置。

| 項目 | 記録 |
| --- | --- |
| 納品音源 | `audio/score-v01/hai-no-machi-loop-v01.wav` |
| 形式・実尺 | WAV、PCM 24 bit、48 kHz、ステレオ、23.414625秒、1チャンネルあたり1,123,902サンプル。推定82 BPMの8小節 |
| 容量・SHA-256 | 6,743,480 bytes、`3ab4afb5bd291341ab42d6d7afc6aa67e9d10fa62003f83f0f0a8538659c96b8` |
| 生成 | Lyria 3.5に曲調のテキストを1回送信し、178.314667秒の48 kHz・16 bitステレオWAVを取得。所要約32秒。公表価格は1曲0.08米ドル、実請求は未確認 |
| 原音 | `audio/score-v01/_generation/lyria-original.wav`、34,244,124 bytes、`7d93a578adb5d947eee9ec08d06a1a7945641cd4a348ac6f978f28dc275fedec` |
| 切り出し | 原音のサンプル1,541,713〜2,665,615（末端は含まない）、32.119021〜55.533646秒。末尾0.200秒に曲頭の直前0.200秒をクロスフェードし、8小節の長さを維持した |
| 音量調整 | 原音の切り出し範囲にあった4,193個のフルスケールサンプルを近傍波形から補間。24 Hzをカットオフとするハイパスと、105 Hz以下を緩やかに抑える低域調整を適用。出力は −24.0 LUFS、−6.21 dBTP |

生成の出典は [Lyria 3.5の生成仕様](https://ai.google.dev/gemini-api/docs/music-generation) と [公式料金](https://ai.google.dev/gemini-api/docs/pricing#lyria-3-5)。

### 生成時の指示

```text
Compose a seamless, instrumental film underscore for a slow-burn urban suspense drama. The mood is cold, restrained and watchful, with a faint trace of grief and resolve. Use a low bowed cello drone with soft bass harmonics, a quiet muted heartbeat-like bass pulse, and a distant, sparse three-note felt-piano figure. Keep the bass audible without excessive sub-bass. Around 80 BPM, steady 4/4, D minor with a persistent D pedal and restrained suspended harmony. Repeat the same eight-bar phrase at least three times, with very small changes in texture but the same meter, harmony and downbeat. Let the steady texture start from the first bar and stay quiet and even under footsteps and spoken dialogue. Leave ample space in the voice range. Use subtle short room ambience and a soft, shadowed stereo image. Maintain the repeating unresolved harmony right through the end, with no fade-out, cadence, count-in, long intro or dramatic change. No vocals, humming, spoken words, sound effects, lead synth, strong drums, trailer impacts, jumpscares or heroic climax. The sound should feel like quiet tension under a scene, with the same atmosphere from beginning to end.
```

## 検査と再出力

- WAV全編と3周連結版をデコードし、3周分のPCMが1周を繰り返した結果と一致することを確認。23.414625秒と46.829250秒の両境界で、隣接サンプル差は −60.35 dBFS（周辺50 msずつの差分の約54パーセンタイル）、境界前後100 msのレベル差は0.39 dB。推定小節周期との差は最大1.83 ms。−55 dBFS以下が60 ms続く無音区間と、出力のフルスケールサンプルはともに0件。
- ローカルの音声区間検出では発話区間0件。人の試聴、動画への配置後の効果音・ニュース音声とのバランス、BGMの採用は確認待ち。
- 同じ環境で再出力し、納品WAVとSHA-256が一致した。Windows、Python 3.12.2、NumPy 1.26.4、SciPy 1.13.0、FFmpeg 8.1.2を使用。
- `audio/score-v01/_generation/` に `request.json`、`receipt.json`、`render.json`、`qc.json`、`qc-three-loops.wav` と再出力スクリプトを保存。原音とスクリプトがある環境で `python -B <メディアルート>/audio/score-v01/_generation/render_loop.py <未作成の出力WAV>` を実行すると、同じ原音から切り出せる。
