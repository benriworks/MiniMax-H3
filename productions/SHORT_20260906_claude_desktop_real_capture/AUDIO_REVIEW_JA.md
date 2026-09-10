# 冒頭の構図修正とSayakaの試作用音声比較

日付: 2026-09-06。利用者の実聴ではv3に発話中の「プププ」というノイズがあり、作品品質は不合格。最新のD調整版も「声のこもりはないがクリーンとは言えない」との評価。ここではその評価を技術QCで上書きしない。**冒頭構図は利用者了承。音声のクリーンさは未達**である。

## スペクトルの実測（D試聴後の追補）

`spectrum_review.py`で原本WAV・同音量A／D・診断manifestのhashを照合し、同じ尺度のスペクトログラム、発話別Welch PSD、帯域電力、RMS包絡の周期スペクトルを出力した。新規合成・フィルター・課金APIは0。原本の前後hash一致を確認した。

- 最終診断フォルダー: `outputs/studio/verification/claude-desktop-real-20260906/spectrum-review/20260906T041309627865Z/`
- `spectrum-overview.png`: 冒頭同一発話のA／Dを共通色尺度−110〜−25dBFS/Hzで比較し、3発話の平均PSDを併記。
- `lowband-and-modulation.png`: 発話別20〜500Hzと、冒頭発話の音量変動周期。声の高さと音節の周期を区別する。
- `report.json`／`mean-spectrum.csv`: 入出力hash、解析条件、帯域・突出量、元のAAC比較値、生の平均PSD。図の目盛／非重複も目視確認済み。

各発話を連結せず個別にHann Welch（8192点）で計算し、発話区間長で電力平均した。原音の周波数分解能は2.692Hz、A／D比較は5.859Hz。区間間の挿入無音は除外した。

| 観測 | 実測 | 判断できる範囲 |
| --- | --- | --- |
| 20〜150Hzの原音エネルギー | 約0.063%（20〜11025Hz内） | 低域カットが主成分へ与える変化は小さい。ただし小エネルギーでも耳障りになり得るため、聴感上の重要度とは同義でない |
| 150〜4000Hzの原音エネルギー | 約99.77% | 主な声の帯域。A／D差は150〜1000Hzで−0.068dB、1000〜4000Hzで＋0.063dBと小さい |
| 50Hz／60Hzの近傍突出量 | 3発話で−1.92〜＋2.03dB | この測定では強い固定ハムの証拠は見つからない。ノイズ全般の不在証明ではない |
| 文中の静かな20ms窓（−55dBFS未満） | 208窓、うち141窓は完全な0 | 残りは声の立上り／減衰も含む。SAPIの設計上の無音を環境録音のノイズ床やclean referenceにしない |
| 音量変動のピーク | 約1.02／4.32／6.10Hzなど | 自然な音節周期も含むため「プププ」の原因と断定しない |

原音とAACのほぼ一致という既存計測と合わせると、AAC工程だけが主因という証拠は弱い。一方、スペクトルの山は声の基音・倍音と重なっており、特定の山をnotchで削れば直るという根拠も得られていない。発話中の合成音声の質感が関係する可能性はあるが、今回の解析だけでは原因を確定しない。Dを標準preset／作品品質の合格へ昇格させない。

診断関数5テストを追加し、案件の18テストを実行して成功（既存13＋今回5）。挿入gapの除外、個別PSDのduration weighting、既知正弦波の電力、入力区間拒否、固定線突出量、デジタルzeroの区別を検証した。下記の77件は前段の実行記録であり、今回の全製品再実行を意味しない。

```powershell
.venv/Scripts/python.exe -B productions/SHORT_20260906_claude_desktop_real_capture/spectrum_review.py
```

## 映像 v4

冒頭の`focus_region`を削除し、メニュー、会話、入力欄、Claudeの注意書きを含む元ウィンドウ全体を表示した。2秒位置の完成フレームを目視し、文字だけの切出しになっていないことと字幕・見出しの非重複を確認した。素材は同じ30秒の録画で、新規収録・Claudeへの送信なし。場面2／3の拡大と21秒の尺は保持した。元のアプリ表示自体は大きい倍率で収録されているため、送信過程や回答3案すべてを同時に見せる再撮影とは異なる。

- recipe revision: `4`、Run: `run_d9058b3baf6f4b12991ab1e1cd32c5a9`
- top Job: `job_7548a9c71a9f400a9e36b3daa53f2644`
- Delivery Job: `job_6972a71289014df88f45f262d9c02064`
- 標準字幕ありMP4: `outputs/studio/runs/run_d9058b3baf6f4b12991ab1e1cd32c5a9/assembly/42D62A4D27AB308F4A7081C6E66C3D4FFF75C6808B151A96DEAABB79733A0FF4/master-captioned.mp4`
- MP4 SHA-256: `8D7CCE113F4DB1830B5C8D5CE80CC8A2ADC332EE2120B7E2BEAF6994C8A3ABB5`
- 21秒、1080×1920、24fps、504frames。技術QC pass、独立全音映像decode成功。13項目の納品ZIPと12payloadのhash一致も確認した。
- 封印済み入力・結果・投稿情報: `outputs/studio/verification/claude-desktop-real-20260906/renders/29F7B09A4D60A0DE6746C95684C0C6DE5D6BD4787F2288B680B36BB361C5D119/`

v4は再利用を意図したが、実際の音声Jobは`cache_hit: false`だった。v3の再利用元を辿らず、v3自身のRunを物理所有先と誤認したためである。v4のWAV・SRT・timingsの実hashはv2／v3と一致したが、新しい4つのartifact IDが作られている。「v4で再合成なし」とは記録しない。後述の比較はv3の参照元WAVを固定する。

