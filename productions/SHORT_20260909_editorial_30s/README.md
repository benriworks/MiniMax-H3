# Claude Desktop・編集スタイルの30秒版

6秒の無音試写を、30秒・3章・6発話の確認作品へ適用する。前作の21秒版と6秒版は上書きしない。サブエージェント・新規画像生成・追加画面収録・外部チャット・有料API・BGMは使わない。

| 時間 | 画 | 伝えること |
|---|---|---|
| 0〜10秒 | 暖色テーマ＋既存イラスト。目的・日付・文字数・依頼文を順次表示 | 条件を添えて3案頼む |
| 10〜20秒 | 白テーマ＋既存Claude Desktop実画面の15〜25秒、等速・全体表示 | 候補から表現を選び、自分の言葉にする |
| 20〜30秒 | 墨色テーマ＋橙色の確認図解。日付→文字数→確認フロー | 下書きはAI、判断は人 |

`story.json`が台本・6発話の開始時刻・見出し・投稿テキストの正本。短い字幕を読み終える時間と章末の間を取り、無理な早口・音声の引き伸ばし・重複発話を避ける。Microsoft Sayaka／rate 0を継続し、新台本をローカルで合成する。音声ノイズへの対策変更は行わない。

## 再現

```powershell
python -m unittest discover -s productions/SHORT_20260909_editorial_30s -p test_story.py -v
node productions/SHORT_20260909_editorial_30s/render.mjs
# 上の最終出力が示した実在のrender.jsonを渡す
python productions/SHORT_20260909_editorial_30s/finish.py <render.jsonのパス>
```

`render.mjs`は10秒の編集素材2本を作り、実画面と共通`TimelineComposition`／`claude_editorial_v1`で720frameを描画する。PNG frame／BT.709／24fps／1080×1920。画像・フォント・実収録は既知hashを照合し、依存ソースを描画前後で照合する。

`finish.py`はStudio既存の`generate_local_narration`と`assemble_local_video`を呼ぶ。6字幕は各発話の実WAV frameからタイミングを得る。各発話が次の発話・次の章・29秒を越えたら停止し、速度変更や切断で隠さない。字幕あり／なしMP4、SRT、WAV、timings、各manifest、投稿テキスト、検証JSON、確認用ZIPを保存する。ZIPは全entryのhashとCRCを読み戻す。

## 通常Studioとの境界

今回は**案件用制作スクリプト**であり、共通描画・音声・assembly workerを利用するが、Studio DBに保存されたrecipe／Run／Jobは作らない。`outputs/studio/runs/run_*`はworkerが使用するファイル作業IDであり、DB登録済みRunではない。簡単作成は現在1章1発話なので、3章6発話の独立スケジュールを画面で編集・一括実行できる状態と混同しない。

独立検証は両MP4の30.000秒・720frame・映像音声形式・全decode・6発話の時間枠・ZIP内容を検査する。通常DB系の技術QC Jobや公開受入を実施したとは記録しない。作品品質、とくに従来から保留している音声品質は人の確認を要する。実画面は通常チャットで、Claude Codeや思考中の実演ではない。

## 完成・確認記録

- [30秒・音声字幕入りMP4](../../outputs/studio/runs/run_f892743dcc2f2eec8dcd10dc4093cb89/assembly/F211950F877FCEFBD397BAB0B2E4B1ED0ED64510F224087CCD7C963D0AB38C60/master-captioned.mp4)
- [字幕なしMP4（見出し・図解は残る）](../../outputs/studio/runs/run_f892743dcc2f2eec8dcd10dc4093cb89/assembly/F211950F877FCEFBD397BAB0B2E4B1ED0ED64510F224087CCD7C963D0AB38C60/master-clean.mp4)
- [投稿用テキスト](../../outputs/studio/verification/editorial-30s-20260909/20260908T192256537Z/publication.txt)
- [確認用ZIP](../../outputs/studio/verification/editorial-30s-20260909/20260908T192256537Z/editorial-30s-review-package.zip)
- [検証JSON](../../outputs/studio/verification/editorial-30s-20260909/20260908T192256537Z/verification.json)

両MP4は30.000秒、720frame、1080×1920、24fps、H.264、AAC 48kHz stereoで全decode成功。字幕入りSHA-256は`65C928FE47EAC8C597C379C3F9D40595F85D84A8637A0C941C2548CF2180F022`、ZIPは`9C2EE217BC18A1E5A186B71BE36E2E6A0478EF3218F717B98F1A4A04074CB085`。ZIPは10項目を読み戻し、全entryのhashとCRCを照合した。

実発話の区間は0.500〜3.864、4.700〜8.773、10.500〜14.223、14.700〜18.383、20.500〜24.343、24.700〜28.548秒。字幕はこれと同じ実WAV境界。6・16・26秒の完成フレームを目視し、見出し・素材・非公式表記・字幕の非重複を確認。字幕は指定安全領域に収まる。最終音声のsample peakは-3.3dBFS、平均-24.1dBFS（FFmpeg volumedetect）。これはノイズの解消や聴感上の公開品質の確認ではない。

専用テスト6件、関連テーマ／音声／cache chainテスト30件が成功。アーキテクチャ本文・Mermaid図を更新。Git commit／merge／pushは行っていない。

初回は共通compositionの素材名制約`clip-NN.mp4`に適合せず停止した。共通validationは緩めず、ドライバーのステージ名を修正。完成済みの前後素材のみを固定hashで再利用し、`20260908T192256537Z`で全体を描画した。初回素材は`20260908T191950790Z`に保持する。上記の通常再現コマンドは修正済みで、素材から新規描画する。`--reuse-verified-panels`はこの記録の固定2素材専用の復旧オプション。
