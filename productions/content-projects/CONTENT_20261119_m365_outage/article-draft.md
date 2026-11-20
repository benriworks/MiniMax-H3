# Outlookの受信箱が開かなかった日

**2026年11月のMicrosoft 365障害を、メールの入口からたどる**

11月13日、日本では朝の受信箱が開かず、翌日の入試に関する連絡を電話に切り替えた大学もあった。Microsoftの暫定報告は原因を三つ挙げる。7月の更新に含まれていた不具合、Teamsの通信経路の変更、そして前日の別件によるサーバー容量の減少だ。三つが重なって、メールの入口が各地で応答できなくなった。 [Microsoft、11月15日付の暫定事後報告書（公開写し）](https://ismg-cdn.nyc3.cdn.digitaloceanspaces.com/asset_files/external/microsoft-report.pdf) ／ [明治薬科大学の入試に関する案内](https://www.my-pharm.ac.jp/news/detail/513/?target=candidates)

## 7月の更新が、なぜ11月に影響したのか

Outlookから受信箱を開くとき、Microsoft側のゲートウェイが接続を受け付け、その先のExchange Onlineへ要求を通す。7月の変更は、このゲートウェイ専用に用意したものだった。内部で複数の処理が同じ資源の解放を待つ「lock contention」（ロック競合）が、ある負荷の組み合わせで膨らみ、CPUやメモリが尽きた。通常の負荷試験は比較的コア数の少ない機種が中心だった。実際に競合が厳しくなったのは、新しい多コア機だった。 [Microsoft、11月15日付の暫定事後報告書（公開写し）](https://ismg-cdn.nyc3.cdn.digitaloceanspaces.com/asset_files/external/microsoft-report.pdf) ／ [MicrosoftのCharles Lamanna氏による説明](https://x.com/clamanna/status/2122209697226948729)

障害の約15時間前、Teamsの通信が、Exchangeも使うゲートウェイへ切り替わった。普段も行う操作だが、受け持つ通信の量と種類が変わる。その入口では前日の別件によりサーバー容量の約14％が使えなかった。容量の減少だけなら余裕はあったが、米国の利用が集中する時間帯に、この二つの条件が重なった。 [Microsoft、11月15日付の暫定事後報告書（公開写し）](https://ismg-cdn.nyc3.cdn.digitaloceanspaces.com/asset_files/external/microsoft-report.pdf) ／ [MicrosoftのCharles Lamanna氏による説明](https://x.com/clamanna/status/2122209697226948729)

<!-- figure:teams -->

<!-- page -->

## 逃がした通信が、次のサーバーも止めた

通信を引き受けるサーバーが応答しなくなると、通常は元気なサーバーへ振り向ける。今回は、振り向けた先にも同じ不具合があった。次のサーバーも詰まり、さらに少ない台数で同じ通信を分け合う。普段なら影響を区画内にとどめる仕切りも、別件のため連鎖を止められなかった。 [Microsoft、11月15日付の暫定事後報告書（公開写し）](https://ismg-cdn.nyc3.cdn.digitaloceanspaces.com/asset_files/external/microsoft-report.pdf) ／ [MicrosoftのCharles Lamanna氏による説明](https://x.com/clamanna/status/2122209697226948729)

報告書は、最悪時には “more than 80% of servers were unresponsive.” と記す。**8割超という値は対象ゲートウェイのサーバー台数についての数字**だ。Teamsは別系統に切り替えられ、障害中も大半の時間は会議やチャットが動いた。一方、Exchangeを使う予定表やメールボックスには影響が残った。 [Microsoft、11月15日付の暫定事後報告書（公開写し）](https://ismg-cdn.nyc3.cdn.digitaloceanspaces.com/asset_files/external/microsoft-report.pdf) ／ [Microsoftの障害通知（ペンシルベニア大学が掲載）](https://mailservices.isc.upenn.edu/computing/email/penno365/alerts/ms-incidents.html)

<!-- figure:cascade -->

## 入試、講義、金曜日の仕事

明治薬科大学は過去のメールも確認できず、翌14日の入試に関する緊急の問い合わせを電話で受け付けた。立命館大学のエクステンションセンターは、自動返信が確認できなくてもシステム上で予約が確認できれば有効と案内した。大阪医科薬科大学は、16日の大学院統合講義を視聴するURLをOutlookの復旧後に送ると告知した。受信箱を開けない時間には、締切前の用事が進んだかを確かめる手段まで失われた。 [明治薬科大学の入試に関する案内](https://www.my-pharm.ac.jp/news/detail/513/?target=candidates) ／ [立命館大学エクステンションセンターの案内](https://www.ritsumei.ac.jp/extension/news/detail/?id=32) ／ [大阪医科薬科大学の大学院統合講義の案内](https://www.ompu.ac.jp/news/cc9f84000002dv21.html)

パリで広報の仕事をするラヤンさんは、仕事の一部は月曜まで待つことになったと話した。一方、取引先も影響を受けたので “we were all in the same boat”（「みんな同じ境遇だった」、仮訳）とも語っている。仏紙が取材した一人の経験だ。 [Le Mondeがパリの広報担当者に聞いた当日の様子](https://www.lemonde.fr/en/economy/article/2026/11/14/microsoft-outage-shows-french-businesses-dependence-on-digital-tools-we-were-all-in-the-same-boat_6780424_19.html)

<!-- page -->

## つながり始めても、メールはまだ配送待ちだった

再起動したサーバーには、待っていた通信が一気に向かい、すぐにまた応答できなくなった。技術者は接続処理を以前の動作に戻す修正を作り、サーバー群をいったん稼働から外し、修正・再起動してから段階的に戻した。規模の大きいExchange Onlineは他のゲートウェイへ丸ごと移すことができず、受け皿を立て直す必要があった。 [Microsoft、11月15日付の暫定事後報告書（公開写し）](https://ismg-cdn.nyc3.cdn.digitaloceanspaces.com/asset_files/external/microsoft-report.pdf)

| 日本時間 | Microsoftの記録 |
| --- | --- |
| 11月13日 01:20 | Exchange Onlineへの影響を示す警報。暫定報告の開始時刻。 |
| 11月13日 16:20 | 一部の容量に、不具合を戻す修正を適用。 |
| 11月13日 20:00 | アジア太平洋の一部で復旧作業を完了。段階的に通信を戻した。 |
| 11月14日 01:10 | 利用者への進行中の影響が解消。監視・滞留メールの処理へ移行。 |
| 11月14日 13:15 | 安定を確認し、二つの障害IDへ最終の管理者通知。 |

報告書の開始から影響解消までは**23時間50分**。各利用者が受信箱を開けなかった長さには、地域・機能・接続手段による差がある。Microsoftは配送期限を延ばし、滞留したメールが処理されたことを確認した。また、容量の追加、通信の振り分けと接続処理の監視、障害の連鎖を防ぐ制限を実施済みと報告している。 [Microsoft、11月15日付の暫定事後報告書（公開写し）](https://ismg-cdn.nyc3.cdn.digitaloceanspaces.com/asset_files/external/microsoft-report.pdf) ／ [Microsoftの障害通知（ペンシルベニア大学が掲載）](https://mailservices.isc.upenn.edu/computing/email/penno365/alerts/ms-incidents.html)

## 公式発表を確かめるには

11月19日に本文を確認できたのは11月15日付の暫定版。管理者向けの対象IDは **EX1550543 / MO1550821**。関連する経過通知はペンシルベニア大学の掲載ページでも読める。公式に告知された版と、利用者に生じた影響をそれぞれの出典で確かめられる。 [Microsoft 365 Statusによる暫定報告の告知](https://x.com/MSFT365Status/status/2122205066157257160) ／ [Microsoftの障害通知（ペンシルベニア大学が掲載）](https://mailservices.isc.upenn.edu/computing/email/penno365/alerts/ms-incidents.html)
