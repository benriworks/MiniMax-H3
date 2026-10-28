# 出典と主張の対応

確認日：2026-10-24。公表日と確認日を分ける。発表元・国内注意喚起を優先した。最終公開時に更新があれば差分を再確認する。

| 出典 | 公表日 | 動画への反映 |
| --- | --- | --- |
| [PHP公式：重大なRCEの告知](https://www.php.net/archive/2026.php#2026-10-21-5) | 10/21 | 2件のRCE、修正済み8.2.35 / 8.3.36 / 8.4.27 / 8.5.12。利用構成で影響が変わり、修正適用を確認する |
| [PHP公式：Session upload progressの追加告知](https://www.php.net/archive/2026.php#2026-10-23-1) | 10/23 | 特殊な設定と実行時の設定切り替えを伴う別の条件。追加告知も確認するという結論 |
| [PHP開発元：CVE-2026-109618](https://github.com/php/php-src/security/advisories/GHSA-w8hw-w9fx-j79w) | 10/21 | メモリ不足の途中状態の扱い。CVSS v4.0 9.2。動画では内部実装と攻撃手順を省略 |
| [PHP開発元：CVE-2026-109619](https://github.com/php/php-src/security/advisories/GHSA-6wmf-4rv5-p3rp) | 10/21 | リクエスト終了後に残った内部状態の扱い。構成や処理経路に依存 |
| [IPAの注意喚起](https://www.ipa.go.jp/security/security-alert/2026/alert20261022.html) | 10/22 | 国内向けの確認先。PHP公式の公表は10/21と区別 |
| [JPCERT/CCの注意喚起](https://www.jpcert.or.jp/at/2026/at260033.html) | 10/22 | 更新前にテスト。OS・製品提供元の情報も確認。侵害有無の調査。痕跡がないだけでは被害なしと断定できない |
| [AWSの観測報告](https://aws.amazon.com/blogs/security/amazon-threat-intelligence-identifies-php2shell-exploitation-prior-to-public-disclosure-in-madpot/) | 調査台帳参照 | 背景調査。ハニーポットでの試行と、実環境での成功を混同しない。短尺には詰め込まない |

画面に示す4つの数字は**10月21日公開の2件に対する修正版の基準**で、10月24日時点の全課題が解消したことを意味しない。OSやサービス側のバックポートもあるので、表示番号だけで未対策と断定しない。10月23日の関連CVE-2026-115560と最初の2件は別に扱う。

録画や画像は安全性の実証ではない。攻撃を試していない。実サイト・社内環境・サーバー設定は変更していない。非公開原本を記事やGitHubへ自動転用しない。

## v03追加調査（2026-10-25確認）

| 出典 | 動画へ反映する事実 |
| --- | --- |
| [W3Techs：サーバー所在地別PHP利用率](https://w3techs.com/technologies/breakdown/pl-php/server_location) | 画面に示されたデータ日2026-10-24、Japan 92.4%。サーバーが日本にあり、サーバー側言語が判別可能な調査対象サイトという分母を表示・音声へ残す |
| [W3Techs調査方法](https://w3techs.com/technologies) | 有効な内容・機能のあるサイトを対象とする。日本の全サイトや利用者を数えたものではない |
| [WordPress公式要件](https://wordpress.org/about/requirements/) | WordPressはPHPを使用する。一般的な要件にある8.3を今回の修正済み番号として案内しない |
| [PHP公式入門](https://www.php.net/manual/ja/introduction.php) | コードはサーバー側で実行し、結果をクライアントに返す。フォーム・動的ページなどへ使える |

92.4%は普及の指標で、PHP2Shellの影響率・被害率ではない。WordPress等を利用する視聴者に利用環境の確認を促すために使う。すべてのインタラクティブなサイトがPHPで動くとは述べない。
