# 編集スタイルの実素材レビュー

新しい`claude_editorial_v1`の共通compositionを、前回の独自イラスト・Claude Desktop実画面・確認図解で描画する。各2秒・計6秒の無音デザイン確認用であり、新しいナレーション入り作品や通常Studio Runではない。

```powershell
node productions/SHORT_20260908_editorial_review/preview.mjs
```

既存source／フォントhashを照合し、現行renderer・依存ソースのhashを描画前後で比較。PNG frame／BT.709でMP4を出力し、144frame・6秒・無音と全decodeを検証する。ファイルは独立した日時付き`outputs/studio/verification/editorial-20260908/`へ保存し、前作を上書きしない。

実装テスト: フロント227件、関連Python42件、mock UI3件、build成功。390pxの構成チェックは縦並びで横にはみ出さない。音声変更・新規画像生成・追加収録・外部送信なし。公開品質の受入は未実施。

## 確認済み成果物

- [6秒・無音の新テーマ確認動画](../../outputs/studio/verification/editorial-20260908/20260908T131233712Z/editorial-design-preview-6s.mp4)
- 1080×1920／24fps／144frame／6.000秒、H.264、音声streamなし、全decode成功。951,066 bytes、SHA-256 `6424BA031A11C72FC6AC21B163BC073C597B5FF78374C3DD6888C0CB2A791C94`。
- [入力・現行ソース・出力の検証JSON](../../outputs/studio/verification/editorial-20260908/20260908T131233712Z/verification.json)
- 0／72／120frameの目視で暖色→白→墨色、章番号、見出し・素材枠・非公式表示の分離を確認。字幕と音声を含む通常Runの新規E2Eではない。前作の21秒動画を上書きしていない。
- Studioのmock UI証拠: `studio/output/playwright/screen-structure-review-desktop.png` と `screen-structure-review-390.png`。実素材の映像品質検査とは別の、実React／合成動画／API遮断によるUI試験。
- アーキテクチャ本文・Mermaid図は更新済み。サブエージェント、Git commit／merge／pushは使用していない。
