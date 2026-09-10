# テンプレート素材の出典・再配布条件

確認日: 2026-09-06。ここにあるフォントは OS にインストールせず、Studio と動画レンダラーからローカルファイルとして利用する。

## Noto Sans JP

- 配布元: [Google Fonts の公式リポジトリ](https://github.com/google/fonts/tree/66a36c8c94b1a5d992ee4e7f392fccfe4945767c/ofl/notosansjp)
- 固定コミット: `66a36c8c94b1a5d992ee4e7f392fccfe4945767c`
- [公式メタデータ](https://github.com/google/fonts/blob/66a36c8c94b1a5d992ee4e7f392fccfe4945767c/ofl/notosansjp/METADATA.pb)
- [フォントの取得 URL](https://raw.githubusercontent.com/google/fonts/66a36c8c94b1a5d992ee4e7f392fccfe4945767c/ofl/notosansjp/NotoSansJP%5Bwght%5D.ttf)
- [ライセンスの取得 URL](https://raw.githubusercontent.com/google/fonts/66a36c8c94b1a5d992ee4e7f392fccfe4945767c/ofl/notosansjp/OFL.txt)

| ローカルファイル | バイト数 | SHA-256 |
| --- | ---: | --- |
| `NotoSansJP-Variable.ttf` | 9,589,900 | `c2f3b4d463500a2ddcd3849cded1fceeb9fd6d1c32e6cbecd568453ba50fc68f` |
| `OFL-NotoSansJP.txt` | 4,388 | `1c05c68c34f9708415aada51f17e1b0092d2cea709bf4a94cd38114f9e73d7d9` |

両ファイルの内容は取得元から未改変。ローカルファイル名のみ変更し、フォント内部の名前・字形・メタデータは変更していない。Git blob SHA-1 も取得元 API と照合済み: フォント `cdd8f083c1f5928ff3361f8cda4d3fc9462cbe89`、ライセンス `1c9f43281b8f216c5461fe9ac729afbade7724e4`。

### 利用条件

SIL Open Font License 1.1。著作権表記とライセンス全文を `OFL-NotoSansJP.txt` に同梱する。フォント単体を販売せず、再配布時も同ファイルを残す。フォントで作成した動画や画像そのものに OFL を適用する必要はない。詳細と原文が優先する。

### 実ファイルの確認

- ファミリー: `Noto Sans JP`。内部バージョン: `Version 2.004-H2;hotconv 1.0.118;makeotfexe 2.5.65603`。
- 可変軸: `wght` 100–900。**初期値は 100 / Thin** のため、見出し等の用途では太さを明示する。Pillow では `set_variation_by_axes([700])` 等、ブラウザでは `@font-face` の `font-weight: 100 900` と利用側の太さ指定が必要。
- 既存 Pillow / FreeType による読み込みと可変軸を確認済み。追加パッケージのインストールは行っていない。
- TrueType の `name` と Unicode `cmap` format 12 テーブルを標準ライブラリで読み取った。次のサンプルに含まれる異なる 49 文字はすべて非ゼロのグリフ ID に対応する。全日本語文字への網羅的保証ではない。

```text
Claude Code 告知文を３案 条件を添えて三案まとめて依頼。思考中 技術解説 日本語 読みやすい 規約 範囲 橙色 製品
```

## 製品ロゴ

このディレクトリには Claude / Anthropic のロゴは同梱していない。フォントの利用許諾は製品ロゴの利用許諾を意味しない。
