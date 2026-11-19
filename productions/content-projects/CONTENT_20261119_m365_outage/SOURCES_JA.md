# 2026年11月のMicrosoft 365障害の出典

11月19日（日本時間）に確認。対象は EX1550543 と MO1550821。暫定事後報告は11月15日付で、Microsoft 365 Statusによる案内は16日。報告書の執筆者はMicrosoft、一般に開けるPDFのホストは第三者。管理センターの契約者向け画面はサインインが必要。公開写しを読み、サービス正常性通知・担当役員の説明の報道とも整合を確認した。最終報告を確認したとは扱わない。

| 資料 | 本編・記事で使った範囲 |
| --- | --- |
| [Microsoft、11月15日付の暫定事後報告書（公開写し）](https://ismg-cdn.nyc3.cdn.digitaloceanspaces.com/asset_files/external/microsoft-report.pdf) | 2ページの影響範囲とUTC開始・終了。3～4ページの三要因、隔離と再起動、7ページの実施済み措置。 |
| [Microsoft 365 Statusによる暫定報告の告知](https://x.com/MSFT365Status/status/2122205066157257160) | 管理者向けの暫定報告の公表と障害ID。X原投稿への参照と、原投稿を埋め込んだ[窓の杜の記事](https://forest.watch.impress.co.jp/docs/news/2156753.html)で確認。 |
| [MicrosoftのCharles Lamanna氏による説明](https://x.com/clamanna/status/2122209697226948729) | 三要因、ラボと本番の違い、80％の分母。Xの直接取得は403。[IT Proが収録した役員の発言](https://www.itpro.com/software/microsoft/microsoft-365-outage-company-exec-lifts-lid-on-the-cascading-failure-that-caused-lengthy-disruption)と報告本文を突合。 |
| [Microsoftの障害通知（ペンシルベニア大学が掲載）](https://mailservices.isc.upenn.edu/computing/email/penno365/alerts/ms-incidents.html) | 大学が掲載しているMicrosoft発の稼働中の経過通知。該当IDで検索。接続不能、予定表、配送待ちの監視。更新されるページなので、後日には対象項目が一覧から外れ得る。 |
| [明治薬科大学の入試に関する案内](https://www.my-pharm.ac.jp/news/detail/513/?target=candidates) | 本学メールの送受信・履歴確認と11月14日の入試窓口。11月16日の復旧案内に、当初の告知を併載。 |
| [立命館大学エクステンションセンターの案内](https://www.ritsumei.ac.jp/extension/news/detail/?id=32) | 申し込み自動返信の確認ができないこと、予約がシステムで確認できる場合の扱い。 |
| [大阪医科薬科大学の大学院統合講義の案内](https://www.ompu.ac.jp/news/cc9f84000002dv21.html) | 大学院講義のURLはOutlook復旧後に送ると案内。記事の日本の事例に使用。 |
| [Le Mondeがパリの広報担当者に聞いた当日の様子](https://www.lemonde.fr/en/economy/article/2026/11/14/microsoft-outage-shows-french-businesses-dependence-on-digital-tools-we-were-all-in-the-same-boat_6780424_19.html) | 仏紙自身が取材したパリの広報担当者Rayan氏の発言。英語版の姓名表記は名のみ。取引先も影響、仕事の一部を月曜へ。英語版の短い抜粋と自訳を明記。 |

## 引用と単位

### フルv03・ショートv01で追加した公式画面

- 11月17日の発言はMicrosoft自身が公開した講演録1ページの “we have work to do” と日付を短く切り出した。講演の会場ページもChromeで撮影した。原因の三要因は11月15日付の暫定報告に帰属する。[基調講演の公式PDF](https://news.microsoft.com/events/wp-content/uploads/2026/11/Nadella_TRANSCRIPT_Ignite-Keynote_Nov-2026.pdf) ／ [Microsoft Ignite 2026公式ページ](https://news.microsoft.com/events/ignite/2026/)
- 11月19日に撮影した正常性ページは、確認日現在の表示として日付を付けた。Microsoft Learnにある管理者向けの入口も照合した。[Microsoftサービス状態](https://status.cloud.microsoft/) ／ [Microsoft Learnの手順](https://learn.microsoft.com/ja-jp/microsoft-365/enterprise/view-service-health?view=o365-worldwide)
- 11月13日の案内と16日の更新が同居する大学ページは、大学名と見出しを撮影し直し、13日の電話連絡の一文へ切り替えた。[明治薬科大学の案内](https://www.my-pharm.ac.jp/news/detail/513/?target=candidates)

### 暫定報告と当事者の説明

- 報告書原文は「lock contention」「more than 80% of servers were unresponsive.」「immediately overwhelmed by waiting traffic」の範囲。二つの行にまたがる箇所は、語順を保ち改行だけを詰めて表示。各引用に日本語の意味とページを添えた。
- 約14％の分母は前日に利用できなくなった当該ゲートウェイの処理容量。8割超は最悪時に応答できなかった当該ゲートウェイのサーバー台数の割合。報告人数・全Windows機・全サービス台数の数値に変換しない。
- 12日16:20 UTC～13日16:10 UTCが公式の影響区間。日本時間はそれぞれ13日01:20、14日01:10。最終の管理者通知は14日04:15 UTC＝14日13:15 JST。告知の遅れを障害時間に加算しない。
- 管理画面で過去の障害を再現する操作は行っていない。公開ステータスの現在表示、大学の公開告知をWindows上の実ブラウザーで開いた。二大学の本文と記事用の大阪医科薬科大学の案内を、元画面から短く切り出した。報告書は文書の文字範囲を直接画像化した。緊急窓口の電話番号等は含めない。
