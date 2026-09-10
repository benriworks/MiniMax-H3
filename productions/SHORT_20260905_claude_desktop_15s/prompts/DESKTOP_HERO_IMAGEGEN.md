# デスクトップ紹介動画の生成画像

方式: 組み込みimage_gen（imagegenスキル）。外部APIキーを使うCLIは使用しない。

用途: 中盤5〜10秒のフォトリアルな背景。アプリ画面は含めず、説明用UI・日本語テロップをRemotionで別合成する。画像そのものは静止画生成であり、動画生成モデルではない。

## 送信プロンプト

```text
Use case: product-mockup
Asset type: original photographic hero insert for a Japanese 15-second vertical video about using a coding assistant through a desktop application.
Primary request: a high-end photorealistic editorial photograph of a contemporary compact laptop on a pale wooden desk, conveying an approachable, calm desktop coding workspace.
Scene/backdrop: tasteful quiet home workspace, softly textured warm ivory wall, bright diffused window daylight, restrained realistic shadows. Only laptop and one understated ceramic cup; uncluttered.
Subject: an unbranded silver laptop fully visible and open, screen facing almost toward camera with a subtle three-quarter angle. The screen is a uniform pale warm gray blank panel, no interface and no text; keyboard and trackpad physically credible.
Style/medium: photorealistic product photography, natural material grain, crisp product edges, tactile metal, refined soft daylight; not an illustration, not a flat UI design.
Composition/framing: tall portrait 9:16 composition. Laptop is prominent in the middle-to-lower middle of the frame, occupying around 70 percent of the width. Leave uncluttered softly lit wall in the upper third for large video titles, and pale desk foreground at the bottom for later subtitles. Entire laptop stays away from the extreme right edge, where video-platform buttons may overlay. Camera around desk height slightly above keyboard, normal-lens perspective, no dramatic wide-angle distortion.
Lighting/mood: fresh, accessible, quietly confident, warm neutral tones with subtle terracotta material accents.
Text: absolutely no text, letters, numbers, logos, branding or watermark. The actual Japanese titles and illustrative controls will be composited later as sharp code-rendered elements.
Constraints: no people, no hands, no floating UI, no fictional app screenshot, no luminous sci-fi effects, no extra monitors or screens. A real-looking usable laptop, not melted geometry. Generate at high resolution, portrait 9:16.
```
