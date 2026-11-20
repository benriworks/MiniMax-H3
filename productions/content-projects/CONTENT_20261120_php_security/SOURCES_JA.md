# 出典・事実照合と撮影範囲

2026年11月20日、日本時間に確認。ショートv01、フルv01・v02、記事v01で共用する。

| 根拠 | 対象と使い方 |
| --- | --- |
| [PHPの10月21日告知](https://www.php.net/archive/2026.php#2026-10-21-5) | 前回の2件。Webリクエストを処理するPHP全般に更新を呼びかけ。2件とも認証なしの遠隔コード実行につながる可能性。実際の危険度は構成で変わる。旧版の撮影を流用せず撮り直した |
| [10月23日の追加案内](https://www.php.net/archive/2026.php#2026-10-23-1) と [11月19日の正式告知](https://github.com/php/php-src/security/advisories/GHSA-658j-r8rw-q6mx) | 前回動画の末尾にあるCVE-2026-115560が今回の定期修正に入ったことを追跡 |
| [PHPの11月18日予告](https://www.php.net/archive/2026.php#2026-11-18-1) | 4週の通常周期。標準外の設定か珍しい構成が必要との説明はCritical評価の問題に限る |
| [11月19日の正式リリース](https://www.php.net/archive/2026.php#2026-11-19-4) と [8.5.13変更履歴](https://www.php.net/ChangeLog-8.php#8.5.13) | 当日の4系列の更新は8.2.36、8.3.37、8.4.28、8.5.13。8.6.0一般公開は同日だが別の系列 |
| [php-src告知](https://github.com/php/php-src/security/advisories)・[公式API](https://api.github.com/repos/php/php-src/security-advisories) | UTC公表日2026-11-19で抽出しCVEが一意な17件。Critical 7・High 4・Medium 6。公開日、ID、深刻度、告知URLを保存。8.5.13変更履歴にはuriparserのCVE-2026-48841も記載される |
| [CVE-2026-126714](https://github.com/php/php-src/security/advisories/GHSA-fm2m-fjf5-v3cp) と [PHPマニュアル](https://www.php.net/manual/ja/session.examples.basic.php) | セッションの中断された保存処理を生活例につなぐ。買い物かごは仕組みの説明、実在店舗での発生や侵害を主張しない |
| [IPA事前案内](https://www.ipa.go.jp/security/security-alert/2026/pre-alert20261119.html) | 事前案内時点。公開後の修正版・11月20日時点の悪用有無の根拠にはしない |
| [Ubuntuの10月向け告知](https://ubuntu.com/security/notices/USN-8948-1) | OSパッケージの完全な番号と公式PHP番号は異なる例。今回の特定ベンダーの適用済み状況は主張しない |
| [甘茶の音楽工房](https://amachamusic.chagasi.com/music_happytime.html)・[利用条件](https://amachamusic.chagasi.com/terms.html) | ローカル曲「ハッピータイム」。Content ID登録なし |

## 配布元を実名で紹介する改訂（2026年11月21日）

| 発信元 | 本編に使った根拠 |
| --- | --- |
| [Red HatのPHP告知 RHSB-2026-020](https://access.redhat.com/security/vulnerabilities/RHSB-2026-020) | 「Affected Products」が製品ごとの確認先。要約は、取り上げた7件のうち2件をRHELでRed Hatが配るPHPの対象外としている。Red Hat側の評価とPHP開発元による深刻度集計は別々に示す。 |
| [Red Hatのバックポート方針](https://access.redhat.com/security/updates/backporting) | 以前の版に修正を取り込む方針。確認対象は使用している配布元のリリース番号まで。 |
| [Red Hatの公式写真「The hat」](https://www.redhat.com/en/about/brand/standards/the-hat) | Red Hat Summit会場に下がる実物のフェドーラ帽で、社名と次に見る告知を結び付ける。会場の写真は全体を保ち、著作者名・掲載ページ・被写体を表示。映像・記事内で解説するための引用。画像配信元は[Red Hatの原写真](https://www.redhat.com/rhdc/managed-files/Brand_standards-Red_Hat-The_hat-The_hat_today-2.jpg)。 |
| [Remiの11月19日付更新記事](https://blog.remirepo.net/post/2026/11/19/PHP-version-8.2.36-8.3.37-8.4.28-8.5.13) | Enterprise Linux向けを含め、4系列のRPMを配布。Remiから入れた8.4系の公表版は8.4.28。利用者の環境にいつ適用されたかは管理先が確認する。 |

Chromeが表示した原文から抜粋した3点と、Red Hatが配信するJPEG写真1点を新規保存。各原画面の大きさは3100×2040、写真原本は833×449。取得ページ、写真URL、範囲、取得時刻、入力と公開候補のハッシュは案件出力の `captures/providers-v01/manifest.json` と[改訂版の検査記録](youtube/verification-v02.json)に収録した。

## 画面と引用

この回の実画面は公式告知を読むローカルChrome。攻撃や更新後の実サイトの状態を撮影題材としない。PlaywrightでPHP公式3箇所とIPA1箇所を開き、実DOMの位置と3000×1900の原本から短い抜粋を取得した。引用・要約・予約サイトの運用例を異なる面で示す。`captures/manifest.json`にURL、原本・切り出しの寸法、座標、bytes、SHA-256、取得時刻。Gitに置くメタデータは[出典台帳](sources.json)と[検査記録](verification-v01.json)にまとめる。
