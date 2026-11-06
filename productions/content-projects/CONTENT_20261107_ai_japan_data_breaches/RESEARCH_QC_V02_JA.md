# 追加照合と企画v02の確認結果

2026-11-07。[初回QC](RESEARCH_QC_V01_JA.md)に対する差分。対象は調査・企画で、動画の媒体検査ではない。

- BigEcho原HTMLのmeta refresh先を確認し、第一興商の初報本文を追加保存した。顧客約8,631,000件と従業員約93,000件を分け、約8,724,000件を比較候補へ反映。11/6続報でも外部へ送信された個人情報は特定されていないとする公表を維持した。
- 公式30出典・国内14候補の14件すべてを採点。N×I・順位順・出典参照を再計算し、上位10件のIDが初回案から変わらないことを照合した。Iの感度と5段階方式も更新。評価方式は未採用。
- 原本・公式CMS本文・原表画像は計35ファイルのhashを照合。初回に挙げた5つのローカル取得失敗はそのまま記録する。第一興商の移動元HTMLと移動先HTMLは両方保持する。
- 企画画像2点は主たる構成・Top10が変わらないため再利用し、初回のhash・bytes一致を確認。全文TXTだけv02へ更新し、Driveへ29,141bytesで保存。名前・サイズ・保存先・所有者のみの非公開状態を読戻し。v01共有ファイルを上書きしていない。
- 既存ContentWorkspaceのCLIで追加調査、同じ2本を継承する提案v02、記事の出典更新確認を記録。revision 7、`awaiting_feedback`、最新`proposal_japan_breaches_v02`、採用なし。記事の10事例・本文と人物は変更していない。
- 初回の軽量資料は`d2c780b`で個人forkへpushし、Draft PR #21のOPEN／Draft／mainベース／remote headを確認した。追加照合と本記録を同じブランチへ保存する。mainマージ・公式upstreamへの書込みは今回行わない。

引き続き未実施：本企画の採用、公式引用のPC実撮影、利用条件確認、MiniMax・TTS・動画書出し、媒体QC、人の試聴、スマホ実機、記事・YouTube公開。採用待ちの企画を完成した動画として案内しない。

詳細受領：`outputs/content-projects/CONTENT_20261107_ai_japan_data_breaches/_private/share/drive-proposal-v02.json`。初回画像と最新版TXTの関係は同案件の `review/v02/manifest.json`。共有URL・原本・画像・DB・私的受領はGit外。
