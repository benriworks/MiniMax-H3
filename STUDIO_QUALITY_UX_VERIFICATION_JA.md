# 品質・Studio UX整備の検証記録

検証日: 2026-09-05（JST）

基準: `main` / `4285d9023f3598c61b2f20e09c08f3f28820e880` からの未コミット変更
状態: 実API一気通貫・全体回帰試験ともに合格

## 実装と実試験で修正した問題

- 取込時のffprobe結果を永続化し、取込動画の尺・画素数・fps・素材音・codecを表示。
- 素材の使用範囲プレビュー、見出し／発話量の助言、対象寸法だけの固定鮮明化、初回台本確認。
- 普段の入口を「作る」「確認・修正」「動画・投稿用テキスト」に整理。詳細ツール12個は開閉式。
- 字幕あり／なし動画の再生・保存、タイトル／説明文／タグをUTF-8 BOMのテキストへ保存。
- 初回入力の「全角20文字」という誤った案内・検証を、実際の各行全角10相当／半角20へ一致させた。変更前は12文字の主文が取込後のrecipe検証で止まったが、変更後は入力段階で過長を判定する。
- 素材一覧のファイル名が狭い列へ入る表示を修正。previewカードは利用可能な横幅に応じて列数を変更。
- 素材metadataを内部の閉じたartifact bindingから分離し、Windows Capture／Voice Upgradeの既存照合を維持。
- Deliveryの監査snapshot取得時刻だけで入力変更と誤判定する既存不具合を修正。実質的な制作変更は引き続き検出する。
- 納品Jobの完了が共通の状態更新から先に届いた場合も、作成中表示が残らず成功・失敗を表示する。

## 実ブラウザー・実APIの一気通貫試験

Chromeの独立した検証セッションでloopback APIを操作。API応答をmockせず、音声・編集・合成・QC・Deliveryを実行した。素材はFFmpegの6秒、320×576、24fps、音声なしのテストパターン。生成AIモデルによる新規動画生成や有料APIは実行していない。

| 確認項目 | 結果 |
| --- | --- |
| 初回wizard | 名前・素材・主文から3場面の実台本を表示し、一括作成を登録 |
| 素材情報 | 320×576、6秒、24fps、音声なし、h264を表示。backend再起動後も保持 |
| 素材プレビュー | 3本ともnative videoが320×576／6秒を読み込み、自動再生なし、media errorなし |
| 使用範囲 | 5.9秒へのseekを5.167秒に戻し、停止状態を確認 |
| 鮮明化 | 対象素材で選択可。選択しても簡単画面を維持。今回の実renderでは補正なしに戻した |
| ナビ | 通常4タブ、展開時16タブ。閉じても機能や処理を削除しない |
| モバイル | 幅390pxでdocument幅390px、素材カード1列。横はみ出しなし |
| 完成MP4 | 15.000秒、1080×1920、H.264＋AAC 48kHz。clean／captioned両方を再生可能 |
| 技術検査 | 実行Runのtechnical verdictはpass |
| 手動投稿txt | ブラウザーで保存したファイルの日本語タイトル・説明・タグ・制作ID・動画hashを読み返して確認 |
| コピー失敗 | 検証セッションだけでclipboard拒否を模擬し、全文選択されたtextareaへ戻ることを確認 |
| ZIP入力比較 | 作成時一致、タイトル変更後に差分、画面再訪時に一致未確認を表示 |
| 納品ZIP | 実ブラウザーでdownload。13ファイル、PNGサムネイル3枚、publication.jsonの文言一致 |
| ZIP整合性 | manifest自身を除く12entry全てのbytes／SHA-256を独立照合して一致 |
| ブラウザー | 正常起動後のapp操作でconsole error 0。Remotion licenseの既存warning 1 |

「字幕なし」は読み上げ字幕なしで、大見出しは残る。テストパターンは機能試験用であり、公開向けの映像品質・自然な発話・リップシンクを評価した作品ではない。

## 出力と識別情報

- 制作: `production_c5b4da3304b07634fba9f5b059d3669e`
- 一括作成Job: `job_9ec4b20b66714dcf90961dee067473b0`
- Run: `run_d3df0935a3054e7fbc2348a2798dd181`
- 成功Delivery Job: `job_1e90094fcbbe4f71a43833b6aa9300a7`
- captioned master: `art_4690751e162759303729e3d42223fa20`
- ダウンロードMP4 SHA-256: `FFF055A478BE3A76F98DA9300C70398C7A92AF401E0B9D363396F98C4AC931E8`
- ダウンロードZIP SHA-256: `755AFF8D903FCB3CA5D67986CE9F3F41436D738D2D55C7D4B1B1D8FBDB01E992`

試験専用制作2件は試験後にアーカイブし、既存の制作一覧5件へ戻した。成果物は削除しておらず「アーカイブ済みを表示」から参照可能。検証用ChromeとStudioサーバーは終了した。

ローカル証跡（`outputs/`以下はGit対象外）:

- [素材preview画面](outputs/studio/verification/quality-ux-20260905/scene-preview-final.png)
- [動画・投稿情報画面](outputs/studio/verification/quality-ux-20260905/manual-delivery.png)
- [ダウンロードしたMP4](outputs/studio/verification/quality-ux-20260905/browser-artifacts/master-captioned.mp4)
- [ダウンロードしたZIP](outputs/studio/verification/quality-ux-20260905/browser-artifacts/delivery-package.zip)
- [投稿用テキスト](outputs/studio/verification/quality-ux-20260905/browser-artifacts/投稿情報-Studio検証用サンプル-2026-09-04.txt)
- [Python全体試験ログ](outputs/studio/verification/quality-ux-python-tests-20260905.log)

txtのファイル名日付と内部日時はUTCのため、JSTの検証日より1日前になっている。

## 自動試験

- `studio`: `npm.cmd test` は169件合格。
- `studio`: `npm.cmd run build` 合格。既存の大きなJavaScript bundleのwarningは残る（約943KB、gzip約264KB）。
- Python: `python -m unittest discover -s tests -p 'test*.py'` は666件実行、665件合格／1件skip（353.285秒）。

使い方と未実装の境界は [STUDIO_CONTENT_QUALITY_GUIDE_JA.md](STUDIO_CONTENT_QUALITY_GUIDE_JA.md) を参照。
