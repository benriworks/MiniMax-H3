# Fable 5.2解説の制作記録

2026-11-10 JST。案件 `CONTENT_20261110_fable_5_2`。依頼の原文と制作上の判断は [企画v01](PROPOSAL_JA.md)、楽曲の追加依頼は [BGM改訂](BGM_REVISION_JA.md) に保存。

## 現在地

ショートv02とフルv03はローカル音源を使用したレビュー版。両方でAnthropicの共同発表本文に掲載された全9図を引用した。フル版は14評価の比較表、架空グラフ1枚を読ませたClaude Codeの実行結果、公開済みGPT-6.1 Solと次のSolへの期待も収録。仮の呼称「Sol 6.2」は期待の場面だけで使った。

| 版 | ローカル成果物 | 技術検査 |
| --- | --- | --- |
| ショート v02 | `release/v02/short/fable-5-2-short-v02.mp4` | 82.250秒、1080×1920、24 fps、1,974フレーム、-16.03 LUFS、-2.23 dBTP |
| フル v03 | `release/v03/full/fable-5-2-full-v03.mp4` | 349.792秒、1920×1080、24 fps、8,395フレーム、-16.02 LUFS、-1.92 dBTP |
| 記事 v01 | `blog-handoff/v01/index.html`、`blog-handoff/fable-5-2-article-review-v01.zip` | 12画像の照合、360pxと1050pxの表示確認、ZIP再読取 |
| 企画・台帳 | `workspace-state-v01.json` | 共通CLI revision 32。制作に用いた構成はv01、ユーザーの最終採用はレビュー後に記録 |

成果物のルートは `outputs/content-projects/CONTENT_20261110_fable_5_2/`。各動画の `verification.json` が最終hash、H.264ストリーム照合、元の画面検査を保持。フル版の4台詞の発音をv03で修正した。[検査記録](DELIVERY_QC_JA.md)を参照。字幕SRTは各版へ保存した。人の最終試聴、スマホ実機再生、ユーザー採用、公開は確認待ち。

## 撮影と根拠

- Claude Desktopは再サインイン表示、ChromeのComputer Useは現在のURLを判定できず終了。デスクトップのモデル選択画面は未取得。WindowsのClaude Codeで明示モデルを指定し、実行ログの利用モデルIDと値を照合した。CLIは別名に関する警告を出したが、応答のモデル利用記録には `claude-fable-5-2` のみが載った。図と抜粋は [記事草稿](article-draft-v01.md) に対応。
- 公開ページは独立Chromiumで開き、タブの折りたたみメニューも操作して全9図を捕捉。軸、凡例、マーカーを含む公式パネルを原本から切り出した。比較表はサイトの固定ナビが重なったため、撮影時だけ表以外を不可視にした。修正前の原本を保持し、ヘッダー付き素材のパスを新しく登録した。
- 動画の字幕と色の強調は引用枠の外側。実演は架空の1例で、動画内のAnthropicの比較結果と分けた。出典、条件、確認日は [出典台帳](SOURCES_JA.md) へ。
- 既存の男女のMiniMax動画を、導入、期待、締めとグラフの読み方のPIPに使用。値や表を読む場面では図を広く取り、字幕は図の下に配置した。

## 再開手順

1. `captures-v02/manifest.json` と `motion/manifest.json` で図の原本と既存キャラを照合する。台本は `story-v01.json`。元の素材と台詞の再送は、必要な修正に限る。
2. `produce.py preview short` または `produce.py preview full` で組版を検査する。初版は `produce.py render`、ローカル音源版は `remix_local.py --inventory <既存の曲庫台帳>` で生成した。生成先は版ごとの独立パスとする。
3. 仕上がりの `verification.json`、代表フレーム、音声レビューを照合する。Drive受領は `_private` の記録で確認する。原曲、音声、動画、ZIP、クラウド共有IDはGit管理外。
4. [投稿文面](YOUTUBE_DRAFTS_JA.md) でタイトル、概要欄、章、楽曲クレジットを確認する。記事の画像は受け渡しZIPの `assets/` を参照する。引用の採否と公開は動画と記事で個別に確認する。
