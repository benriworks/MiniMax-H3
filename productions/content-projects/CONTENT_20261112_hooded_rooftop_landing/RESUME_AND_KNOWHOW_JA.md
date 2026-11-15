# 「灰の街」制作の再開記録

2026-11-15更新。案件IDは `CONTENT_20261112_hooded_rooftop_landing`。

## 現在地

2026-11-15更新。

- 題名と設定、ニュースのアナウンサー音声、時間のテロップ（1:00「3日前」、2:00「現在」）は採用済み。
- 最新の通しは **3分版v01** `review/full-180s-v01/haino-machi-full-180s-v01.mp4`（180秒、36カット）。確認用は同じフォルダーの `preview-720p.mp4`。ユーザーの確認待ち。
- 作り方と学びは [静止画から作る短編アクションドラマのノウハウ](../../../docs/video-production/H3_ACTION_DRAMA_KNOWHOW_JA.md)。時系列の詳しいログは同じフォルダーの `RESUME_JA.md`、全カットはメディアルートの `CUTS_CATALOG_JA.md`（99本）。
- 3分版の再出力: `assemble_sequence.py --version <名前>-raw --cuts <36個のID>` → `add_news.py --start 90` → `add_screen_text.py --at 166.2 --duration 3.6 --text 第二段階へ移行せよ` → `add_titles.py --title 60.3 3日前 --title 120.3 現在`。IDの並びは `review/full-180s-v01-raw/render.json` にある。
- 最新の音楽は **通しBGM v01** `audio/score-full-v01/hai-no-machi-full-score-v01.wav`（180.000秒）。前のループの雰囲気を保ち、0:50直前と2:35直前へストリングスの山を配置した。技術検査・AI補助聴取済み。映像への本番ミックス、人の最終試聴、今回の曲の採用は未確認。配置・再現・検証の詳細は [通しBGM制作記録](SCORE_FULL_V01_JA.md)。

## 通しBGM v01（2026-11-15）

ユーザー返答は「このシナリオ向けに、ループではなく完璧なBGNを作成して下さい。さきほどのループも雰囲気は良いです。ストーリーの盛り上がるところでストリングスなどで盛り上げて下さい。」。旧ループの**雰囲気への肯定**を引き継ぎ、曲の形式を3分の場面展開に合わせる依頼として反映した。旧版は保持し、新曲の採用や映像の公開許可とは扱わない。

- Lyria 3.5でストリングスを含む180.683秒と、終幕用の58.165秒を新規生成。旧曲の生成原音も再利用し、重複しない6区間を編集。音源のループ、テンポ変更、ピッチ変更は行っていない。
- 0:50〜0:51と2:35〜2:45は音楽を抜く。ニュースの1:30〜1:45を抑え、2:45からピアノと弦の静かな余韻で閉じる。映像の0:00に合わせる単体WAV。
- 初回生成は盛り上がりがニュースに重なり、最後にも動的な弦が残ったため、原音のまま採用せず場面ごとに編集した。編集初稿の1:49付近の音色急変をAI補助確認が指摘したため、ニュースから潜入までを旧原音の連続区間へ修正した。
- 最終WAVは48 kHz / 24 bit / ステレオ、8,640,000サンプル/チャンネル、51,840,068 bytes。SHA-256は `4e4c3f6218958f1228f0898db2949cf033c053126a81efd48c3db83bb534dd8d`。−23.01 LUFS、−3.36 dBTP、LRA 14.90 LU。全デコード・所定無音・出力クリッピング0件・同環境再出力を検査。
- 制作索引・総覧・この案件記録、制作コードの独立設計本文とMermaid図を更新。共通規約は見直したが、今回の山や無音位置は案件固有のため `AGENTS.md` の変更は不要と判断した。文書・コードは専用ブランチ `codex/hai-no-machi-full-score-v01`、音源・応答・詳細検査はメディアルートへ分離する。

次の作業はユーザーの試聴と、映像へ配置する際の効果音・ニュースとの最終バランス確認。WAVの制作完了を、動画のミックス完了・新曲採用・公開完了へ広げない。

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
