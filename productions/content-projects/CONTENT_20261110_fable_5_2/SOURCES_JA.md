# 出典と引用台帳

確認日 2026-11-10 JST。本文の9図を収録対象に確定。System Cardの付録図表と、記事本文のデモ映像や装飾は別資料とする。

| ID | 公式資料 | 支える内容 |
| --- | --- | --- |
| launch | [Claude Fable 5.2 and Mythos 5.2](https://www.anthropic.com/claude-fable-and-mythos-5-2) | 2026-11-09発表、本文全9図、14評価の比較表、速度と提供条件 |
| fable-spec | [Claude Fable 5.2](https://platform.claude.com/docs/en/models/fable-5-2/overview) | 100万コンテキスト、128K最大出力、8／40ドル、APIの既定effort、データ保持 |
| fable-previous | [Claude Fable 5.1](https://platform.claude.com/docs/en/models/fable-5-1/overview) | 10／50ドル、同条件で比較する前世代 |
| system-card | [Fable 5.2 and Mythos 5.2 System Card](https://www.anthropic.com/document/claude-fable-5-2-mythos-5-2-system-card) | 評価方法、行動監査、保護措置 |
| briefcase | [AA-Briefcaseの採点方法](https://artificialanalysis.ai/articles/aa-briefcase/) | ルーブリックとEloの意味 |
| sol-launch | [Introducing GPT-6.1 Sol](https://openai.com/index/introducing-gpt-6-1-sol/) | GPT-6.1 Solの公開内容と2／10ドルの標準API単価 |
| sol-docs | [GPT-6.1 Sol API model](https://developers.openai.com/api/docs/models/gpt-6.1-sol) | 公開モデルIDと特徴 |
| openai-models | [OpenAI APIモデル一覧](https://developers.openai.com/api/docs/models) | GPT-6.1 Solの掲載と、仮称Sol 6.2を公式資料で確認できなかった範囲 |

## 使用する図と条件

| 番号 | 公式図 | 確認した条件と使う箇所 |
| --- | --- | --- |
| 1 | FrontierCode 2.0 | コード修正、費用対スコア。45.3% High、49.1% Xhigh |
| 2 | WANDR | 緩和基準の採点、MediumとOpusの最高点の費用比 |
| 3 | BenchCAD 2.1 | ツールあり、形状と回路の一致度を0〜100点で採点 |
| 4 | Humanity’s Last Exam | ツールあり、LowとOpusの最高点の費用比 |
| 5 | Chartography | ツールなし、MediumとOpus Maxの比較 |
| 6 | CVE Rediscovery | Mythos 5.2、修正前コードから既知の脆弱性を再発見 |
| 7 | Fermat proof formalization | Lean、約1,000エージェント、各モデル1回、18時間で再開 |
| 8 | RoboDojo | シミュレーター、提供元の実行環境での平均成功率 |
| 9 | Automated behavioral audit | Mythos 5.2、約1,900シナリオの複合指標、低いほど良い |

取得はWindowsの分離したPlaywright Chromium。表示領域1600×1050、device scale factor 2。原本を `captures-v02/original` に、図のパネルのみを `captures-v02/quotes` に保存。数値、凡例、色、軸の画素を保持し、下部の英文本文は範囲外にした。比較表は固定ヘッダーの位置だけ撮影時に解除し、列見出しを反復して14評価を3分割した。URL、取得時刻、寸法、座標、SHA-256は `captures-v02/manifest.json` を参照。

公開されている資料のうち、解説に必要な図と表に範囲を絞り、画面で引用と自作説明を分け、発表者と発表日を表示した。公開用の個別許諾や一般再配布ライセンスは確認できていない。記事素材はレビュー用の引用候補として保持し、公開時の引用範囲と各媒体の適用条件を確認する。 [Anthropic Legal Center](https://www.anthropic.com/legal) [文化庁の引用に関する説明](https://www.bunka.go.jp/seisaku/bunka_gyosei/kibankyoka/faq/index.html)