この連鎖cacheの不具合はlocal SAPIの参照解決だけを修正した。隔離回帰は修正前3runでworker2回、修正後1回・同一4artifactへ変化。各linkのidentity／artifact署名、最終所有root、symlink成分、物理hashを確認し、循環・欠落・改ざんは拒否する。専用9テスト成功。外部TTSや実DBの履歴は変更していない。

## ノイズの切り分け

`audio_diagnostics.py`がv3の封印済みresultと読み取り専用DBから原音の所有Run／artifactを解決し、hashを照合する。旧MP4から抽出したAAC音声と元WAVを48kHz monoへ揃え、全体の遅延とgainを最小二乗で整列して比較した。

| 計測 | 結果 | 解釈の範囲 |
| --- | --- | --- |
| raw対AACの遅延 | 0ms | 今回の全体整列値 |
| raw対AACのgain差 | −0.006dB | 大きな音量差はない |
| 相関 | 0.999988 | 波形はほぼ一致、聴感スコアではない |
| 発話中の残差SNR | 46.34dB | AACで大きな新ノイズが加わった証拠は弱い |
| 原音／AACのfull-scale clip | いずれも0 | 単純な飽和は検出されない |
| 短いdropout／大きな単発不連続 | 検出条件下で0 | 全種類のクリック・異音を否定しない |

原音は22,050Hz mono PCM16。従来の`narration_only_v1`は無音補完とAAC化であり、Sayaka版にdenoiseやダイナミックレンジ圧縮を入れていたわけではない。声の周期・音節の周期とノイズは区別できないため、スペクトルの山を単に削るnotchや強いgateは使わない。

同じSayaka・同じ冒頭1文を明示24kHz／48kHzで各1回だけ合成した。両者はほぼ同じ波形だが、既定22,050Hzとの差には時間グリッド差もあり、サンプルレート変更による改善は未確認。`SupportedAudioFormats`は空でnative rateは特定していない。製品の既定形式は変更しない。

別途、既存WinRTの音声一覧も確認したが、この端末ではSayakaがなく、同じ声で比較する実合成は0回。別音声へのfallback、音声インストール、レジストリ変更、有料API利用は行っていない。

## 比較用の調整

原音・旧動画は上書きしない。以下は**標準Studioの採用済みpresetではなく、案件専用の聴き比べ候補**。

- A: 原音をresampleし、比較用の固定gainだけ適用。
- B: 旧動画AACからの診断対照。再圧縮する比較動画には採用しない。
- C: 80Hz・2pole highpassだけの軽い候補。
- D: `highpass=f=120:p=2,treble=g=-2:f=3500:t=q:w=0.7`。低域と高域の軽い整理。特定できた周期ノイズの修復ではない。

A〜Dは21秒、48kHz mono PCM16、−20.5LUFSへ固定gainで統一。Dのtrue peakは−2.8dBFS。処理後の全体遅延を揃え、低減した高域量をノイズ除去率や品質スコアとは呼ばない。声が細くなる・こもる可能性も試聴で判断する。

### お渡しする比較ファイル

`assemble_audio_review.py`は検証済みv4の映像streamをcopyし、AとDのPCMをそれぞれ一度だけAAC 256k monoへ変換する。映像payloadの完全一致、21秒・504frames、全音映像decode、encode後も−20.5LUFS・true peak A −2.0／D −2.8dBFSを確認した。新しいStudio Jobや納品合格は作らず、標準Deliveryとは別の実験コピーとして保持する。

```text
比較用動画の保存先:
outputs/studio/verification/claude-desktop-real-20260906/audio-video-review/20260906T022109263959Z-a5923437/

A_raw_control.mp4
SHA256: 32E781F71C6103B2154019AA467986690B31E0C0BA2A6A32097EEA1E6AF7C34E

D_lowcut120_treble_hypothesis.mp4
SHA256: C2FBBA75E58F0DA77679E99260C8C4F99B0A4996BCB8689F404FB167D34FFC3B
```

同フォルダーの`manifest.json`に元動画・音声・診断report・スクリプトのhash、encode設定、出力hash・計測値を保存する。

短い比較WAVは`outputs/studio/verification/claude-desktop-real-20260906/audio-diagnostics/20260906T021544623145Z/followup-lowcut120/comparison_A_raw_D_gentle_EQ.wav`。前半0〜4.15秒がA、後半4.65〜8.8秒がD。動画プレーヤーのAAC再生を外して比較できる。ここでも完全除去・音質向上の実聴合格は付けない。

## 再現と試験

```powershell
.venv/Scripts/python.exe -B productions/SHORT_20260906_claude_desktop_real_capture/assemble_audio_review.py outputs/studio/verification/claude-desktop-real-20260906/audio-diagnostics/20260906T021544623145Z/followup-lowcut120/manifest.json --candidate D_lowcut120_treble_hypothesis
.venv/Scripts/python.exe -B -m unittest discover -s productions/SHORT_20260906_claude_desktop_real_capture/tests -p 'test_*.py'
```

案件用テスト13件成功（音声診断6、構図／台本3、比較動画入力4）。メディア実検査と純関数テストを区別する。診断の最初の結果は`audio-diagnostics/20260906T021544623145Z/manifest.json`、Dと形式の追補はその`followup-lowcut120/manifest.json`。原本と初回の測定結果を保持して追補した。

主担当の最終回帰は案件13件に加え、cache連鎖／narration25件とDetailed／Quick Create／画面解説39件、重複なし計77件成功。`git diff --check`も成功。全スイートの再実行や公開品質の合格という意味ではない。Git commit／merge／push、外部投稿は行っていない。
