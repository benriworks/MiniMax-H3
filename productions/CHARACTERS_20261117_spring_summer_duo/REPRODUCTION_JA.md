# 再現手順｜春服と夏服

基点は `a3aedec903d763a3cd0b69b911601a0beee94c61`。コードのフォルダーと素材の `outputs/characters/CHARACTERS_20261117_spring_summer_duo/v01/` を照合する。FFmpeg、ffprobe、Python 3.12、Pillow、Studio同梱のNoto Sans JPを使用。

1. Fable 5.2の `female-understanding.mp4` と `male-happy.mp4` から1.2秒直後のフレームを抽出する。実制作では冬服の `references/female-understanding-1.2.png` と `references/male-happy-1.2.png` を再利用。元の2枚と生成した4枚の寸法・ハッシュを確認する。 [基準画のプロンプト](IMAGE_PROMPTS.md)
2. 版付きの `keyframes` に4画像を置く。定義は [motion-spec.json](motion-spec.json)。新規生成を行う場合のみ、既存の `productions/content-projects/CONTENT_20261108_short_drama/generate_h3_shot.py` に、保存予定のジョブフォルダー・対象のプロンプト・同じPNGの開始画と終了画・5秒を渡す。受理済みのタスクを回収する場合は、同じジョブフォルダーで再開し、送信時のフォルダーやIDを照合する。
3. `python -X utf8 productions/CHARACTERS_20261117_spring_summer_duo/assemble_seasons.py inspect outputs/characters/CHARACTERS_20261117_spring_summer_duo/v01` で正式な素材の全編デコードと標本を確認する。手や衣装、表情、机と画角の変化は `qc/spring` と `qc/summer` で確認。 `motion-review.json` に実際の動作と候補区間を記録する。
4. `python -X utf8 productions/CHARACTERS_20261117_spring_summer_duo/assemble_seasons.py package outputs/characters/CHARACTERS_20261117_spring_summer_duo/v01` で、元音声を外した編集用MP4、確認用プレビュー、PNG、台帳をZIPにする。旧版が存在する場合は保管し、書き出しの版と出力先を分ける。映像とZIPの実ファイルを検査してから限定共有に保存する。

完成素材がある場合は保存済みテイクから再パッケージできる。ImageGenやMiniMaxの出力を再生成した際のバイト一致は未検証。
