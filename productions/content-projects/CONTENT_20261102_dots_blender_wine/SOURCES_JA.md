# 出典・素材と検証範囲

確認日：2026-11-02。

## 提供素材

対象はDriveの「dots制作履歴 第3弾 ワイン（Blender素材）」：https://drive.google.com/drive/folders/1GIfitY8aaIZ2ICafVlQ9ep8zm3wlY_ZY 。最初に指定された別フォルダーは除草作業・列車接触の素材だったため、無関係な原本は取得せず、名前検索とREADMEで題材を照合した。

完成物4ファイル、工程1ファイル、履歴7ファイルの計12ファイル。動画4、PNG5、ZIP3。ローカルの `outputs/content-projects/CONTENT_20261102_dots_blender_wine/source-inventory.json` に容量・SHA-256・動画probeと展開64ファイルのhashを保存。提供スクリプトは読み取りのみ、元blendは開かず、ローカルの別の未保存シーンは変更しない。

- `final/wine_pour_750ml_v3_5s.mp4`：960×540、24fps、5秒、無音。v3完成CG。
- `final/wine_bottle_size_v2_v3_comparison.png`：1920×642、同じカメラ・フレームの比較。
- `process/wine_actual_process_milestones_20s.mp4`：960×720、20秒の工程静止画スライド。連続操作ではない。
- 履歴ZIPの `capture_log.jsonl` と `captures/01_table.png`〜`05_final_geometry.png`：実画面1366×1024。公開用は下部を除く1366×925。準備コンソール00は非公開。
- 初版→v2：瓶を起こして保持してから退避。初版冒頭77フレームを再利用し、後半43フレームを描画した記録がある。
- v2→v3：瓶とラベルを一様に1.9097797507倍。回転・液体の動きを保持し、停止後の高さとカメラを調整。保存されたQAログの読取であり、今回の独立した3D再検証ではない。
- 源流の実行環境はBlender4.3.2・Cycles CPU。現PCは5.1.2の別シーンで追加撮影経路は未確認。現在のPCで制作したと偽らない。

## 公式根拠

| 出典 | 使用する根拠 | 限界 |
| --- | --- | --- |
| https://learn.chatgpt.com/docs/dots/computers-and-apps | dotsのコンピューターとアプリ、操作権の受渡しの前提 | 全アカウントで同じBlender環境を保証しない |
| https://www.saverglass.com/en/our-products/catalog-still-wine/ancienne-75-cl-plate-unique | 参考瓶の高さ299mm | 普遍的寸法でもモデル内部容量の証拠でもない |
| https://www.zwiesel-glas.com/en/shop/wine-glasses/red-wine-glasses/burgundy-red-wine-goblet-classico | 参考グラスの高さ230mm | 特定商品の精密再現とはしない |

公式ページの撮影原本は `_private/captures/official-computers-original.png`、見出し切り出しは `assets/official-dots-heading.png`。英語引用は7語。引用の目的はクラウドPCの説明で、メーカーの商品写真は転載せず提供CGを使用する。出典を動画・記事に明示する。

## 断定しないこと

流体物理の成功、厳密な750ml容量、実写品質、完全無人、全体の所要時間、元の依頼会話、撮影されていない連続操作。960×540原本をフルHDで合成しても新たな細部が増えたとはしない。
