# 冬服のGPT-6.2解説の制作構成

ショート・フルは `dialogue.json` の並びで別々に構成する。台詞は表示用、読み上げ用、話者、参照する映像を持つ。モデル選択・返信・公式リリースの原画面と宿の比較表が両版の共通入力。撮影時の個人情報を含む原本は主cloneの出力内に置き、公開用画像は座標を指定して切り出す。

| 担当 | 処理 |
| --- | --- |
| 実演、人物 | `specimen.py` が架空の料金表を描く。`prepare_visuals.py` は実画面の公開用領域と冬服人物の左右を保存する。`shoot_pair.py` が同じ冬服画像を基準に2種類のH3二人動画を生成し、受領したタスクから再開する。未応答の個別撮影は別記録に保持する。 |
| 音声 | `narrate.py` はGoogleの `gemini-3.8-flash-tts` を指定し、既存の話者割当てと会話用プロンプトを利用。WAVヘッダー・サンプル数、モデルと話者を確認。個々の入力・応答はローカル保存。`edit_voice.py` が正式版の1台詞を日本語の終了後の無音で切り出す。 |
| 映像と音 | `render.py` は台詞のPCM長から24fpsの絵と字幕を配置する。BudouXと既存の `editorial_captions` で金額・モデル名・宿名を保護し、`art.py` の縦横専用構図と実映像を合成。`longform_audio` のオリジナル伴奏を `explanation_v1` でミックスし、FFmpegで2パス音量調整、H.264/AAC書き出しと全デコードを行う。 |
| 確認と配布 | `verify_speech.py` はローカルASR、`check_words.py` は原稿を渡さない独立音声照合。`review_frames.py` は最終MP4から字幕ページごとに実フレームを抽出。`kit.py` はカバー・概要欄・実尺チャプター、`article_package.py` は記事ZIP、`studio_record.py` はStudioの企画・根拠・草稿記録を扱う。 |

[独立したMermaid図](ARCHITECTURE_DIAGRAM.md) ・ [再開手順と媒体証跡](RESUME_AND_KNOWHOW_JA.md)。
