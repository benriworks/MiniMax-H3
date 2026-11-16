# Claudeの利用指数で日本は32位。仕事でAIをどう広げる？

「日本がAIの非先進国に位置づけられた」という話題をきっかけに、Anthropicの元の地図を確認しました。日本は **121の国・地域のうち32位、指数は1.91**。公式の区分名は **Upper middle** で、人口当たりのClaude利用が上位4分の1に次ぐ層です。ダッシュボードの更新は2026年6月26日、表示された会話データの対象は同年5月です。 [Anthropicの国別画面](https://www.anthropic.com/economic-index#country-usage) · [調査報告書](https://www.anthropic.com/research/economic-index-june-2026-report)

## 32位の中身は、Claudeの人口当たりの会話量

![日本の国別画面。121の国・地域中32位、利用指数1.91](images/country.webp)

利用指数は、ある国がClaudeの全会話に占める割合を、その国が世界の15〜64歳人口に占める割合で割った値です。基準の **1.0** は人口比と会話比が同じ。日本では全会話に占める割合が **3.28％** で、人口比から期待される会話量の **1.91倍** でした。数値と順位は、Anthropicが公開した5月のCSVから照合しています。 [公式データ仕様](https://huggingface.co/datasets/Anthropic/EconomicIndex/blob/caa39af/release_2026_06_26/data_documentation.md) · [公開データ](https://huggingface.co/datasets/Anthropic/EconomicIndex/tree/caa39af/release_2026_06_26)

| 国 | Claude利用指数 |
| --- | ---: |
| オーストラリア | 6.40 |
| 米国 | 3.87 |
| 韓国 | 3.78 |
| 日本 | 1.91 |

![Claude利用指数を4色で表示するAnthropicの公式地図](images/map.webp)

地図の4区分は Leading、Upper middle、Lower middle、Emerging。色分けの対象はClaudeの利用です。地域別ファイルが含むのは個人向けFree・Pro・MaxのチャットとCoworkで、企業向けAPIは別のファイルで集計されます。Claudeを使う人が同じ月に何度も会話すれば、そのぶん会話量に反映されます。他社製品を含む国内普及や、人口の何％が利用したかを知るには、対象を広げた調査が必要です。 [Anthropicの世界地図](https://www.anthropic.com/economic-index#global-usage) · [公式データ仕様](https://huggingface.co/datasets/Anthropic/EconomicIndex/blob/caa39af/release_2026_06_26/data_documentation.md)

![日本の国別画面の全体。利用指数とよくある話題、タスクの分類](images/country-full.webp)

同じ5月のデータで、**日本のClaude会話の47.0％** が仕事向けと分類されています。世界全体では **43.36％**。ここでの分母は会話です。企業の何割がClaudeを仕事に使うかは、この比率からは分かりません。 [公開データ](https://huggingface.co/datasets/Anthropic/EconomicIndex/tree/caa39af/release_2026_06_26)

## 日本企業では導入が進み、基礎的な活用が6割

AWSが調査会社Strand Partnersに委託し、国内のビジネスリーダー1,000名と一般市民1,000名を対象に行った別の調査では、日本企業のAI導入率は **43％から54％** に上がっています。導入した企業に絞ると、**60％** は基礎的な活用や小さな効率化が中心でした。企業での導入を尋ねた調査と会話ログでは、観測する範囲も分母も異なります。 [AWS公式発表](https://press.aboutamazon.com/jp/2026/11/aws-research-finds-ai-adoption-accelerating-in-japan-with-a-narrowing-gap-between-advanced-and-basic-adopters)

![AWS調査の公表要点。日本企業の導入率54％、導入済み企業のうち60％は基礎的な活用](images/aws-points.webp)

ここからは私たちの提案です。国の順位を追うより、自分のチームで毎週繰り返す仕事を一つ選び、どの工程が楽になるか確かめてみます。

## 実演　架空の会議メモから次の作業を表にする

11月17日、架空の印刷会議メモをClaude Codeに入力し、決定事項と作業を分けて、後者を「作業・担当・期限」の表にするよう頼みました。抜けている担当や期限は「未定」とし、次回会議の日付を流用しないという条件を加えています。 [実演の入力](demo-prompt.txt) · [応答全文](demo-result-v01.md)

Claude Haiku 5.5は資料をA4片面にする決定を抜き出し、次の表を返しました。

| 作業 | 担当 | 期限 |
| --- | --- | --- |
| 原稿案を出す | 制作担当 | 11月20日 |
| 印刷の見積もりを取る | 購買担当 | 未定 |
| 配布部数を決める | 未定 | 次回（期限は未定） |

元のメモでは、次回の打ち合わせ日は11月24日ですが、見積もりの期限は決まっていません。表の該当セルを元のメモと見比べ、日付が混ざっていないことを確認しました。実演は架空例1回です。時短率や運用品質を計測した結果はありません。

## 会社が認めたツールで、一つの作業を2週間

1. 定例会議のメモ整理など、繰り返す作業を一つ選びます。チームで使えるツールと入力してよい情報を先に確認し、顧客情報や機密を除いた例から試します。
2. 決定事項・作業・担当・期限をたどれる形にし、元のメモとの確認を担当者に割り当てます。分からない欄は「未定」のまま持ち帰ります。
3. 普段の方法とAIで下書きする方法で、それぞれ作成・確認・修正にかかった時間と修正箇所を記録します。効果があった手順を、確認時の注意と一緒にチームへ共有します。

導入の有無だけでは、職場で役立ったかは見えません。出力を確認する時間まで含めて、毎週の仕事で使い続ける価値があるか判断します。 [総務省・経済産業省 AI事業者ガイドライン](https://www.meti.go.jp/shingikai/mono_info_service/ai_shakai_jisso/20260331_report.html)
