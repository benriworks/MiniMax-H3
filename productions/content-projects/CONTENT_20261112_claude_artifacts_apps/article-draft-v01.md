# Claudeで試食会の企画を予算表に。Whiteboards・Sheetsと外部アプリの使い方

試食セットを40個から45個に変えると、Claude Sheetsの合計は64,000円から67,250円に変わりました。予算上限は70,000円で、残りは2,750円です。11月10日に発表された機能を、11月12日に日本語のClaude Web版で試しました。

![試食セット45個に変更したClaude Sheets。合計67,250円、残額2,750円](images/sheet-after.png)

*撮影　Claude 日本語Web版、2026年11月12日。合計セルを選ぶと上の数式バーに `=SUM(D2:D4)` が出る。*

## 11月10日に加わった機能

| 機能 | 提供状況 | 使いどころ |
| --- | --- | --- |
| Claude Whiteboards | ベータ | 企画の工程をカードと矢印で整理 |
| Claude Sheets | ベータ | 数量や単価をセルで編集して、数式で予算を計算 |
| Claude Data | 一般提供 | データソースを接続し、実績を集計してダッシュボードを作成 |
| 対応アプリの横表示・全画面 | 順次展開 | 既存の文書や資料をClaudeのそばで開いて作業 |

Claude Dataは従来のClaude Dashboardsです。認定クエリとライブ共有は引き続きベータです。 [Artifactsの公式発表](https://claude.com/resources/articles/sheets-whiteboards-data) [Claude Data公式ヘルプ](https://support.claude.com/en/articles/17454700-get-started-with-claude-data)

## 1. Whiteboardsで試食会の準備を整理する

Claudeの「Artifacts」で「ホワイトボード」を開き、「チャットする」から、会場の予約、試食セットの手配、チラシの配布を3枚のカードで整理するよう頼みました。「12月1日、5日、8日」の日付と「予算上限70,000円」も入れています。

![商店街の試食会の準備を3枚のカードと矢印にしたWhiteboards](images/board.png)

*撮影　Claude 日本語Web版、2026年11月12日。架空のイベント。* [Claude Whiteboards公式ヘルプ](https://support.claude.com/en/articles/18324319-get-started-with-claude-whiteboards)

## 2. Sheetsで同じ企画の予算表を作る

別のチャットで、同じ企画の費目、数量、単価、予算上限を渡しました。「Claude Sheetsで、手でセルを編集できるスプレッドシートを作って」と伝え、タブを「予算」にしました。列は費目、数量、単価、金額の4つです。

| 行 | 費目 | 数量 | 単価 | 金額の式 |
| --- | --- | ---: | ---: | --- |
| 2 | 会場費 | 1 | 30,000円 | `=B2*C2` |
| 3 | 試食セット | 40 | 650円 | `=B3*C3` |
| 4 | チラシ | 100 | 80円 | `=B4*C4` |
| 5 | 合計 | | | `=SUM(D2:D4)` |
| 6 | 予算上限 | | | 70,000円を入力 |
| 7 | 残額 | | | `=D6-D5` |

初期値は合計64,000円、残額6,000円でした。B3を45にすると、試食セット代は29,250円、合計は67,250円、残額は2,750円になりました。増加分は650円×5個で3,250円です。

![試食セット40個の予算表。合計64,000円、残額6,000円](images/sheet-before.png)

*撮影　Claude 日本語Web版、2026年11月12日。* [Claude Sheets公式ヘルプ](https://support.claude.com/en/articles/18324300-get-started-with-claude-sheets)

### Excelで持ち出す

表のタイトルメニューから「エクスポート」→「Excel」を選択しました。書き出した `.xlsx` には、金額3件、合計、残額の5式が保存されていました。D5とD7の保存値は67,250円と2,750円です。確認範囲はこのファイルの数式・保存値と、Sheets上の再計算です。Excelデスクトップ上での再計算は未検証です。

![Claude Sheetsのエクスポートメニュー。Excel形式を選択](images/excel-menu.png)

*撮影　Claude 日本語Web版、2026年11月12日。*

### Claude Dataで実績を集計するには

来場者数や売上を継続して集計する場合は、データウェアハウスやCRMなどを接続し、Claude Dataで質問します。Claude SheetsからDataへのライブデータ連携は非対応です。今回のPCではDataの入口を確認しました。接続先でのダッシュボード生成は未検証です。 [Claude Data公式ヘルプ](https://support.claude.com/en/articles/17454700-get-started-with-claude-data) [Claude Sheets公式ヘルプ](https://support.claude.com/en/articles/18324300-get-started-with-claude-sheets)

## 3. Claudeの横で対応アプリを開く

対応するコネクタでは、アプリをチャットの横に開いたり全画面に広げたりできます。公式のConfluenceデモは、開いている企画書にClaudeが要約を追記する例です。自分でも同じ画面を操作し、Claudeに頼んだ変更は必要に応じて承認できます。 [インタラクティブコネクタの公式発表](https://claude.com/resources/articles/interactive-connectors-full-tool)

![公式デモ。左のClaudeチャットと右のConfluence企画書](images/confluence.png)

*引用　Anthropic公式デモ「Your apps have moved into Claude」約22秒、2026年11月12日確認。* [公式デモ](https://www.youtube.com/watch?v=Gy1jSeSzAhk)

日本語版の「カスタマイズ」→「コネクタ」から、おすすめのインタラクティブコネクタを確認できました。この環境ではVercelが接続済みで、公開ドキュメント検索を1回許可すると、結果がテキストで返りました。利用できる表示や操作は、呼び出す機能、コネクタ、接続先の権限で変わります。外部サービスには提供元の利用条件が適用されます。 [インタラクティブコネクタ公式ヘルプ](https://support.claude.com/en/articles/13454812-use-interactive-connectors-in-claude) [コネクタの利用条件と権限](https://support.claude.com/en/articles/11176164-use-connectors-to-extend-claude-s-capabilities)

## 対象プランと組織の設定

- **Whiteboards、Sheets、Data**はPro、Max、Ultra、Team、Enterpriseが対象。Teamでは3機能が既定でオン。EnterpriseではWhiteboardsとSheetsが既定でオフ。Dataは、所有者が設定を保存済みの場合を除き、11月19日に既定でオンになります。 [Claude公式発表](https://claude.com/resources/articles/sheets-whiteboards-data) [管理者ガイド](https://support.claude.com/en/articles/16994751-artifacts-admin-guide-for-team-and-enterprise-plans)
- **外部アプリの新しい表示**は、新しいClaudeのWeb版とデスクトップ版で全プランに順次展開中。チャット横・全画面の新表示はモバイル非対応です。組織ではコネクタの有効化と接続先の権限も確認してください。 [インタラクティブコネクタ公式ヘルプ](https://support.claude.com/en/articles/13454812-use-interactive-connectors-in-claude)
