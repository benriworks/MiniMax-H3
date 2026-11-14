# ClaudeがGoogle Meetに参加して、会議中に資料も作る

イベント会議で日程を決めている間に、会場予約、招待状、名札印刷をホワイトボードに並べる。Anthropicが11月12日に発表したClaude Meetingsの公式例です。Google Meetに参加したClaudeは、会話を文字に起こすほか、頼まれた文書、ホワイトボード、スライドなどを会議中に作れます。 [Anthropic公式発表](https://claude.com/ja/resources/articles/claude-meetings)

![Google Meetの参加者一覧と、Claudeのタイル](images/participant.webp)

*引用　Anthropic「Introducing Claude Meetings」。画面下段のClaudeタイルが参加を示す。*

## 会議の前、途中、終わったあと

### 会議前にGoogle Calendarから予定を選ぶ

Claude Meetingsは、ClaudeのWeb版とDesktopでTeam・Enterprise向けに順次提供中のベータです。組織の所有者がGoogle Calendarを有効にし、利用者が自分のカレンダーを接続します。ClaudeのMeetingsでGoogle Meet付きの予定を選び、参加者全員が文字起こしに同意してから「Add Claude」を押します。自動参加を使う場合も、参加者への説明が先です。 [Claude公式ヘルプ](https://support.claude.com/en/articles/18325154-use-claude-meetings)

![Claude公式ヘルプにある参加者の同意と会議への追加手順](images/help-screen.webp)

*引用　Claude Help Center「Use Claude Meetings」。文字起こしへの同意と、カレンダーから予定を選ぶ手順。*

### 会議中に日程や担当を並べる

Meetの会議画面では、Claudeは参加者として表示され、チャットにも参加を通知します。「クロード、この予定をホワイトボードにして」と話しかけるか、チャットから依頼できます。通常の回答は会議チャットへ文字で返ります。Anthropicの公式例では、会場を予約する月、招待状を送る月、名札を印刷する月がボードに並びます。招待されたチームの人は、会議ページで作成物を編集できます。 [Anthropic公式発表](https://claude.com/ja/resources/articles/claude-meetings)

![顧客イベントのホワイトボードと会議の参加者が並んだ公式例](images/meeting-plan.webp)

*引用　Anthropic公式発表。左に予定と担当、右にClaudeと参加者のタイル。*

### 会議後に、次の担当と期限を確認する

Meetのチャットに投稿されるリンクからClaudeの会議ページを開くと、要約、決定事項、アクション項目、文字起こし、作成した資料を確認できます。アクション項目は、会議のあとに誰が何をするかを示します。決定事項と担当・期限は元の会話と照合できます。 [Claude公式ヘルプ](https://support.claude.com/en/articles/18325154-use-claude-meetings)

![Claudeの会議ページに、チャット・議事録・イベント計画・予定表が並ぶ](images/meeting-page.webp)

*引用　Anthropic公式発表。議事録の欄には要約、決定事項、アクション項目があり、上のタブで作成物を開ける。*

### 組織設定、共有、費用

| 項目 | 公式ヘルプで確認できた条件 |
| --- | --- |
| Team | Meetingsは既定でオン。外部ゲストを含む会議も既定で許可され、所有者は変更できる。 |
| Enterprise | 管理者が対象メンバーに機能を有効化。外部ゲストを含む会議には追加の設定が必要。 |
| ベータ対象外の例 | データ保持なし（ZDR）、HIPAA対応構成、顧客管理の暗号化鍵（CMEK）を使う一部の組織。 |
| 共有 | 組織内の招待者が会議ページを開ける。許可済みの外部ゲスト会議でも、ゲストに会議ページや要約メールは届かない。Meetチャットは参加者に見える。 |
| 保存 | 文字起こし、要約、画面の説明を保存。音声ファイルは保存しないと公式ガイドに記載。 |
| 利用料 | 議事録・文字起こし・接続ツールを使わない回答は対象プランに含まれる。会議内の文書・ホワイトボードは2027年2月10日まで無料。接続ツール利用は本人の利用量に数えられ、組織に料金が発生する場合がある。 |

[設定・共有・利用料の公式説明](https://support.claude.com/en/articles/18325154-use-claude-meetings)

今回は公開された公式画面で作業の流れを確認しました。このPCのアカウントへの展開、Google Meetへの参加、日本語の認識精度、利用量の実測は未検証です。模擬会議で検証する場合は、全員が同意したうえで架空のイベントの担当3名・期限3件を話し、会議ページの文字起こしと各成果物で一致するかを照合します。

## Claude CodeのCode Modeは、ツールの使い方をまとめる

Claude Code v2.1.323に、既定で無効の実験機能Code Modeが加わりました。公開時刻は11月12日22:12 UTC、日本時間では11月13日7:12です。通常の道具の呼び出しでは、Claudeが検索や読み取りの結果を見て次の操作を選びます。Code Modeでは、Claudeが複数のツールを呼ぶJavaScriptを書き、検索結果を次の読み取りへ渡したり、独立した操作を並行させたりできます。 [公式リリース](https://github.com/anthropics/claude-code/releases/tag/v2.1.323) [公式ガイド](https://code.claude.com/docs/en/code-mode)

![Claude Code公式ガイドのCode Modeの説明と既定無効の注記](images/code-screen.webp)

*引用　Claude Code Docs「Run tool calls from code with Code Mode」。*

たとえば「ローカルのMarkdownを探し、リンク切れを一覧にする」作業なら、探す、読む、結果をまとめる手順を一つのJavaScriptに組めます。ガイドには、ネイティブ版v2.1.323以降、対話型ターミナル、Claude契約またはConsoleアカウント、WindowsではGit for Windowsが必要とあります。対応モデルはOpus 5.5、Sonnet 5.5、Haiku 5.5、Fable 5.2。Desktop、VS Codeのパネル、非対話の `-p`、Agent SDK、クラウドセッションは対象外です。外部ゲートウェイや一部の組織設定にも制限があります。 [公式の要件と制約](https://code.claude.com/docs/en/code-mode#requirements)

このPCのClaude Codeは2.1.316でした。動画の作業比較は仕様の説明図です。実際の時間、モデルの利用量、費用を比較するには、同じモデル・入力・作業フォルダーで条件をそろえ、結果の一致を確認します。

## 同日のOpenAI公式更新

11月13日、米国の対象ChatGPT Pro利用者向けにChatGPT Walletがdotsで順次展開されました。Codex CLI 0.169.0もターミナルのサイドチャットなどを更新しています。 [ChatGPT Wallet公式発表](https://openai.com/index/introducing-chatgpt-wallet/) [ChatGPT・Codex変更履歴](https://learn.chatgpt.com/docs/changelog)

---

記事と動画は11月13日版。一次資料の取得・確認は2026年11月14日（JST）。動画BGMは甘茶の音楽工房「ハッピータイム」。 [曲ページ](https://amachamusic.chagasi.com/music_happytime.html)
