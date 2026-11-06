# BERT・GPT誕生史：編集を再現する手順

2026-11-07。対象はshort v07／full v05、記事v04。白衣版v02の顔・衣装・役割・声を継承する。制作コードの基準は `55138d7`。今回の記録では追加TTS・人物生成・動画書出しを行っていない。

入口は[索引](../../../docs/video-production/README.md)→[総覧](../../../docs/video-production/PRODUCTION_KNOWHOW_JA.md)→[案件記録](RESUME_AND_KNOWHOW_JA.md)。入力の所在とhashは[再現用台帳](reproduction-inputs-v01.json)、確認時刻は[QC v04](FINAL_REVIEW_QC_V04_JA.md)、画面は[Renderer](produce_v04.py)を正とする。

## 編集判断を再利用する

| 順序 | 助手が行うこと | 今回の具体例と確認 |
| --- | --- | --- |
| 結果を先に見せる | 疑問と答えを同じ具体例で示す | GPT＝次を予測、BERT＝隠した語を予測。現在のChatGPTを2018年の製品として扱わない |
| 画面の主役を決める | 見る対象・疑問・回答・人物表示の理由を場面ごとに割り当てる | 具体例→仕組み→根拠→同じ具体例へ戻る。箱と長文だけにしない |
| 図を段階更新する | 語・候補・接続・隠す／見せる順を意味に合わせる | 次語予測、bankの多義性、穴埋め。字幕更新とカット数を分ける |
| 人物を使い分ける | 質問、思考、困り、気づき、納得に画角と動作を対応させる | 顔アップ・胸上・中景・二人・人物なしの原図。所持素材数と実使用数は別 |
| 公式根拠を読む | 原図の全体→注目部分→図外の日本語説明 | BERT/GPT/ELMoの全体から各パネルへ。小さい英語の全記号を読ませない |
| 字幕と声を分ける | 表示文・読み文・保護語・実フォント幅を照合する | 画面はGPT・BERT、音声は読み指定。語中改行・無断縮小を避ける |
| 題名をセットにする | 投稿題・冒頭見出し・サムネイル・記事題を目的別に用意 | 投稿題の【AI】を保存ファイル・Drive案内・チャットでも維持 |
| レビューする | 技術QCに加え、5指摘を最終MP4の実フレームで再確認 | 余白、変化、公式根拠、人物の画角、題名。人の採用・公開は別 |

本編ショット18／74という数、年表、白衣、今回の配色・一定BGMを他企画へ無条件に固定しない。意味のない切替で更新数を増やさず、読む時間を残す。

## この案件の設定

- 縦1080×1920／横1920×1080、24fps。字幕64px／50px。NotoSansJP-Variableのaxis650。文字の収まりは実フォントで確認する。
- 旧10＋新胸上2のnative人物素材を保持、全編の実使用は旧6＋新2。追加分はQ3 diffusion／Q2 text encoder／Turbo8 steps、480×864・124frames・24fps。[画像プロンプト](image-prompts-closeup-v04.json)、[動作プロンプト](motion-prompts-v04-closeups.json)、[切り出し来歴](closeup-generation-and-edit-v04.json)を参照。
- 原本下端の生成文字を避け、上部0〜642pxを別派生へ切り出した。顔や原図の文字を塗り直さない。口の動きは完全な音素同期ではない。同じprompt・seedでも別環境の生成画素の完全一致は保証しない。
- 音声はCharon／Aoede、短編8＋フル35台詞。累計45生成中、現役43台詞。映像だけの改訂は検証済み音声を再利用する。
- BGMは「夕暮れのキャンパス」／甘茶。基準-31 LUFS、発話ごとのducking・頭尾boostなし、頭0.3秒／尾1.2秒フェード、ループ接続2秒。この案件の設定であり、共通explanation_v1の置換ではない。**Content ID登録なし**。

## 入力を照合する（読取りのみ）

Gitに素材本体は付属しない。別worktreeではコード、同じ案件IDのoutputs、H3実行環境を区別し、入力台帳の139ファイルを元の相対位置へ復元する。台帳はbytes・SHA-256を持ち、素材本体・キー・共有URLを持たない。次の確認はリポジトリルートから実行し、API・GPU生成・画面操作を行わない。

```powershell
$env:PYTHONUTF8='1'
@'
from pathlib import Path
import hashlib,json
root=Path.cwd()
record=root/'productions/content-projects/CONTENT_20261106_ai_bert_gpt_history/reproduction-inputs-v01.json'
manifest=json.loads(record.read_text(encoding='utf-8'))
for item in manifest['inputs']:
    path=root/item['path']
    assert path.is_file(),item['path']
    assert path.stat().st_size==item['bytes'],item['path']
    assert hashlib.sha256(path.read_bytes()).hexdigest()==item['sha256'],item['path']
print('verified inputs:',len(manifest['inputs']))
'@ | python -
```

