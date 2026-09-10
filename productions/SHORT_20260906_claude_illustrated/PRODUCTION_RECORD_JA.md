# Claude Desktop：イラスト入り外観の試作

## 目的とカット割り

ロゴや既存マスコットを使わず、暖かい橙色・生成り・独自イラストでClaudeを題材にした独立解説の雰囲気を作る。21秒、縦1080×1920、24fps、BGMなし。Desktopの通常チャットをCode操作とは呼ばない。

| 尺 | 映像 | 見出し | ナレーション（前版と同じ） |
| --- | --- | --- | --- |
| 0–7秒 | 独自の手描き風イラスト＋目的／日付／文字数の順次表示 | Claude Desktop／条件を添えて、３案 | 条件を添えて、三案まとめて依頼。 |
| 7–14秒 | 既存の実Claudeウィンドウ全体。回答3の表示区間 | ３つの候補から／使う表現を選ぶ | 候補が出たら、使う表現を選びます。 |
| 14–21秒 | 橙色背景＋日付／文字数の2カード | 仕上げるのは／あなたの判断 | 最後は、日付と文字数を確認。 |

カット1は「コンセプトイラスト」、カット3は「編集図解」と明示し、実UIと混同させない。最後の9月20日・40字以内は架空デモで依頼した条件。検証済みマークは付けず、確認を促す。カット2は極端な文字帯への拡大をやめ、周辺UIと入力欄を残す。追加の思考中素材・3案一覧・新規チャット・再収録はない。

## 制作経路と監査

- [画像生成プロンプトと素材来歴](ILLUSTRATION_PROMPT.md)。画像生成スキルにより独自のbitmap素材を生成した。
- `PanelComposition.tsx` / `render_panels.mjs` が2本の無音7秒・1920×1080素材を作る。Noto Sans JPを読み込み完了まで待ち、動きはフレーム番号だけから決める。乱数・外部URL・新規TTSは使わない。
- 出力panel、画像、renderer、依存ファイル、フォントの実bytesとSHA-256をmanifestに封印する。
- 専用`produce.py`は既存収録証跡を再照合してから、panelを通常Studio素材取り込みへ渡す。前版を上書きせず新recipeを作り、標準Quick Create→Detailed→ナレーションcache→Remotion→assembly→QC→Deliveryへ接続する。
- **汎用Studio UIに画像生成ボタンや新レイアウトを追加したわけではない。** 独自素材の準備のみ制作案件用スクリプト。最終動画・監査・納品は通常の制作経路を使う。
- 音質改善は保留中。聴感・教材としての有効性・公開品質は人による受入前であり、技術QCだけで合格にしない。

## 実行

```powershell
node productions/SHORT_20260906_claude_illustrated/render_panels.mjs
python productions/SHORT_20260906_claude_illustrated/produce.py render <出力manifest.json>
```

描画中はrendererやpackageのソースを変更しない。再実行は保存済みmanifestとcheckpointで同じ受付を照合する。

## 検証結果

- 新規ドライバーの隔離テスト15件成功。元入力・台本・声・音量・尺・hash・無音・同じ音声artifact・再試行書込みの境界を検証。別担当のread-onlyレビューでも実行を止める具体的不具合はなし。これは完成動画の視聴品質保証とは別。
- React確認スキルを適用し、動きのフレーム由来化、静的データとcomponentのトップレベル定義、既存のFontFace読み込み待ち／再利用を確認した。
- 初回panel素材`20260906T064728029Z`は採用せず保持。Remotion既定のJPEG frameがfull-range／BT.470BGになり、共通テンプレートへの再入力で指定RGB `(217,119,87)`が`(243,129,80)`へ変化した。初回終了時のブラウザcloseに非致命的ProtocolErrorも出たが、MP4の全decode・規定尺検証は成功していた。
- 採用素材`20260906T065122124Z`はPNG frame＋明示BT.709＋yuv420pへ変更。2本とも無音7秒／168frame、全decode成功。共通compositionのプレビューでRGB `(216,119,87)`となり、指定との差は最大1。色変更を元イラストへ焼き込まず、動画変換設定を直した。
- 最終描画用manifest: `outputs/studio/verification/claude-illustrated-20260906/panels/20260906T065122124Z/manifest.json`。直下`template-preview`の3枚で、イラスト／実ウィンドウ全体／橙色カードの違い、見出し・枠・非公式表記の分離を目視確認。後段字幕入りの完成MP4は別途検証する。

