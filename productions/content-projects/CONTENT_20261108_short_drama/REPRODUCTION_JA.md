# ショートドラマ v03 の再編集手順

対象は「日曜、海に行かない？」のレビューv03。原本を使う再編集はAPI送信を必要としない。新しいワークツリーでは、主cloneのignored素材の存在とハッシュを照合する。

| 入力 | 主clone内の位置 |
| --- | --- |
| 承認基準画 | `outputs/content-projects/CONTENT_20261108_short_drama/characters/v02/maho-reference-v02.png` |
| 4本のH3原本・受付台帳 | 同案件 `shots/v01/<カットID>/source.mp4` と `generation.json` |
| 着信・写真裏と人物の基準画 | 同案件 `plates/v01/*.png` |
| 写真の既存試験素材 | `outputs/benchmarks/h3-api-cost-latency-20261108/v01/pilot-5s-vertical.mp4` |
| 台詞原本v03 | 同案件 `audio/v03/tts/d01-maho/voice.wav`、`audio/v03/tts/d02-father/voice.wav` |
| 確認用の書き出しと台帳 | 同案件 `review/v03/`、`qc/v03/` |

環境はWindows、Python 3.12、FFmpeg／ffprobe 8.1.2、Pillow 12.3.0、NumPy 1.26.4、リポジトリのBudouX文節組版、WindowsのYu Gothic Bold。開いたリポジトリルートで、主cloneを環境に合わせて指定する。

```powershell
$primaryClone = 'C:\Users\mono_\MiniMaxH3'
$dramaMedia = Join-Path $primaryClone 'outputs\content-projects\CONTENT_20261108_short_drama'
$pilotMedia = Join-Path $primaryClone 'outputs\benchmarks\h3-api-cost-latency-20261108\v01\pilot-5s-vertical.mp4'
python -B productions/content-projects/CONTENT_20261108_short_drama/render_short_drama.py $dramaMedia $pilotMedia --version v03-reproduction --voice-version v03 --master-gain-db 3.8
```

1. 画像・映像から7カットを作り、各範囲と元ファイルのSHA-256を記録する。表示字幕の文節と幅を検査し、台詞に合わせて二箇所へ合成する。
2. 雨・効果音、ピアノ、台詞を別のWAVに出す。台詞の先頭と末尾の無音を整え、父の声に電話の帯域を適用する。BGMは共通プロファイルで会話全体を減音する。
3. 映像とAACを結合し、1080×1920、24 fps、720フレーム、30.000秒、全decodeを確認してから版を確定する。実フレーム、発話と字幕の内容、AACの音量を [v03の検証要約](verification-v03.json) と照合する。素材が異なる環境の再現結果は別記録にする。

このWindows環境では、上の手順で別版へ書き出し、レビューv03とSHA-256の一致を確認した。再編集にAPI送信は発生していない。

## 新規生成を行うときの境界

`generate_h3_shot.py` の初回送信にはカット別プロンプト、基準画、秒数、課金実行の指定が必要。送信前の記録と受付IDを保存する。同じカットの再開は受付IDから照会する。受付結果が不明な送信は、重複課金を避けるためタスクを確認してから扱う。使用量から算出した料金と、利用明細の差引額は別に記録する。

Gemini 3.8 Flash TTSはこの制作でWAVを返した。旧PCMアダプターで弾かれた最初の声は、保存済みの生応答からWAVを検査して回収した。新しい音声生成は送信済みの応答を先に確認する。v03の原本を使う再編集は、この音声APIを呼ばない。
