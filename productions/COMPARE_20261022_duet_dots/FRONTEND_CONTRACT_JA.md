# 比較動画の描画契約

入力型の正本は `studio/src/remotion/comparisonMotion.ts`。登録は `comparisonEntry.tsx`、composition IDは `ProductComparison`。

- 全体：`title`, `durationInFrames`（1440〜2160）, `scenes`（8〜24）, `captions`, `mode`（fixture / production）, 任意 `showGuides`。任意 `presenterTreatment` は `card / immersive`。未指定は既存card表示を保ち、immersiveは人物の3場面だけ縦画面全面へ映す。
- 各scene共通：`id`, `from`, `duration`（24〜192）, `eyebrow`, `headline`。見出しは10表示単位×2行以内。任意 `source_ids` は根拠追跡用。
- `kind: comparison`：`layout`（fictional_case / signal / workspace / availability / decision）、`panels`（1〜2）。各panelは `label`, 任意 `detail`, `icon`, `tone`, `state`。workspaceの手元PC接続を描く場合だけ `connection: local`。閉じるノートPCは `icon: laptop, motion: close`。それ以外のPCは開いたまま。
- `kind: source`：`capture: {origin: official, image: capture-XX.png, title, source_url}` と任意 `points`（2行まで）。比較用だけMeet dotsの正確なルートURLを追加許可。公式PNGは色・文言を変えずcontain表示する。
- `kind: presenter`：`role`（opening / insight / closing）, `points`（1〜2）, 任意 `note`。実MP4は `media: media-XX.mp4`, `mediaStart`, `mediaDurationInFrames`, 任意 `mediaPlayFrames`。すべて24fps換算のフレーム数。区間が実素材を超えると拒否し、再生区間がsceneより短い場合は自作まとめへ切り替える。
- 画像／人物が未取得のfixtureは明示的 `fixtureLabel` が必要。productionでは欠落素材を拒否する。fixtureは内部確認表示を常に持ち、公開成果物にはしない。
- 字幕：`{start,end,text}` の配列。範囲内、重なりなし、12表示単位×2行。`caption-phrases.json` の短句は元台本のナレーションと連結一致を確認済み。実音声に基づく時刻は制作側で確定する。

静的文字は54px以上、字幕62px、重要文字領域x60〜912/y198〜1490。主な図・出典は1230pxまで、字幕の上端は1300px。フォント準備後に各frameの実文字矩形を検査する。

immersive人物場面は顔を避けた下側へ見出しと要点を置き、上下の暗いグラデーションで可読性を確保する。素材区間の最後6frameで紙色の背景が下から上がり、最後3frameからまとめ文字を段階表示する。実動画の区間終了後は動画を停止延長せずまとめだけを表示する。この処理でも字幕時刻・人物の非重複区間・全尺は変更しない。

`render-fixtures.mjs` は内部確認用でAPI/TTSを呼ばない。`verify-motion-fixture.mjs` の合成カラーパターンMP4は再生と切替だけの検査入力で、MiniMax人物動画の代用ではない。

production外側の必須事項：画像の原本・crop・URL・日時・SHA-256をproofに結合し、実MP4の生成証跡・hash・decode・目視合格・実尺を照合する。Frontendの型・URL・区間検査だけでは公開に足りない。実素材の全カット目視、Aoedeの実尺・同期・試聴と、S3/配布の検査は別工程。
