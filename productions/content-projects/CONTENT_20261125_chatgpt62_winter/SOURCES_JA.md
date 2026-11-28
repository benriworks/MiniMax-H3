# 出典と実演条件

2026-11-25 JSTに照合。発表日はOpenAIの掲載日。「Chat」は通常のチャットタブ、「Work」「Codex」は先行してAstraとSolが導入された作業環境。

| 資料・原本 | この動画で使った箇所 |
| --- | --- |
| [OpenAI「ChatGPT release notes」2026-11-23](https://help.openai.com/en/articles/6825453-chatgpt-release-notes) | “GPT-6.2, now in the chat tab”。日常会話向けに調整したSol、段階的な提供、Plus・Pro・Business・Enterprise、Enterpriseの管理者設定。Chatでの画像理解スコア47.4%→71.7%、難しいプロンプトで指示に沿った回答の割合62.5%→78.1%。いずれも順序はGPT-6→GPT-6.2。 |
| [OpenAI「Introducing GPT-6.2 Astra and Sol」2026-11-17](https://openai.com/index/introducing-gpt-6-2-astra-sol/) | 11月17日のWork・Codex・APIでの発表。今回のChatへの提供と時系列で比較。 |
| [OpenAI Deployment Safety「GPT-6.2 in ChatGPT System Card」](https://deploymentsafety.openai.com/gpt-6-2-chatgpt/safety-overview) | チャット版の発表日と位置づけの照合。動画の提供対象は、対象プランと管理者条件を列挙するリリースノートに従った。 |
| [公式画像理解の原図](https://images.ctfassets.net/j22is2dtoxu1/2g5e4AHl1DqnWvRNUV9Qsn/ec06f34ee8db26f048a32770062d87cf/Image_understanding__1_.png?fm=webp&q=80&w=1344) ／ [公式指示追従の原図](https://images.ctfassets.net/j22is2dtoxu1/6gui9wlnzRcYKTi7TQfE0W/b112db8f57c159c93389c335fd94331c/following-complex-instructions.png?fm=webp&q=80&w=1344) | 公式発表のグラフ2枚を確認・撮影し、リンク先の1344px版を動画の原図に使用。画面に出典を併記。 |

## 実画面

Windowsのログイン済みChromeでホーム→Chat→入力欄のモード名→モデルを選択→GPT-6.2。「6.2 Instant」を確認して一時チャットへ移動。料金表は実演用に自作した画像。チャットにこの1枚を添付し、動画内の2問を順に送信。一問目の選択、計算と回答形式、二問目の回答を撮影した。

1. 「画像の料金表だけを使ってください。1人で2泊、朝食は2回。合計22,000円以内、駅から徒歩15分以内ならどちらの宿？ 両方の合計と、選んだ理由を3行で。」
2. 「ほかの条件は同じで、駅から徒歩5分以内にしたら？ 一文で答えてください。」

駅前館は23,600円、雪灯り館は22,000円。15分以内なら雪灯り館、5分以内では該当なし。一つの画像と会話で観察した結果。割合の比較はOpenAI側の評価値。

`captures/original/` はPC画面原本、`captures/figures/` は公開用の切り出し、`captures/official/` は公式グラフ原図。保存座標と画像hashは `captures/figures/manifest.json`。一時チャットでもサイドバーやブラウザ上部の履歴は別に表示されるため、入力・回答・選択肢以外の領域を除外した。撮影した英語の公式ページで日付と2つの原図を確認。日本語ページには確認時に当該項目が見つからなかった。