観測環境はPython3.12.2、NumPy1.26.4、Pillow12.3.0、PyMuPDF1.27.2、markdown-it-py4.0.0、requests2.32.5、budoux0.10.2、FFmpeg8.1.2。フォントhashも台帳にある。全依存の導入済み保証ではなく、2026-11-07の観測値である。

## 同じ音声で、新しい映像版へ書き出す

以下は実行例で、今回の記録作業では実行していない。入力検査を先に通し、必要な原本を復元する。既存人物動画を使う場合はH3を起動しない。既存releaseを削除して再実行しない。

例はshort v07の音声を空いているv08へ再利用する。フルは `kind='full'`、`revision='v06'`、`source_revision='v05'`。版が既存なら別の未使用版を選ぶ。

```powershell
@'
import sys,shutil
sys.path.insert(0,'productions/content-projects/CONTENT_20261106_ai_bert_gpt_history')
import produce_v04 as production
kind='short'
revision='v08'
source_revision='v07'
production.old.REVISIONS[kind]=revision
target=production.old.dest(kind)
assert not target.exists(),'Choose a new revision; keep existing releases'
production.render(kind)
source=production.OUT/'release'/source_revision/kind
for name in ['mix.wav','narration.wav','music-mixed.wav','audio-provenance.json']:
    with (source/name).open('rb') as src,(target/name).open('xb') as dst:
        shutil.copyfileobj(src,dst)
import audio
audio.mux(kind)
'@ | python -
```

Rendererは旧処理を再利用する。`audio.py` 単独実行の版は旧short v03／full v02へ向くため、上のように同一プロセスで版を指定してimportする。声が変わらなければmixを再生成せずPCM hashを照合する。声を直すときだけ該当台詞を新IDへ生成し、字幕・尺・記事の依存先も更新する。

この経路は原曲再読込み・新規TTSを行わない。BGM再mixには `audio.source_music()` の私的inventoryと許諾済み原曲が必要。原曲hashは `audio.py`。原曲単体・私的inventoryをGitや公開ZIPへ複製しない。

## 公式画像・原論文と記事の復元条件

[公式画像台帳](official-assets-v04.json)は取得6件／実使用4件。`fetch_official_v04.py` は保存済みHTMLの実リンクを前提にする。最新Webの自動収集ではなく、再取得でhashが変わったら旧台帳を上書きせず調査する。直接取得をPC撮影とは呼ばない。

BERT原論文Fig.1は[出典と座標](official-vector-quote-v04.json)に従い、PDFのpage3（Python index2）、clip `[72,42,524,177]`、scale5で2260×675へ描画した。元PDFと派生hashを台帳に含めた。モデル別cropは[QC](FINAL_REVIEW_QC_V04_JA.md)とRendererを参照。透明画像は白へ合成し、原図ラベルを書き換えず、Ben Barryの作品クレジットを保持する。

記事は自作図7＋引用4の11画像。`package_article_v04.py` は `release/v03/full/timeline.json` と `article/v03/index.html` のCSSにも依存するため、最新MP4だけを移しても再構築できない。両入力を台帳に含めた。同スクリプトはarticle v04を出力するので、既存v04のある場所で再実行せず、別の検証用worktreeへ原素材を復元するか、出力版を明示して改訂する。

PDFは `package_pdf.py --article-version v04 --pdf-version v06` の派生で、既存PDFを上書きしない。記事HTML・ReportLab・Meiryoフォントが必要。2026-11-07には標準Pythonと既存H3 venvにReportLabがなく、前回PDF生成環境の正確な版も記録されていない。再生成時は専用環境で導入・版を記録し、7ページ・11画像・日本語抽出・図の固定幅と代表ページを再検査する。この不足を動画再編集の条件や既存PDFの確認結果と混同しない。

## 共有と資産化

1. 新MP4の全decode、実尺・寸法・frames、全字幕状態、最終AACの音量・true peakとhashを検査する。
2. 冒頭、具体例、公式原図、人物の寄り、比較、締めを実フレームで確認する。技術合格・AI所見だけで編集採用にしない。
3. 不変音声のPCM、ZIP全member hash、PDF実ページも確認する。小さいproxyだけで原図の細部を判定しない。
4. 【AI】付き題名、動画、記事案・素材と確認事項2〜3点を用意。Driveを優先し、保存読戻しと実機再生を分ける。
5. 共通規約・総覧・案件履歴・索引、影響する構成本文・Mermaid図を更新。実remoteを照合し、軽量資料だけ個人forkへ保存する。

今回の記録では共通7ファイルのunittest計37件、入力139ファイルと既存の最新MP4二本のhashを確認した。人の全編試聴・スマホ再生・完成品採用・公開を新たに確認したものではない。
