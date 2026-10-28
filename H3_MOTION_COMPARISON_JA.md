# MiniMax H3 APIとローカル生成の動作比較

更新日：2026-10-29。これは比較実験の実行機能であり、APIとローカルの品質差を測定済みという資料ではない。

`tools/h3_compare.py` は既存の `tools/h3_api.py` とStudioのComfyUIアダプターを使う。APIへの新規送信は1コマンド1件。共通の英語プロンプトを両方へ渡し、要求尺5秒・9:16で試す。人物シリーズの制作ではなく、犬・球と積木・玩具車を使う動作検証である。

## 試験セット

`benchmarks/h3-motion-v1.json` に次の3ケースがある。各ケースに共通プロンプトと具体的な確認項目を保存した。

| ID | 主な確認対象 | カメラ |
| --- | --- | --- |
| `fetch` | 犬の走行・方向転換・接地、形の保持 | 固定 |
| `collision` | 球と3個の積木の接触、落下と個数の保持 | 固定 |
| `tracking` | 車輪、曲線走行、背景の視差 | 追従 |

最初は1ケースの1試行を確認する。同じプロンプトを何度か試す場合は `init --trials 3` 等で独立試行を用意する。APIのseedは既存クライアントで公開していないため固定しない。ローカルseedは基準値＋試行番号−1。異なる試行のseedが偶然APIと一致するとは扱わない。

## このPCでの準備と実行

PowerShellでリポジトリ直下から実行する。Python標準ライブラリと、PATH上のFFmpeg／FFprobeを使用する。

```powershell
python tools/h3_compare.py doctor
```

2026-10-29の実確認では、必要な4モデルの存在とbytes、FFmpeg／FFprobe、ローカルの固定ワークフロー・runtime・ツールの識別解決を確認した。doctorはモデル全体のhash検査やAPI認証検証を行わない。APIキーは未設定、8188番ポートのComfyUIは未起動だった。実際のGPU生成直前には既存アダプターがモデルhashと稼働プロセスを検査する。

`.env.example` を参考に、ローカルの `.env` に `MINIMAX_API_KEY` を設定する。キーをチャット・Git・コマンド引数へ貼らない。既存の値がある場合は `.env` を上書きしない。ローカル生成用には別ターミナルで起動する。

```powershell
.\run-local.ps1 -Profile official_q4 -NoBrowser
```

比較の初期化はネットワーク通信・生成を行わない。以下の `v02` は今回作成済みなので、そのまま `run` から使える。新たに初期化する際は別の保存先を指定する。

```powershell
python tools/h3_compare.py init outputs/benchmarks/h3-motion-20261029-v02
python tools/h3_compare.py run outputs/benchmarks/h3-motion-20261029-v02 --case fetch --provider api --confirm-billable
python tools/h3_compare.py run outputs/benchmarks/h3-motion-20261029-v02 --case fetch --provider local
python tools/h3_compare.py compare outputs/benchmarks/h3-motion-20261029-v02 --case fetch
python tools/h3_compare.py status outputs/benchmarks/h3-motion-20261029-v02
```

`run` の既定待機上限は1800秒。`--wait-timeout 3600` 等で変更できる。外側の端末実行がタイムアウトしただけなら、プロセスが残っていないか先に確認する。並行実行を防ぐ `.comparison.lock` はプロセスが通常終了すると消える。強制終了で残った場合は、対象プロセスが終わったことを確認してからそのファイルだけを削除する。

APIキーが設定されれば上記 `run --provider api` で課金を伴う1件を送信する。コストを見積もる場合は初期化時に、確認した出力1秒当たりの単価を `--api-price-per-second 0.1 --currency USD` のように指定する。**0.1はコマンド例であり現在の公式価格ではない。** 見積りはケース数×試行数×5秒×入力単価。割引・税・再試行等は含めない。実請求額は取得しておらず `actual_api_cost: null`、ローカル電気代も未測定のまま保存する。

## 再開と二重発注の防止

- APIはPOSTより前に `submission_unknown` を保存する。task ID受領後は保存済みIDを照会する。同じ `run` を再実行しても新規POSTしない。完了済みの場合は原本のbytes・SHA-256を確認して再利用する。
- POSTの応答を受け取れなかった場合は、自動再送しない。プロバイダー側で依頼の内容とtask IDを照合できたときに限り、`attach-task` を使う。既存taskの状態取得に成功しても同一プロンプトであることまではAPIから検証できないので、手動照合の責任範囲を残す。
- APIの失敗・取消は同じ試行内で再発注しない。別の比較ディレクトリを初期化して新しい試行にする。
- ローカルは既存アダプターの送信マーカーからIDを復元する。入力・モデル・runtime・FFprobeが変わった場合、別比較として初期化する。ローカルの時間切れは既存アダプターが取消を試みるため、再開しても失敗状態が残ることがある。マーカーを削除しての自動再発注はしない。

