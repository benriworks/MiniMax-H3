# 出典と実演記録｜2026年11月17日

数字の出典と画像の対応は [sources.json](sources.json)。ブラウザーの撮影原本・要点の切り出し座標・バイト数・ハッシュは、各版の `captures/figures/manifest.json`。原本にはログイン情報や個人データを含めていない。

| 画面・主張 | 根拠と確認範囲 |
| --- | --- |
| 国別 32 / 121、1.91x | 公式の Country usage から Japan を選択。ダッシュボードの表示に加え、公開CSVの2026-05-01〜2026-06-01未満、`country/overall/0/usage_per_capita_index` 121行から再計算。値を超える国・地域は31。 [公式画面](https://www.anthropic.com/economic-index#country-usage) |
| 4区分 | Global usage の Usage Index の凡例と地図を採録。画面表記は Leading、Upper middle、Lower middle、Emerging。日本は上から2番目の色。 [公式地図](https://www.anthropic.com/economic-index#global-usage) |
| 対象と分母、数字の比較 | 個人向けチャットとCowork。世界人口の15〜64歳の割合で調整。日本の会話比3.28％、仕事用47.0％、世界の仕事用43.36％。同じ月・粒度のみ使用。 [公式データ仕様](https://huggingface.co/datasets/Anthropic/EconomicIndex/blob/caa39af/release_2026_06_26/data_documentation.md) · [公開データ](https://huggingface.co/datasets/Anthropic/EconomicIndex/tree/caa39af/release_2026_06_26) |
| 日本企業の導入43％→54％と、基礎的活用60％ | 2026年11月12日公表。AWS委託のStrand Partners調査。後者の分母はAI導入済み企業。公表文の要点2項目を幅1800pxのビューポート原本から911px幅で抜粋。 [AWS発表](https://press.aboutamazon.com/jp/2026/11/aws-research-finds-ai-adoption-accelerating-in-japan-with-a-narrowing-gap-between-advanced-and-basic-adopters) |
| 仕事での試行の提案 | ツールと扱える情報をチームで確認する。計測項目と2週間という長さは制作側が示した試行の例。 [総務省・経済産業省ガイドライン](https://www.meti.go.jp/shingikai/mono_info_service/ai_shakai_jisso/20260331_report.html) |

## フルv02とショートv01の実演経路

1. このPCのClaude Desktopの対象ウィンドウを確認。白い画面で会話欄を読み取れなかったため、表示可否の結果を記録。
2. ローカルのClaude Code 2.1.316の接続と `claude -p` を利用し、2026年11月17日03:14 JSTに [架空の入力](demo-prompt.txt) を一度実行。ツールとセッション保存を無効化した状態で、返答のモデルは `claude-haiku-5-5`。実行レシートは出力ルートの `_private/demo-receipt.json`。
3. 期限等を元のメモと照合した [応答全文](demo-result-v01.md) を保存し、表の値を映像用に組版。人物やアプリ画面を合成したUIの提示はしていない。検証範囲はこの架空例1回。時短や他の入力での精度は未計測。

## ショートv02の実演経路

同じローカルCLIで、架空のテンプレート・商談メモ・提案条件を3ファイルとして読み込み、青葉製作所の提案書初稿を別ファイルに書き出した。台本と画面の要約は実際に保存された初稿と元資料を照合した内容。 [入力、初稿、検査記録](PROPOSAL_SHORT_REVISION_V02_JA.md) · [CLIリファレンス](https://code.claude.com/docs/en/cli-reference) · [権限規則](https://code.claude.com/docs/en/permissions)

## 音源と人物

- BGMは既存のローカル音源「ハッピータイム」甘茶の音楽工房。既定 `explanation_v1` と入力レベル調整を使用。公開時のメモは **Content ID登録なし**。 [楽曲ページ](https://amachamusic.chagasi.com/music_happytime.html) · [利用規約](https://amachamusic.chagasi.com/terms.html)
- 既存の男女4クリップは11月10日Fable 5.2案件のMiniMax出力と照合。今回のクロップ・開始位置・表示目的は [編集確認](EDITING_REVIEW_JA.md) と [再現手順](REPRODUCTION_JA.md) に記録。
