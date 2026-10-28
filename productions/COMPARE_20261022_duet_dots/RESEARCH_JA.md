# Claude Duetとdots：比較調査

確認日：2026年10月22日。指定4ページと、定時実行を確認するための追加1ページを開き、本文を確認した。調査対象は公式に記載された機能と利用条件。実際の同条件実行テストは行っていない。

| 比較軸 | Claude Duet | dots | 根拠 |
| --- | --- | --- | --- |
| 共通の土台 | 独自のクラウドPC・ブラウザーで作業を継続 | 独自のクラウドPC・ブラウザーで作業を継続 | [Duet発表](https://claude.com/resources/articles/claude-duet)、[dots接続](https://learn.chatgpt.com/docs/dots/computers-and-apps) |
| ① 知らせ方 | 朝の要点まとめ、一定間隔の確認 | 自発的にフォロー時期を判断。定時の反復は保存する予定で設定 | [Duet案内](https://support.claude.com/en/articles/17631495-get-started-with-claude-duet)、[Tasks and memory](https://learn.chatgpt.com/docs/dots/tasks-and-memory) |
| ② 作業の見え方 | 現プレビューではブラウザー閲覧・操作引継ぎ不可 | ブラウザーを開き、操作引継ぎと制御の返却が可能 | [Duet制限](https://support.claude.com/en/articles/17631495-get-started-with-claude-duet)、[dots接続](https://learn.chatgpt.com/docs/dots/computers-and-apps) |
| ② 手元PCとの接続 | 手元のPCファイルへアクセスできないという制限 | 許可したPC上のWork／Codex、新規・既存Codexへ連携。PCオンラインとChatGPT起動が必要 | [Duet制限](https://support.claude.com/en/articles/17631495-get-started-with-claude-duet)、[dots接続](https://learn.chatgpt.com/docs/dots/computers-and-apps) |
| ③ 提供条件 | 米国Pro／Maxの招待待ち。日本は対象外 | 対象プランと地域で順次提供。対象でも即利用は保証されない | [Duet案内](https://support.claude.com/en/articles/17631495-get-started-with-claude-duet)、[dots Access](https://learn.chatgpt.com/docs/dots) |
| ③ 利用枠 | 背景確認もClaudeの共通枠へ算入 | 会話はChatGPT枠外。Work／Codexの実作業は各製品の枠へ算入 | [Duet利用枠](https://support.claude.com/en/articles/17631495-get-started-with-claude-duet)、[dots Access](https://learn.chatgpt.com/docs/dots) |

## 表現上の重要点

- 発表日は公式ページに記載された2026年10月21日。日本時間へ換算した発売時刻や、日本での提供開始日ではない。
- Duetの米国条件は地域・アカウント条件であり、日本人という国籍を除くという説明にはしない。日本展開日は未確認。
- Duetの朝のまとめを、dotsには朝の確認ができないという差分にしない。dotsは予定を保存する経路がある。
- Duetのクラウド作業を常時・即時監視とはしない。一定間隔のため確認の間に緊急情報が届く場合がある。
- dotsのローカル接続と、クラウドPCを混同しない。手元PCを閉じても進む説明はクラウドの仕事に限定する。
- Duetに開発能力がないとは言わない。差分として確認したのは、ブラウザーの操作引継ぎとローカルCodex連携の経路である。
- Duetの既存Claude設定の引継ぎと、メインClaude本体のDocs／Slides実演を同じ機能として扱わない。
- dotsの会話枠の扱いから、全作業が無料・無制限と推論しない。具体的な深い作業の枠量は今回の資料で確定していない。

## 未確認と編集上の解釈

比較速度、出力精度、成功率、消費量の実測、日本語での運用品質、個別アカウントへの提供可否は未検証。朝の確認や途中の引継ぎを選択の観点にするのは編集上の整理で、性能の優劣ではない。架空の同一カフェ業務は理解のための例であり、成功した実操作として見せない。

詳細な主張・根拠の対応は `evidence-table.json`、引用語数と本文の確認範囲は `sources.json` を参照。
