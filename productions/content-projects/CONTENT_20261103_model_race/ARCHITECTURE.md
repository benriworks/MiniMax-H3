# モデル競争動画と記事の制作構成

2026-11-03。企画v01の大筋をユーザー確認済み。表現は公式用語と具体的な動作へ改訂。ショートv01／フルv02をローカルでレンダーする案件処理で、Studioの新UIや自動公開機能ではない。

## 入力と版

- `sources.json`：21出典。公式、一次報道、二次情報と原投稿の取得経緯を区別。
- `wording-v03.json`、`WORDING_REVISION_JA.md`：日本語公式の用語と助手の要約を対応付け。
- `short-dialogue-v03.json`、`full-dialogue-v04.json`：画面の表示とTTS読みを分離。フルv04はf02の読みだけを修正したもの。
- `ARTICLE_DRAFT_V03_JA.md`：媒体非依存の最新草稿。旧v02と原稿v01〜v03は履歴として保持。

## 実行と再開

`prepare.py`は実ブラウザ原本から明示座標の短い引用を切り出し、原本hashと実寸、出典を保存する。図3点は1920px。既存人物のアトラスとMiniMax動作6本は同一hashで再利用し、新しい顔や動作を生成していない。

`editorial_record.py`は実際の返答、構成採用、公式用語の調査を共通CLIへ記録する。`narrate.py`は構成採用を確認後、51台詞をGeminiで生成。female=Aoede、male=Charon、conversational_v3。完了受領を再利用し、失敗や不明な課金呼び出しを自動再送しない。`repair_voice.py`は確認されたf02の誤読だけを別フォルダーへ再生成する。APIキーはプロセスまたはユーザー環境変数から取得し、記録しない。

`produce.py`は実WAVから尺を作り、共通`editorial_captions.timed_captions`へ本案件の保護語を渡す。後方互換の既定を変えず、複合モデル名と小数点を保護する。顔と字幕の領域を分離し、PIPは発話者のみ音量連動の簡易口パク。6動作は適切な台詞で一度再生し、その後保持する。公式引用と比較では人物を退避する。

動画は24fps、ショート1080×1920、フル1920×1080。元音声は保持し、派生ミックスで台詞ごとのゲインを制限して調整。共通explanation_v1、明るいループ、発話中減音、限定したSE、2-pass loudnormを使用する。ターン別MP4とコードhashで再開を検査し、完成版の上書きを防ぐ。

## 検証、記事、共有

最終MP4は全decode、フレーム数と実尺、AACのLUFSとtrue peakを検査してから確定名へ移す。`verify_release.py`は最終MP4から全字幕ページの中央と重要場面を復号し、別に低容量の実AVプロキシを作る。長尺のselect式はFFmpegの式の深さ上限を避けるため二分木で構築する。

`review_media.py`は実音声／実動画をAI補助確認へ渡し、原稿確認とは区別する。初回フルで検出した誤読と、台詞単独の再確認、修正版を別受領で保存する。APIの品質評価を人の最終試聴としない。

`register_production.py`で人物、採用範囲、素材、主張、実尺の絵コンテ、記事の依存先をSQLiteへ保存する。共通台帳のproduction readinessは媒体品質・人の採用・公開の保証ではない。報道と未確認情報のwarningは意図的に残す。

`handoff.py`は原稿と図、短い引用、alt、出典、切り出し座標を記事一式へまとめ、ZIP内のhashを照合する。媒体のMDX組み込みと公開は実施しない。Drive送信は接続ツールで助手が行い、名前・容量・親・アクセス状態を読み戻す。動画・音声・撮影原本・API応答・受領・ZIPはignoredのoutputsへ。Gitへは軽量な文書、原稿、コード、検証要約のみ保存する。

入口は[再開履歴](RESUME_AND_KNOWHOW_JA.md)、図は[独立したMermaid](ARCHITECTURE_DIAGRAM.md)。レビュー候補、ユーザー採用、YouTube／記事の公開、mainマージは別の状態として維持する。
