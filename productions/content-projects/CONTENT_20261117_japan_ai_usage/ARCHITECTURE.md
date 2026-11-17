# 日本のClaude利用｜制作アーキテクチャ

`story-v01.json` が表示文、話者、画面と目標尺を保持する。出典・数字・原本の切り出しは `sources.json`、読み指定は `narrate.py`、フルで扱う架空の会議入力と実応答は個別のテキスト。ショートv02では [差し替え台本](story-short-v02.json) から後半2場面の表示・読みと画面を置き換える。

- `prepare.py` が固定版の公開CSVのSHA-256と順位・数値を検査し、公開画面をトリミングしてブログ用のWebPを作る。人物クリップの元ハッシュを検証し、12 fpsの作業フレームに展開する。
- `narrate.py` は共通Gemini経路で先頭1台詞の検証後に続ける。検証済みのナレーションを選択記録へ登録する。ローカルSAPIには別の出力世代がある。
- `short_proposal_voice.py` はv01とv02の台詞を照合し、同じ話者・本文・読みのWAVを検証してコピーする。変更台詞は既存のGemini経路で生成し、ショートv02の選択記録を保存する。
- `proposal-demo-v02/run.py` は独立した作業フォルダーで、Claude Codeへ架空の提案書テンプレート・商談メモ・提案条件を渡す。ツール実行と保存された初稿を検査する。掲載する画面は台本と `graphics.py` で要約し、レンダリングは保存済み素材だけで実行できる。
- `render.py` と `graphics.py` が動画ごとの表示・字幕時刻を組み立て、`mix_audio.py` が既定のBGM処理と最終音量を調整する。PillowとFFmpegで静止画・既存人物・音声を組み合わせ、MP4とSRT、技術検査を版付きで保存する。
- ショートv03はショートv02の台本と音声選択記録を読み、`Editor` の `show_role_labels` を無効にして、2人の下の役割名を描画せずに出力する。
- `record_workspace.py` はStudioの共通CLIへ企画・調査・素材・記事を登録する。`package_article.py` はStudioの画像出力からMDXとHTMLのレイアウト確認用ZIPを作る。
- Gitの対象は台本・出典・編集コード・検証要約。素材・映像・音声・全応答レシートは `outputs/content-projects` の案件フォルダーで管理する。

[アーキテクチャ図](ARCHITECTURE_DIAGRAM.md) · [再現手順](REPRODUCTION_JA.md)
