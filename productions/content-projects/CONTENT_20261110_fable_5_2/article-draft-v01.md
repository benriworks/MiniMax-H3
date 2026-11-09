# Claude Fable 5.2の性能と費用を、公式9グラフから読み解く

2026年11月9日、AnthropicがClaude Fable 5.2とClaude Mythos 5.2を発表しました。Fable 5.2では、旧世代より標準API単価が2割下がりました。コード修正や図表読解などでは、推論の深さを抑えても旧モデルの高い設定と同程度か、それを上回る結果が出ています。どの作業で、どの設定を選ぶと費用に見合うのでしょうか。 [Anthropicの公式発表](https://www.anthropic.com/claude-fable-and-mythos-5-2)

## 標準API単価と、1件を終える費用

標準APIの料金は、100万トークンあたり入力8ドル、出力40ドルです。Fable 5.1の入力10ドル、出力50ドルと比べると、それぞれ20%下がりました。たとえば入力10万、出力2万トークンを同じ量だけ使うと、標準単価での計算は2.00ドルから1.60ドルになります。実際の費用には、使ったトークンの量、キャッシュ、追加の試行やツールも影響します。 [Fable 5.2の仕様](https://platform.claude.com/docs/en/models/fable-5-2/overview) [Fable 5.1の仕様](https://platform.claude.com/docs/en/models/fable-5-1/overview)

Anthropicによると、通常時の出力生成は前世代比で最大30%高速です。別に用意されたFast modeはトークン生成を最大2.5倍に速め、100万トークンあたり入力16ドル、出力80ドルです。コンテキストは100万トークン、最大出力は128K。APIの既定の `effort` は `high`、ClaudeアプリとClaude Codeの既定は発表時点でMediumと案内されています。APIは原則30日のデータ保持が必要で、例外はAnthropicの認可などの条件に従います。 [Anthropicの公式発表](https://www.anthropic.com/claude-fable-and-mythos-5-2) [Claude Platform Docs](https://platform.claude.com/docs/en/models/fable-5-2/overview)

## スコアと費用の位置

最初の5図の縦軸はスコア、横軸は1タスクまたは1試行あたりの米ドルです。横軸は**対数目盛り**で、同じ倍率が同じ間隔になります。点の高さが同程度なら、左側の点ほど費用が低くなります。同じ色の点でもLow、Medium、High、Xhigh、Maxといった推論設定によって位置が変わります。ツールの有無と比較した点の設定を見てから、費用を読み取ります。 [Anthropicの公式発表](https://www.anthropic.com/claude-fable-and-mythos-5-2)

### 1. FrontierCode 2.0

オープンソースのリポジトリで、保守担当者が変更を受け入れられる水準かを測ります。Fable 5.2のHighは45.3%、Opus 5.5のMaxは45.5%。この2点ではFableの1件あたり費用が約半分でした。Fable 5.2のXhighは49.1%で、設定を上げた場合の点も同じ図にあります。

![FrontierCode 2.0のスコアと費用。Fable 5.2 HighとOpus 5.5 Maxは近い高さにある](assets/frontiercode.png)

引用元はAnthropic公式発表。以下の9図と比較表は2026年11月10日確認。 [Anthropicの公式発表](https://www.anthropic.com/claude-fable-and-mythos-5-2)

### 2. WANDR

広い範囲の情報を集める評価です。緩和基準の採点では、Fable 5.2のMediumがOpus 5.5の最高スコアと同程度に達し、1試行あたりの費用は約40%でした。比較表の82.1%は、Fable 5.2について掲載された上位設定の値です。

![WANDRの緩和基準スコアと費用。Fable 5.2の線は同じ高さで左寄り](assets/wandr.png)

### 3. BenchCAD 2.1

ツールを使い、モデルが設計した形状と回路が参照とどの程度一致するかを部分点込みで採点します。Fable 5.2のMaxは83.5点で、Opus 5.5は65.3点、Fable 5.1は44.4点でした。ここでの尺度は0〜100点です。

![BenchCAD 2.1の設計スコアと費用。Fable 5.2のMaxは83.5点](assets/benchcad.png)

### 4. Humanity’s Last Exam

専門分野を横断する難問の評価です。ツールありの条件で、Fable 5.2のLowはOpus 5.5の最高スコアと同程度で、費用は10分の1未満でした。公式表のFable 5.2のスコアは74.2%です。

![Humanity’s Last Examのスコアと費用。Fable 5.2のLowとOpus 5.5の高い設定を比較できる](assets/hle.png)

### 5. Chartography

ツールを使わずに図表から値や関係を読み取ります。Fable 5.2のMediumは66.4%、Opus 5.5のMaxは64.4%。この比較点で、Fable側の費用は10分の1未満でした。公式表にはFable 5.2の73.4%も掲載されています。

![Chartographyのスコアと費用。図表読解はツールなしの条件](assets/chartography.png)

## 性能比較表の読み分け

公式表は、特記がある場合を除き各モデルで利用できる最高の推論設定を掲載し、Fable 5.2、Fable 5.1、Opus 5.5は原則として保護措置ありの結果です。AutomationBenchではFable 5.2が51.4%、Gemini 4 Carbonが53.9%でした。OSWorld 2.1の89.3%はオフライン課題の部分点を含みます。AA-Briefcase v1.1ではFable 5.2がルーブリック66.1%、Opus 5.5が61.2%ですが、採点と成果物の分析・見せ方の質を組み合わせたEloでは1785と1800で順序が入れ替わります。 [Anthropicの公式発表](https://www.anthropic.com/claude-fable-and-mythos-5-2) [Artificial Analysisの採点方法](https://artificialanalysis.ai/articles/aa-briefcase/)

![Anthropic公式比較表の全体。Fable、Opus、GPT-6 Astra、Gemini 4 Carbonの条件別スコア](assets/benchmark-table.png)

### 6. CVE Rediscovery

既に公開された脆弱性を、修正前のコードから見つけ直すAnthropicの内部評価です。ここで評価された新モデルはMythos 5.2で、公式表は89.6%です。FableとMythosは基盤モデルを共有し、保護措置と提供条件が異なります。サイバーや生物分野の業務でMythosを使う組織には検証プログラムの条件があります。

![CVE Rediscoveryの脆弱性再発見率と費用。Mythos 5.2が比較対象](assets/cve.png)

### 7. フェルマーの最終定理の形式化

既知の証明を、Leanで機械検証できる形にする実験です。各モデルについて約1,000エージェントを用いた1回の実行を比較しました。Fable 5.2は開始から18時間で86%に達し、保存地点からの再開を経て合計30時間で完了しました。同じ実験設定のOpus 5.5は終了時に27%でした。

![フェルマーの最終定理の形式化進捗。18時間で中断し、合計30時間でFable 5.2が完了](assets/fermat.png)

### 8. RoboDojo Sim

カメラ画像をもとにシミュレーター上の双腕ロボットを制御します。Anthropicが各モデルを同じ実行環境で試した内部評価で、Fable 5.2の平均成功率は64.9%、Fable 5.1は27.6%、GPT-6 Astraは29.8%です。図中のGeminiは4 Argonで、比較表のGemini 4 Carbonとはモデルが異なります。

![RoboDojoの平均成功率。Fable 5.2は64.9%](assets/robodojo.png)

### 9. 自動行動監査

約1,900のシナリオで望ましくない行動を調べた複合スコアです。この図は低いほど良く、Mythos 5.2が2.67、Mythos 5.1が3.28です。値の意味は監査の条件と組み合わせて読みます。 [Fable 5.2・Mythos 5.2 System Card](https://www.anthropic.com/document/claude-fable-5-2-mythos-5-2-system-card)

![自動行動監査の複合スコア。低いほど良く、Mythos 5.2は2.67](assets/audit.png)

## Claude Codeでの図表読解

WindowsのClaude Codeでモデルを `claude-fable-5-2` に指定し、週別の差し戻し件数を描いた架空のPNGを読ませました。尋ねたのは、新工程が既存工程を初めて下回った週、その週の両件数、4週目の差です。

![架空の差し戻し件数。1週目から4週目までの既存工程と新工程の折れ線](assets/demo-input.png)

初回出力は、2週目に既存工程が約20件、新工程が約17件となり、4週目の差は約4件と回答しました。用意した値と一致し、回答は目盛りからの読み取り値であることも添えていました。実行ログのモデル利用記録で指定モデルを確認しました。試行は1枚・1回です。

![Claude Codeの実行ログの抜粋。2週目に初めて逆転し、4週目の差を約4件と回答](assets/demo-output.png)

## OpenAIの次のSolに期待すること

OpenAIが公開したGPT-6.1 Solは、標準API単価が100万トークンあたり入力2ドル、出力10ドルです。OpenAIはコーディング、コンピューター操作、専門業務のいくつかの評価でAstraに近づいたと報告しています。2026年11月10日確認時点で、今回例に挙げた「Sol 6.2」という名称の製品は公式発表とモデル一覧で確認できませんでした。 [GPT-6.1 Sol公式発表](https://openai.com/index/introducing-gpt-6-1-sol/) [OpenAI APIモデル一覧](https://developers.openai.com/api/docs/models)

次のモデルで見たいのは、同じ仕事を最後まで任せられる範囲です。たとえば同じバグ修正を、同じテストと権限で試すなら、テストを通過した割合、完了までの時間、やり直しを含めた費用を揃えて比べられます。表や画像の説明なら、回答を元資料の箇所に戻って確かめられるとレビューしやすくなります。ブラウザやアプリを操作する仕事では、保存までの記録を追えて、送信など影響のある操作の前に人が判断できることにも期待しています。
