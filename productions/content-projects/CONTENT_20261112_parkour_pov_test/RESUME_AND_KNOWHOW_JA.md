# 屋上パルクール 俯瞰から一人称へ

2026-11-12の単発映像テスト。動画IDは `parkour-pov`、見出し案は「【映像テスト】屋上パルクール｜俯瞰から一人称へ」。参照入口は[制作索引](../../../docs/video-production/README.md)と[制作ノウハウ総覧](../../../docs/video-production/PRODUCTION_KNOWHOW_JA.md)。

## 現在地と次の作業

レビュー版は **v01、10.000秒、縦1080×1920、24fps、240フレーム**。2案の一人称を比較し、着地後に体を丸めて肩越しに視界が傾く初稿を選んだ。前転の回転は控えめ。最終MP4の全デコード、5.000秒の視点切り替え、Driveの名前・容量・オーナーアクセスを確認した。次の作業はユーザーによる切り替えと着地の見え方のレビュー。スマホでの再生と採用は確認待ち。公開は未実施。

依頼は俯瞰5秒から一人称5秒へつなぎ、ビルの屋上間をジャンプして前転で着地すること。制作者判断で9:16、架空の人物と屋上、発話なしの環境音とした。

| 版 | 映像と確認結果 |
| --- | --- |
| v01 レビュー版 | 0.000–5.000秒は高い位置から助走と踏み切り。5.000–10.000秒は空中から着地し、肩越しに視界が傾いて水平へ戻る。フレーム119・120で白枠天窓と青緑の換気口が左右で一致。着地から約7.1秒の体の丸まり、9.5秒の視界の回復を確認した。 |
| v02 比較保管 | 俯瞰を再利用し、一人称だけ同じ基準画で再生成した。手が地面につくところは明瞭になったが、回転は弱く、立ち上がり前の動きがしゃがみ込みに見えた。v01を共有した。 |

## 保存先と再現

メディアルートは素材保存用cloneの `outputs/content-projects/CONTENT_20261112_parkour_pov_test/`。各ファイルの相対位置、生成時間、bytes、SHA-256は[検証台帳](verification-v01.json)に記載。コードと素材のルートは別で、Gitの取得後は素材保存先を確認する。

| 内容 | メディアルートからの位置 |
| --- | --- |
| 共有版と編集受領記録 | `review/v01/rooftop-parkour-pov-test-v01.mp4`、`review/v01/render.json`、`review/v01/share-receipt.json` |
| 比較版と再現版 | `review/v02/`、`review/v01-reproduction/` |
| 基準画3枚と投入用PNG | `plates/v01/originals/`、`plates/v01/inputs/` |
| H3原本と生成受領記録 | `shots/v01/01-overhead/`、`shots/v01/02-pov/`、`shots/v02/02-pov/` 内の `source.mp4` と `generation.json` |
| 切り替え・着地の検査画像 | `qc/v01/review-cut-and-landing.jpg`、`qc/v01/review-start-and-end.jpg`、カット別の連続フレーム、`qc/v02/02-pov.jpg` |
| 記事の写真候補5枚 | `blog-handoff/v01/assets/` と `asset-manifest.json`。制作記事の[草稿](ARTICLE_DRAFT_JA.md)と同じ版の実フレームを使う。 |

基準画は[作成プロンプト](prompts/keyframes.txt)の3枚。FFmpegで `scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1920,setsar=1` とし、既存入力3枚とデコード後の画素MD5が一致した。俯瞰は[FL2VA](prompts/01-overhead-fl2va.txt)、一人称は[I2VA](prompts/02-pov-i2va.txt)と[改訂I2VA](prompts/02-pov-roll-i2va.txt)。生成ヘルパーは真帆の案件 `productions/content-projects/CONTENT_20261108_short_drama/generate_h3_shot.py` の `b8383ed109a20ae6ec08272de0f00e7a9342adc9` を再利用した。5秒、768P、比率adaptiveの応答は各124フレーム、768×1344、約5.167秒だった。[MiniMax公式API](https://platform.minimax.io/docs/api-reference/video-generation-v2-create)

既存の `source.mp4` と `generation.json` があれば、新規生成なしで編集できる。リポジトリルートで `$media` に実際のメディアルートを指定し、まだ存在しない版名で実行する。Python 3.12.2とFFmpeg 8.1.2の同一環境でv01を再編集し、MP4のSHA-256一致を確認した。

```powershell
python -B productions/content-projects/CONTENT_20261112_parkour_pov_test/assemble_review.py $media --version v01-reproduction-local
```

比較版の素材で組む場合は `--pov-revision v02 --version v02-reproduction-local` を指定する。APIで元の映像を再生成する作業は別工程。設計は[本文](ARCHITECTURE.md)と[Mermaid図](ARCHITECTURE_DIAGRAM.md)。

## 生成・共有の履歴

- 2026-11-12、俯瞰と一人称の初稿を同時投入。API処理は136秒と128秒、保存までの観測時間は151.688秒と141.110秒。元の尺からカットごとの先頭と末尾を保って各120フレームへ整え、音は0.12秒重ねた。共有版の最終音量は−14.4 LUFS、真のピーク−0.9 dBTP。
- 同日、一人称で回転を強調した比較案を1回生成。API処理131秒、保存まで139.000秒。3件合計の出力課金対象は15秒で、参照画像は各件5枚以下。MiniMax H3の動画部分は15秒×0.08米ドルで **約1.20米ドル** と見積もった。口座の実引き落としは未確認。[MiniMax公式料金表](https://platform.minimax.io/docs/pricing/overview)
- 同日、v01をGoogle Driveの「動画・ブログ制作レビュー」へ保存。読戻しは12,259,656 bytes、`video/mp4`、オーナー権限。端末再生と人の最終試聴は確認待ち。記事素材5枚と草稿を準備した。
- 俯瞰と一人称の違いは、共通物の位置と進行方向を保つと読み取りやすい。カメラの回転を強く指示した試行でも結果はしゃがみに見えた。素材の確認では着地の瞬間、肩越しの動き、視界が戻った時点を順に見る。この確認を総覧へ反映した。