### 完成版

- Run: `run_a2df0ca5610949a397b125e5dd723da8`、top Job: `job_20325f156934442fabc2c05ecc7994d9`、recipe: `announcement_80190d37bd2ea49fb54782bedb903dd7` revision 1。旧recipeは上書きしていない。
- 通常制作・納品は2026-09-06 06:54:13–07:00:11 UTC、約358秒。これは画像生成・panelの準備・事前確認を除く所要時間。
- [字幕あり完成MP4](../../outputs/studio/runs/run_a2df0ca5610949a397b125e5dd723da8/assembly/A6646335E0301DB72D358281471B9E570450CE1A002A0A09403DB66F9B18D5BF/master-captioned.mp4): 2,376,538 bytes、SHA-256 `FCDDAA0F7C7F67A904900ACE030E4AB88EBAC72BC88F21326F4AD640FE574538`。
- [ナレーション字幕なしMP4](../../outputs/studio/runs/run_a2df0ca5610949a397b125e5dd723da8/assembly/A6646335E0301DB72D358281471B9E570450CE1A002A0A09403DB66F9B18D5BF/master-clean.mp4): 2,482,364 bytes、SHA-256 `533E1A4615ABF9F3401B75788B35F4F566B845A642591C74F962C687E94560AC`。見出し・図解は残る。
- 両方21.000秒、1080×1920、24fps、504frame、H.264＋AAC48kHz stereo。通常QC passに加え、独立したffprobeと全音映像decode成功。
- ナレーション工程は`cache_hit=true`、元のWAV・SRT・timings・manifestの4artifact IDを再利用。完成MP4のAAC payload SHA-256も前版と同じ`D528AF113075BD2646CD8D768BC354F3DEAE84AB3ED7E0AC4013DD6F7675573C`。新規合成なし、音質が改善したという主張はしない。
- 最終の橙色flat領域RGBは`(215,118,85)`。指定`(217,119,87)`に対して最大差2で、素材から最終動画までの色の再変換を確認した。
- 完成MP4の2／10／16.5／20.5秒を抽出して目視。3場面の絵柄と色面が異なる、見出し・非公式表示・字幕が重ならない、最後に図解を保持する、生成画を実UIと表示していないことを確認した。小さな実UI全文のスマートフォン可読性や聴感の公開受入は未実施。
- [独立検証JSON・抽出フレーム](../../outputs/studio/verification/claude-illustrated-20260906/final-review/20260906T070018Z/verification.json)。`verify_result.py`で再検証可能。
- [投稿用タイトル・説明文TXT](../../outputs/studio/verification/claude-illustrated-20260906/renders/80190D37BD2EA49FB54782BEDB903DD798F376DAB4EA1B331B954753F8A8410B/publication.txt)。
- [標準納品ZIP](../../outputs/studio/deliveries/production_18812c9ff18e4955858700ee7815f678/3EC5887D647F9192465A3AD422FBC5E73CE2B3F422989C10F78FD7396CFD6714/delivery-package.zip): 5,651,557 bytes、SHA-256 `D2AA4DEA5EB8A6161A4DB53F5AF540780F22D6790D4AD08B18BE2813D12801FC`。13項目、ZIP全エントリCRC検査成功。Job `job_12ae91306fd0498f8356297e9d19d3be`。
- 追加収録・外部チャット送信・有料TTS呼び出し・投稿・Git commit／merge／pushは0。内蔵画像生成1回は別工程であり、画像生成の利用量をStudioの0円API台帳が測定したものではない。
