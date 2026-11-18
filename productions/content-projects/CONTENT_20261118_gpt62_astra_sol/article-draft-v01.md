# GPT-6.2 AstraとSolの違い。Codexでどちらを選ぶ？

OpenAIは2026年11月17日、GPT-6.2 AstraとGPT-6.2 Solを発表しました。予約ボタンの文言を直すような日常の作業はSolから。予約の記録を追って、メールが届かない原因を調べるならAstraが候補です。モデルを選ぶときは、作業の範囲と確認に必要な手順を見ます。 [OpenAI公式発表](https://openai.com/index/introducing-gpt-6-2-astra-sol/)

## 変更箇所が分かっているときはSol

**GPT-6.2 Sol**は、普段のコーディングや文章作成、複数の手順を含む日常業務向けです。予約ボタンの文言を直すなら、変更する画面と対象の文言を渡します。プルリクエストのレビューなら、気になる変更点と確認してほしい条件を添えます。 [ChatGPT Learnの利用ガイド](https://learn.chatgpt.com/docs/whats-new/gpt-62-astra-sol)

## 原因調査からテストまで任せるならAstra

予約が成功した表示は出るのに、確認メールが届かない。画面だけでは予約処理と通知処理のどちらを調べればよいか分かりません。OpenAIが複雑な作業に位置づける **GPT-6.2 Astra** を使うなら、再現手順と期待する動作を渡し、どこを調べて、どのテストを実行したかを確認します。これは依頼の組み立て方を示す架空の例です。 [ChatGPT Learnの利用ガイド](https://learn.chatgpt.com/docs/whats-new/gpt-62-astra-sol)

## 公式のスライド作例で見るAstra

OpenAIは取引状況の更新を、既存の1枚に合わせて作る例を公開しています。新しいAstraの出力には見本の濃紺の帯があり、2店舗での試験導入が決まったことが見出しに入っています。表は次の作業、担当、日付を並べています。比較相手は旧GPT-6 Astraです。 [OpenAIの公式作例](https://openai.com/index/introducing-gpt-6-2-astra-sol/#slideshows)

<!-- figure:slide-template -->

<!-- figure:slide-comparison -->

最初に決まったことを読み、次に表から担当と期限を確認できます。実務では、見出しや表の数字と担当者を渡した元資料と照合します。

<!-- figure:slide-astra-detail -->

## ChatGPT WorkとCodexのモデル選択

通常のChatから利用する場合は、ChatGPT Workを開きます。公式の利用ガイドは対象プランとしてPlus、Pro、Business、Enterprise、Eduを挙げています。EnterpriseとEduではワークスペース管理者による有効化が必要です。Codexアプリでは入力欄のモデル選択、CLIでは `/model` が入口です。制作PCのCodexでは、モデル選択欄にSolとAstraが並んでいることを確認しました。 [ChatGPT Learnの利用ガイド](https://learn.chatgpt.com/docs/whats-new/gpt-62-astra-sol)

<!-- figure:app-composer -->

<!-- figure:app-model-picker -->

## APIの標準単価

2026年11月18日に確認した、標準APIの100万トークンあたりの米ドル単価です。利用するサービス階層により条件は異なります。 [OpenAI公式発表の料金](https://openai.com/index/introducing-gpt-6-2-astra-sol/#pricing-and-availability)

| モデルID | 入力 | キャッシュ入力 | 出力 |
| --- | ---: | ---: | ---: |
| `gpt-6.2-sol` | $2.00 | $0.10 | $10.00 |
| `gpt-6.2-astra` | $8.00 | $0.40 | $40.00 |

同じ量の入力と出力なら、各標準単価はAstraがSolの4倍です。たとえばキャッシュを使わず、入力10万、出力1万トークンを仮定すると、Solは0.30ドル、Astraは1.20ドルです。実際に使うトークン数はモデルや依頼によって変わります。 [Solのモデル資料](https://developers.openai.com/api/docs/models/gpt-6.2-sol) [Astraのモデル資料](https://developers.openai.com/api/docs/models/gpt-6.2-astra)
