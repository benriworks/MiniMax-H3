# 新規人物リアクション版v03の検査

2026-10-31。対象は動画v03と人物ポーズ6本。ユーザーは今回の生成・差し替えを依頼済みだが、完成動画の最終採用・公開は未実施。

| 対象 | 確認結果 |
| --- | --- |
| 本編 | 48秒、1080×1920、24fps、1152フレーム、H.264／AAC 48kHz stereo |
| 容量・SHA-256 | 5,171,867 bytes／`2521d1d5dcdba38dc50d8960493befcc280388211d9fb86c6bd48fd335b66780` |
| 媒体 | ffprobe照合と全編decode通過。v02とのAAC圧縮bitstream同一性を確認 |
| 新規生成 | 男性・女性それぞれ思考／喜び／納得の6本。ローカルMiniMax H3、公式INT8＋Q4、768×1376、20 steps、124フレーム／24fps |
| 生成証跡 | 成功history、graph、参照画像・モデル投入画像・MP4のhash、出力geometry、全編decodeを6件保存 |
| AI補助確認 | 各素材のcontact sheetとフルサイズの動作フレーム。本編13フレームと24.0秒／46.6秒の指先・表情を確認 |
| 修正 | 男性納得の原本に意図しない衣装文字。原本は保持し、416×530の寄りを派生して本編・記事用画像に使用。切り出し以外の描き換えなし |
| 音声 | 追加TTS 0。声とBGMはv02からAACのstream copy。人物の生成音は使用しない |
| ポーズ一覧 | 15秒・無音。6本を思考／喜び／納得の順に男女で並べ、全編decode確認。2,210,901 bytes |
| Drive | 本編とポーズ一覧の名前・MIME・容量・所有者権限をreadback照合。共有URL・IDはignoredの受領記録に保存 |
| 記事 | 本文・公式引用はv02を維持。新規ポーズから静止画6枚と原本・派生のmanifestを収集。blog配置・公開は未実施 |

新規6本は元の同じ2本のループの付け替えではなく、別seed／prompt／実行IDによる新規H3出力。男性の納得だけは、顔とうなずき・指先を残す寄りの派生を使用する。人物動画の生成要求は6回、再生成0、外部MiniMax API要求0。実行時間の合計は9,504.684秒で、このPC・設定・6件に限った実測。

技術検査・AI補助によるフレーム確認、人の最終試聴、実スマホ再生、ユーザー採用、YouTube・記事公開を分ける。後4項目は未確認または未実施。検査したフレームから全瞬間の意味・品質を機械保証したとはしない。

根拠：出力 `release/v03/verification.json`、`motion-provenance.json`、`qc/`、`drive-upload.json`、`motions/v01/*/verification.json` と `visual-review.json`。男性の寄りは同フォルダーの `public-derivative.json`。記事の追加素材は `blog-handoff/motion-assets-v01/manifest.json`。