```powershell
python tools/h3_compare.py attach-task outputs/benchmarks/h3-motion-20261029-v02 --case fetch --task-id TASK_ID_FROM_PROVIDER
python tools/h3_compare.py run outputs/benchmarks/h3-motion-20261029-v02 --case fetch --provider api
```

## 比較と評価

`compare` は原本のhashを確認し、`review/fetch-01/index.html`、`report.json`、入力hashに対応する `side-by-side-*.mp4` を出力する。比較MP4は左API・右LOCAL、各480×864、24fps、先頭5秒、音声なし。縦横比を維持して余白を付ける。原本動画を別々に再生でき、音声は原本で確認できる。比較MP4を生成後に全デコードして確認する。

| 項目 | API条件 | ローカル条件 |
| --- | --- | --- |
| モデル | MiniMax-H3、サービス側の内部版は未取得 | INT8 convrot、Q4_K_Mテキストエンコーダー |
| サイズ | 768Pが既定、実寸は出力をFFprobeで測定 | 480×864 |
| サンプリング | 内部条件未取得 | simple／20ステップ、res_multistep |
| 尺 | 5秒要求 | 124フレーム／24fps、約5.167秒 |
| 乱数 | 指定なし | seed記録あり |

これは現在の手元の構成とAPIの実用比較で、解像度・量子化など1要因だけを分離した実験ではない。共通表示サイズの動画と原本の両方を見る。単一出力を一般的な品質優位の証拠にしない。必要なら複数試行、観察者や順序を変えた確認へ進む。

動きの補助計測は6fps・64×64グレースケールの隣接フレーム平均絶対差と、差が0.002未満の割合。カメラ移動、ちらつき、圧縮ノイズでも値が変わるので画質点・優劣には変換しない。完全に静止した映像でも精細さが良い可能性があり、大きく変化しても形が崩れている可能性がある。

人またはAI補助の評価を記録する際は `--reviewer` に実際の評価者・手法を明記する。観察した秒数と現象を `--note` へ書く。1＝達成しない／目立つ破綻、3＝部分的な達成／破綻あり、5＝達成／気になる破綻を観察しない、2・4はその間。未評価は省略してnullとする。

```powershell
python tools/h3_compare.py score outputs/benchmarks/h3-motion-20261029-v02 --case fetch --provider api --reviewer human:USER --action 4 --identity 3 --temporal 3 --note "00:02の方向転換で後ろ足が一瞬変形。音声は未評価。"
python tools/h3_compare.py compare outputs/benchmarks/h3-motion-20261029-v02 --case fetch
```

評価軸は `action`（動作達成）、`identity`（形と数の維持）、`temporal`（時間的一貫性）、`detail`（細部）、`audio`（同期と自然さ）。評価は追記で、両原本のhashに結び付く。`score` 後に `compare` を再実行するとページも更新される。自動合算や勝者の自動決定は行わない。人の最終確認、ユーザー採用、公開状態は別で、初期値を未確認から自動昇格させない。

## 保存と検証範囲

`outputs/benchmarks/<比較ID>/` に凍結したsuite、実行台帳、raw MP4、比較派生、評価を置く。suite変更を検出した場合は実行を拒否する。APIレスポンス全文や期限付きの動画URLは台帳へ保存しない。ローカルはモデル・runtime・ワークフローhashを含む既存Studio manifestへ参照を残す。原本と比較MP4はGitHubへ追加しない。

今回の検証は入力固定・料金見積り・二重POST防止・API既存taskの再開・ローカル送信マーカー復元・hash照合・実メディアの比較変換／デコード／補助計測・評価保存。APIの実認証・生成・請求と、実生成映像の品質比較、人の最終試聴は未実施。

公式API形式の確認元： [MiniMax公式リポジトリの直接生成例](https://github.com/MiniMax-AI/MiniMax-H3/blob/main/scripts/readme/full-2k-t2va-reference-768p-result-by-directly-calling-open-platform-api.sh)（2026-10-29確認）。`POST /v2/video_generation`、`GET /v2/query/video_generation/{task_id}` と既存クライアントの形式を照合した。プラットフォームのAPI仕様ページは今回のブラウザー取得では到達できなかった。現在価格・全境界値を新たに検証済みとはしない。

これは内部の技術比較実装であり、公開解説動画・記事の制作開始や公開を意味しない。実測後に紹介企画にする場合は通常の調査・実画面・記事素材・Driveレビューの工程を適用する。
