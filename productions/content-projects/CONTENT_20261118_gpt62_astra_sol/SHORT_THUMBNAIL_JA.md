# GPT-6.2ショートのサムネイル v01

2026-11-19。対象はショートv03（46.292秒）。依頼は「このYouTubeショートのサムネイルを作成して」。文字は「GPT-6.2」「Sol?」「Astra?」。動画と同じ人物の顔・髪・衣装を参照し、男性を左、女性を右へ胸上で配置した。

JPGはメディアルートの `release/v03/short/thumbnail-v01/gpt62-astra-sol-short-thumbnail-v01.jpg`。2160×3840、796,571 bytes、SHA-256 `a0d737b4925359fcd8737339d33321e5e076e42d611ae3545d27dbbc21096d88`。YouTubeのショート用推奨寸法に合わせた。採用・設定はレビュー後に確認する。 [YouTubeヘルプ](https://support.google.com/youtube/answer/72431?hl=ja)

## 素材と確認

- 制作時に使った旧モデル競争案件の `male-thinking.mp4` と `female-understanding.mp4` を照合し、約1.4秒から各フレームを抽出。ImageGenに人物参照として順に渡した。
- 初稿の「GPT-6.2」が中央正方形で欠けたため、組み込みImageGenでその見出しの大きさと位置を調整した。その生成原本（941×1672）を2160×3840へ拡大。JPEGの書き出し時に、上端104pxを反射で補って下端を同量切り、見出しと顔を中央に収めた。
- 最終JPGから、幅180pxの縦型・中央正方形・中央4:5をそれぞれ出し、3つの文字列、顔の切れ、背景と文字のコントラストを目視した。入力・出力のSHA-256、生成原本、確認画像はローカルの `_private/short-thumbnail-v01/`。FFmpeg 8.1.2で寸法とJPG形式を確認した。

## 再書き出し

`$source` は保存済みの `imagegen-final.png`、`$output` は別名のJPG出力先。再書き出しは保存済みの生成原本から行う。

```powershell
ffmpeg -v error -nostdin -n -i $source -frames:v 1 -vf 'scale=2160:3840:flags=lanczos,pad=2160:3944:0:104,fillborders=top=104:mode=mirror,crop=2160:3840:0:0,setsar=1' -q:v 2 -pix_fmt yuvj444p -update 1 $output
```

## ImageGenのプロンプト

初稿。

```text
Use case: ads-marketing.
Asset type: one finished vertical 9:16 custom thumbnail for a Japanese YouTube Short about when to choose GPT-6.2 Sol and Astra.
Inputs: the first source still is the exact male host identity; the second is the exact female host identity. Preserve both recognizable adult 3D anime-style faces, eyes, hair shapes and the blue shirt under each hoodie. The man wears his original dark charcoal hoodie and is thoughtfully considering something; the woman wears her original cream hoodie and has a small, confident smile. Both should look toward the viewer. Use the references for identity, not for the original sitting composition.
Composition: two large equal-height head-and-shoulders portraits, man at left and woman at right, facing toward the camera, no chairs or laptops. Build a crisp studio poster with a clear teal half on the left, amber-gold half on the right, and a restrained dark navy gradient around the typography. Use a simple soft diagonal meeting of the two colors. The bright rim lighting shapes the silhouettes, but keep skin colors natural. Make the eyes and hair sharp. This is a polished editorial YouTube thumbnail, not a screenshot. The main content is a single compact composition: all three text runs and both complete faces must be safely inside the vertically centered 1:1 square of a 9:16 canvas. Leave room around both outer sides (at least 10% of width). Upper and lower surplus area is atmospheric color and shoulders; do not use blank padding bars.
Typography: render only the following words, exactly spelled and fully legible. Center 'GPT-6.2' across the full canvas in white bold geometric sans, high contrast, near the top edge of the safe square. Immediately below that, on a single line, place 'Sol？' on the left in bright mint and 'Astra？' on the right in warm light gold, in extra-bold heavy geometric sans, equally prominent, with a dark stroke if needed. These two model names should be the biggest type. Then below the text show the two faces; no text overlaps eyes or hair. The first name is uppercase S lowercase o and l. The second name is uppercase A lowercase s t r a. Each name gets exactly one question mark. Do not add any other lettering, fake UI, logos, tiny labels, frames, icons, or watermark. Make it instantly legible as a 180px-wide thumbnail.
```

見出しの改訂。

```text
Use case: precise-object-edit. Edit this exact vertical YouTube Shorts thumbnail with one narrowly scoped change: adjust only the single white heading "GPT-6.2". It is slightly too high and oversized. Reduce its size evenly to about two-thirds of the canvas width, center it, and move it downward. On the 1672-pixel-tall preview, the white letters should start around y=395–400 (24% of the height) and end before y=510. This places the WHOLE heading inside the centered square. Leave a small clean gap before the green and gold words. Retain the exact text GPT-6.2.
Everything else is the original artwork: keep the very large green "Sol?" on the left and gold "Astra?" on the right in a single row, at the same approximate y=520 to y=690 area. Keep the same faces, hairstyles, body framing, thoughtful hand and smile, identical color split and lighting, in the same positions. Do not redraw or stylize the two hosts. Restore the smooth existing studio gradient behind the moved heading. No extra text, borders, icons, or decorations. Keep the format portrait 9:16 and ensure the heading, both names, and both faces are completely readable in the central square crop.
```
