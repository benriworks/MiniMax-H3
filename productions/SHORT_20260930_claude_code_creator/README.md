# Claude Code紹介 — 演出付きショート

2026-09-30の演出・品質改修サンプル。主題は前作と同じ「Claude Codeで何ができるか」。キャラクター原本を再利用し、台本、場面割、文字、音楽、効果音を共通制作機能で作り直す。

## 制作

[creator-story.json](creator-story.json)を`python -m tools.studio.shorts_creator make --story <path>`へ渡す。案件ごとのTSX／音声合成コードは不要。詳しい手順は[演出機能の説明](../../SHORTS_CREATOR_JA.md)。

10場面、1080×1920、24fps、30秒。ナレーションはMicrosoft Sayaka・速度1。「Claude Code」は「クロードコード」。画面内の生成ツール名表示は入れない。

## 最新版：注釈除去と女性キャラクター調整（2026-09-30）

利用者の指定により、共通描画部品から「図解イメージ」の注釈を削除。女性キャラの肩幅・袖・胴回り・座り姿勢を調整した新しい元絵からH3動画を作り、最後の場面を差し替えた。顔・髪型とアイボリー／水色の服装を引き継いでいる。

- [修正版の30秒MP4](../../outputs/productions/SHORT_20260930_claude_code_creator/20260930T045206790884Z/shorts-creator.mp4)
- [修正版の一式ZIP](../../outputs/productions/SHORT_20260930_claude_code_creator/20260930T045206790884Z/shorts-creator-review.zip)
- [前版と比較できる再生ページ](../../outputs/productions/SHORT_20260930_claude_code_creator/20260930T045206790884Z/index.html)
- [女性キャラクター素材の比較](../../outputs/characters/programmer-duo-20260930/index.html)
- [修正版の検証記録](../../outputs/productions/SHORT_20260930_claude_code_creator/20260930T045206790884Z/verification.json)

前版の音声を`--reuse-audio`で再利用し、AAC packetの完全一致を確認した。30.000秒・720frames・1080×1920・24fps、-15.97 LUFS、true peak -1.50 dBFS。全decode・全720framesの文字領域検査・場面一覧と360px幅の目視・ZIPの読戻しに合格。先頭の男性と「最後は自分で確認」の図解は比較した静止画の全pixelが前版と一致する。注釈を消した7場面は注釈領域のみの差分（1画素・1/255階調の描画丸め差を除く）。今回の表現の最終採否は利用者確認用。

再実行例：

```powershell
.\.venv\Scripts\python.exe -m tools.studio.shorts_creator make --story productions/SHORT_20260930_claude_code_creator/creator-story.json --reuse-audio outputs/productions/SHORT_20260930_claude_code_creator/20260929T190107153171Z
```

## 内容の出典と範囲

日本語での依頼、ファイル編集、エラー修正、テストの流れは[Claude Code公式ドキュメント](https://code.claude.com/docs/en/overview)を参照した前作の出典を引き継ぐ。中盤は説明用の図解で、実操作の収録・所要時間の実測ではない。最終確認は利用者が行う構成。旧版と同等の再生数・視聴維持率を保証するものではない。

## 確認記録

出力先の`verification.json`に形式・全デコード・音量、`render.json`にソースと原本のhash、`timings.json`に発話と字幕時刻を保存する。技術検証と利用者の採否を分ける。

初回改修時の検証済み候補（前版として保持）：

- [比較・再生ページ](../../outputs/productions/SHORT_20260930_claude_code_creator/20260929T190107153171Z/index.html)
- [30秒MP4](../../outputs/productions/SHORT_20260930_claude_code_creator/20260929T190107153171Z/shorts-creator.mp4)
- [動画・カバー・台本・字幕・検証記録のZIP](../../outputs/productions/SHORT_20260930_claude_code_creator/20260929T190107153171Z/shorts-creator-review.zip)
- [詳細な検証記録](../../outputs/productions/SHORT_20260930_claude_code_creator/20260929T190107153171Z/verification.json)

30.000秒・720frames、H.264／AAC stereo 48kHz。実測音量は-15.97 LUFS、true peak -1.50 dBFS。重要文字の実DOM領域は描画中の全720framesで検査。全場面の完成映像コンタクトシートと360px幅の比較・チェックリスト・終幕を確認し、図解と字幕の重なりを解消した。全デコード、素材・ソースhash、ZIP内のCRCと個別hashの読戻しも合格。

状態は`verified_candidate_awaiting_user_review`、`user_approved: false`。聴感と表現の採否は利用者確認用。以前の作品と最初の試作は保持し、今回の候補は独立フォルダーに保存している。
