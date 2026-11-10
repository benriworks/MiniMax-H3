# ショートドラマ v03〜v06 の再編集手順

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

## 回想入りv04の再編集

同じWindows環境で別版へ書き出し、レビューv04と最終MP4のSHA-256が一致した。下の再編集は生成APIを呼ばない。入力は主cloneの案件フォルダーから取得する。

| 入力 | 位置と照合方法 |
| --- | --- |
| 回想で父が差し出す基準画 | `plates/v04/00-childhood.png`。2,206,019 bytes。桟橋の試験素材を参照。 [画像プロンプト](prompts/childhood-reference-v04.txt) |
| 真帆が受け取った基準画 | `plates/v04/00-childhood-received.png`。2,215,648 bytes。直前の画を参照。 [画像プロンプト](prompts/childhood-received-v04.txt) |
| 現在に戻る三場面 | `plates/v01/01-incoming.png`、`shots/v01/02-envelope-look/source.mp4`、上記の写真の試験素材。 |
| 比較元と再利用区間 | `review/v03/nichiyou-umi-short-v03.mp4` と `render.json`。 `edit/v03/` の `mix.wav`、および `04-photo-back.mp4` から `07-listening.mp4` までの4ファイル。 |

入力と最終ファイルのhash・カット境界は [検証要約v04](verification-v04.json) で照合する。使用するPython・FFmpegは上記の環境。作成済みの版と別の名前で実行する。途中で止まった場合も、途中の出力を調べられるように別の版名で試す。

```powershell
python -B productions/content-projects/CONTENT_20261108_short_drama/revise_opening.py $dramaMedia $pilotMedia --version v04-reproduction
```

最終MP4は `review/<版>/`、カット・PCMは `edit/<版>/`。全編decode、映像の720フレーム、30.000秒、旧版の10秒以降の映像と編集元PCMを照合する。AACは新しい全編音声として符号化する。最初の二枚と波・雨の境界、桟橋の写真、電話の字幕と笑顔を、実フレームと音で確認する。記事の1080×1920画像は `blog-handoff/v04/asset-manifest.json` のフレーム番号で再抽出できる。

## キーフレーム比較版v05の再編集

主cloneの `review/v04/nichiyou-umi-short-v04.mp4` と同フォルダーの `render.json`、`edit/v04/` の冒頭5カット、`edit/v03/` の写真裏と電話の3カット、保存済みの `shots/v05/05-decision-fl2va/source.mp4` と `generation.json` を使う。素材のhashと出力条件は[検証要約v05](verification-v05.json)で確認できる。Python 3.12.2、FFmpeg 8.1.2の環境で別版のSHA-256一致を確認した。

```powershell
python -B productions/content-projects/CONTENT_20261108_short_drama/replace_decision_shot.py $dramaMedia --version v05-reproduction
```

再編集は生成済み124フレームの両端を残して120フレームに整える。v04のAACをコピーし、差し替え区間外の復号画像とAACパケットを照合する。全decodeと30秒を確認して `review/<版>/` を確定する。再現時は未使用の版名を指定する。

FL2VAの入力は `references/workflow-v01/05-decision-start.png` と `05-decision-end.png`。既存CLIでは `--image` と `--last-image` を指定でき、各画像のhashを受付記録へ保存する。試行済みの受付を照会する場合は保存先のディレクトリを指定する。 [プロンプト](prompts/05-decision-fl2va-rehearsal-v01.txt)

## 画角修正版v06の再編集

主cloneの `review/v05/` のMP4と `render.json`、`edit/v04/`・`edit/v03/`・`edit/v05/` の既存カット、`plates/v06/00-childhood-received.png` と `plates/v06/04-photo-back.png` を使う。入力2枚の出所、寸法、hashは[検証要約v06](verification-v06.json)で照合する。

```powershell
python -B productions/content-projects/CONTENT_20261108_short_drama/revise_cut_angles.py $dramaMedia --version v06-reproduction
```

未使用の版名へ出力する。39フレームと72フレームを別の基準画で組み、v05からAACをコピーする。区間外609フレームとAACのhash、720フレーム、30.000秒、全編decodeを照合する。同環境での別版は最終MP4のSHA-256が一致した。新規の動画・音声API送信を必要としない。

## 新規生成を行うときの境界

`generate_h3_shot.py` の初回送信にはカット別プロンプト、基準画、秒数、課金実行の指定が必要。送信前の記録と受付IDを保存する。同じカットの再開は受付IDから照会する。受付結果が不明な送信は、重複課金を避けるためタスクを確認してから扱う。使用量から算出した料金と、利用明細の差引額は別に記録する。

Gemini 3.8 Flash TTSはこの制作でWAVを返した。旧PCMアダプターで弾かれた最初の声は、保存済みの生応答からWAVを検査して回収した。新しい音声生成は送信済みの応答を先に確認する。v03の原本を使う再編集は、この音声APIを呼ばない。
