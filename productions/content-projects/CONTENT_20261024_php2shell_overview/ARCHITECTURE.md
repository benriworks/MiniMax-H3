# PHP2Shellショート制作の構成

共通ContentWorkspaceが調査、提案、返答、採用、撮影可否、出典、人物版、絵コンテの正本。`production.py` は案件用の薄いドライバーで、過去の完成品を書き換えない。

## 入出力

1. PHP・IPA・JPCERT/CC等の一次資料を調査台帳へ記録。PCで公式画面を実際に開きPNG保存。
2. 明示的に採用された三浦航v01画像と人物設定を固定。画像と採用受領をhashで結ぶ。
3. 専用ComfyUIサービスでMiniMax H3 I2VA。リソース・queue・prompt_idを検査。過去案件の `generate.py` を読み込み、出力と入力ディレクトリを案件内へ差し替える。専用ポート以外に接続しない。
4. 採用した構成を9カットの `creator-story.json` にする。Aoedeは既存の共有ロックと22秒の送信間隔で生成。未知の送信結果を自動再送しない。
5. 公式の見出しを原本から画素を変えず切り出す。原本・矩形・hash・URL・日時・AI確認範囲をproofに記録。
6. `tools/studio/shorts_creator.py` が原稿一致と音声サンプル数を検証し、実発話時間から50秒へ配置。生成動画は全decodeとフレーム確認を終えてからbindする。元動画より長い静止延長・ループをしない。
7. `studio/creator-render.mjs` と共通Remotion部品で1080×1920、24fps、H.264描画。`finish` でAAC音声、発話中のBGM低減、音量・全decode・携帯幅プレビューを検査。
8. 完成候補をDriveへアップロードしmetadata read-back。人の試聴と採用、YouTube公開は別記録。

## 保存境界

- `productions/content-projects/CONTENT_20261024_php2shell_overview/`：調査・台本・ドライバー・設計・検証要約。
- `outputs/content-projects/CONTENT_20261024_php2shell_overview/`：人物原画、MiniMax原動画、Aoede原音声、原本・改訂・共有受領。
- `outputs/productions/SHORT_20261024_php2shell_overview/`：レンダー入力、引用派生、版付きMP4・レビュー・納品。
- SQLite：採用対象版と依存関係。レンダー記録とhashで同一性を確認。
- GitHub：公開可能なコードと制作ノウハウ。動画・音声・ZIP・鍵・個人情報・署名URLは保管しない。

## 検証境界

公式情報の確認、ローカル生成成功、AIによる見た目の確認、人の試聴、採用、公開は別状態。実サイトの影響判定や攻撃成功を主張しない。検証の進捗は `VERIFICATION_JA.md` を参照する。

## v03：国内との関係とWeb処理の図解

`revision-v03.py` がv02を保持したまま12カット・60秒候補を作る。改訂した冒頭4場面のAoedeだけを生成し、後半8場面はv01の完了proofとPCMを照合して再利用する。人物の参照画像とMiniMax動画も同じ採用版。新しい音声manifestとrender-stateはv03の別パスに置く。

`record-v03.py` はユーザーの修正依頼、W3Techs・調査方法・WordPress・PHP入門の一次資料、分母を明記した主張、追加撮影の原本、依存する絵コンテを共通ContentWorkspaceへ記録する。初回の採用を改訂後動画への採用に置き換えない。

共通 `WebRuntimeDiagram.tsx` は、利用者・ブラウザーをサーバーの外に、WordPress等の例とPHPをサーバーの中に描く。`web-services` は関係、`web-flow` はアクセス・処理・応答を段階的に示す。ネットワーク通信や実サービスへの入力を行わない。`FeatureDiagram` から選択し、Python/TypeScriptの同じ閉じたgraphic列挙で検証する。`creator-render.mjs` は新部品もhash付き入力に含める。

92.4%の表示は、W3Techsでサーバー所在地が日本かつサーバー側言語が判別可能なサイトという集計。利用者のサイトが脆弱だという実測結果ではない。調査日・取得日・動画の最終確認日を分ける。
