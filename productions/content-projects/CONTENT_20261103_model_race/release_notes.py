"""Write scoped, measured delivery evidence after media and Drive readback."""
import json,re
from pathlib import Path
from produce import ROOT,HERE,OUT,dest,save,sha

def read(p):return json.loads(p.read_text(encoding='utf-8'))
def unwrap(x):
    while isinstance(x,dict) and isinstance(x.get('structuredContent'),dict):x=x['structuredContent']
    return x
def stamp(seconds):
    total=int(seconds);return f'{total//60:02}:{total%60:02}'

def build():
    info={}
    for kind in ['short','full']:
        folder=dest(kind);plan=read(folder/'timeline.json');qc=read(folder/'qc.json');assert sha(ROOT/qc['path'])==qc['sha256']
        av=read(OUT/'_private/media-review'/(kind+'-av-'+plan['revision'])/'review.json');assert av['media_access_ok'] and not av['material_issues']
        up=unwrap(read(OUT/'_private'/('drive-'+kind+'-'+plan['revision']+'.json')))
        meta=unwrap(read(OUT/'_private'/('drive-'+kind+'-readback-'+plan['revision']+'.json')))
        assert up['success'] and up['id']==meta['id'] and int(meta['size'])==qc['bytes'] and up['parent_id'] in meta['parent_ids'] and meta['shared'] is False
        info[kind]=dict(plan=plan,qc=qc,av=av,meta=meta)
    rows=[]
    for kind,x in info.items():
        q=x['qc'];p=x['plan'];scope=read(dest(kind)/'decoded-review/scope.json')
        rows.append(f"| {kind} / {p['revision']} | {q['seconds']:.3f}秒、{q['width']}×{q['height']}、24fps、{q['frames']}frames | {q['bytes']:,} bytes | {q['loudness']['input_i']} LUFS / {q['loudness']['input_tp']} dBTP | {scope['decoded_subtitle_states']}字幕状態、{scope['decoded_images']}復号画像 |")
    qc_doc='''# 完成候補の検証

2026-11-03。技術確認済みレビュー候補。人の最終試聴、ユーザー採用、YouTube／記事の公開は未実施。

| 動画・版 | 実尺・仕様 | ファイル容量 | 最終AAC測定 | 最終MP4の確認範囲 |
| --- | --- | --- | --- | --- |
'''+ '\n'.join(rows)+'''

両MP4を全decodeし、フレーム数と実尺を照合。字幕は固定フォントの実グリフ幅を測定し、最終MP4から全字幕ページの中央を復号。短尺58、長尺350種類の文字ボックスの収まりを確認した。復号画像を保存したことと、人が全フレームを目視したことは同じではない。代表フレームとコンタクトシートは助手が確認した。

実AVの圧縮プロキシをGemini 3.8 FlashでAI補助確認し、両最新版の重大な指摘は0件。これは人の試聴や新しい事実の外部照合ではない。初回フルv01のf02でGPT-6をGPT-5と読んだ指摘を、正解原稿を与えない台詞単独確認でも検出。原本を残し、f02のみ別版へ再生成。修正後の単独確認とフルv02で再確認した。Fableの長音寄りの聞こえ方、GPT-6の「ろく／シックス」の揺れは残るため、最終試聴の観点として残す。

音量は派生ミックスで調整し、原WAVを変更していない。BGMはexplanation_v1、頭尾強調、発話中減音。既存MiniMax動作6本と顔アトラスを再利用、新しいMiniMax課金呼び出しは0回。新規TTSは初回51台詞と修正1台詞。エンベロープによる簡易口パクで、音素単位の精密リップシンクではない。

Driveへショートv01とフルv02を保存し、ファイル名、容量、親フォルダー、非共有状態を接続ツールで読戻した。リモートSHA-256を取得したとはしない。ブラウザのショートプレビューは読み込み中のまま、1回再読込後も再生進行を確認できなかった。PC上のDrive再生、スマホ実機の再生は未確認。ローカルMP4のdecode成功とは分ける。Drive受領と私的な再生確認はoutputs/_privateへ保存し、Gitへ含めない。

共通字幕変更の回帰確認は`python -m unittest tests.test_editorial_captions`の8件成功。外部の視聴効果は未測定。共通CLIのreadinessは媒体の品質や公開許可を保証しない。報道／未確認、短尺の物語分類、原案540秒と実尺約579秒の差に関するwarningをそのまま保持する。

Driveプレビューの停滞を受けS3代替も確認したが、現行S3up設定のAllowedRootsが別プロジェクトに限定され、対象MP4のdry-runが範囲外として拒否された。AWS送信は0件。設定や認証、許可範囲を変更せず、別の認証への迂回も行っていない。Driveには元のMP4が保存されており、ダウンロード可能な成果物として渡す。
'''
    (HERE/'DELIVERY_QC_JA.md').write_text(qc_doc,encoding='utf-8')
    review='''# 演出・編集レビュー

対象：model-race-short v01、model-race-full v02。視聴者の「次々出るモデルは何が変わった？ 次はもう決まっている？」に答える。冒頭は取得済みのFable 5／Astra公式ビジュアルから転機へつなぐ。

適用技法：A1/A2/A3/A8（変化を先出しし疑問を回収）、B2/B7（図の段階更新と現在章）、C1/C2/C3/C5/C7/C8（質問→根拠、感情、比較時の退避、やわらかな既存男女）、D1/D2/D5/D6/D7（役割別の文字、保護語、確度の色と線、引用）、E2/E4/E6/E7（数字の間、台詞単位音声、減音）、F1/F2/F8（意味の切替と図・字幕更新の区別）、Gの締めと次への導線。全60技法を埋めたとはしない。視聴維持の効果は未測定。

| 実時刻・台詞 | 視聴者の疑問 | 画面の役割と見る対象 | 更新・保持の意図 | 人物を出す理由 | 文字の分担 | 記事へ残す素材 |
| --- | --- | --- | --- | --- | --- | --- |
'''
    motion={'opus5','computer_result','cadence','report_result','closing_hope','audience','related','short_closing'}
    for kind,x in info.items():
        for t in x['plan']['turns']:
            v=t['visual'];question=v.endswith('question');person='両者の疑問・注視。発話者のみ簡易口パク' if question else '意図に合う既存MiniMax動作を一度再生し保持' if v in motion else '引用・図・数値を主役にして退避'
            update='疑問を言い切って次の根拠へ。字幕更新とカットを区別' if question else '図の要素、値、強調を説明順に更新。音声実尺と末尾の確認時間を保持'
            role='人物' if question else '人物と短い結論' if v in motion else '公式引用' if 'source' in v or v=='astra62' else '図解・確認'
            review+=f"| {kind} {stamp(t['start'])}〜{stamp(t['end'])} / {t['id']} | {t['heading']} | {role}：{v} | {update} | {person} | 章＝位置、見出し＝論点、図ラベル＝対象、字幕＝発話 | 出典台帳、引用、図と表示原稿を共用 |\n"
    review+='''
フル末尾10秒はナレーションを終え、関連動画と登録のための固定領域とBGMフェードを保持する。未発行のリンクを焼き込まない。PIPとMiniMax動作は別処理で、前者の顔の高さと目線を合わせ、後者は各原本から明示した領域を切り出した。価格棒は実数を原点0から表示し、架空の性能順位や仕事量を描かない。

技術、AI補助、Drive読戻しの範囲は[検証記録](DELIVERY_QC_JA.md)。ユーザーに確認いただく点は、具体的な動作の言い方、掛け合いと声の聞きやすさ、フル後半の報道／噂の分かりやすさ。完成品採用と公開は未実施。
'''
    (HERE/'EDITING_REVIEW_JA.md').write_text(review,encoding='utf-8')
    title=(HERE/'TITLES_AND_PUBLICATION_JA.md').read_text(encoding='utf-8').split('\n## 実尺チャプターとレビュー版')[0]
    title+='\n## 実尺チャプターとレビュー版\n\nショートv01：59.75秒。フルv02：578.958秒。採用・公開前のレビュー候補。Driveリンクは私的受領へ保存し、ここへ埋め込まない。YouTube公開URLと詳細記事URLは未発行。\n\n'
    title+='\n'.join(stamp(c['start'])+' '+c['title'] for c in info['full']['plan']['chapters'])+'\n'+stamp(info['full']['plan']['body_seconds'])+' 関連動画とチャンネル登録\n'
    (HERE/'TITLES_AND_PUBLICATION_JA.md').write_text(title,encoding='utf-8')
    history=HERE/'PREPRODUCTION_HISTORY_JA.md'
    if not history.exists():
        old=(HERE/'RESUME_AND_KNOWHOW_JA.md').read_text(encoding='utf-8')
        history.write_text('# 初回準備時点の保存記録\n\n以下は構成への返答を受ける前の履歴。現在値はRESUME_AND_KNOWHOW_JA.mdを参照。\n\n'+old,encoding='utf-8')
    resume='''# 再開履歴兼ノウハウ：OpenAI×Anthropic新モデル競争

更新日：2026-11-03。案件ID：CONTENT_20261103_model_race。

## 現在地と次の作業

- 制作索引、総覧、編集プレイブックとレビュー票、題名と掛け合い、共通企画工程、画面引用、ナレーション、BGM既定、動画とブログの共通工程を参照した。blogの文章と画像の現行規約も確認。
- ユーザーが企画v01の大筋を確認。抽象的な名詞を、公式や原発信で使う言葉へ直す指定を受けた。[返答原文と対応表](WORDING_REVISION_JA.md)。同じ構成の再確認は不要。完成動画・記事の採用と公開には広げない。
- [21出典](sources.json)。Fable 5.1は公式の日付差から月までを採用。Astra 6.1は公開見送り報道、6.2は元の出所が不明な投稿画像として区別。公式用語と具体例を会話、図、記事に反映した。
- 既存の架空の成人男女を継続。男性は疑問役、女性はやわらかな会話で根拠へ案内。外見と服装、男性左／女性右、Aoede／Charon、6種類の既存MiniMax動作を再利用。新しい人物の量産なし。
- 最新版は以下の2本。両MP4を全decode、字幕全状態の収まり、最終AAC音量、実AVのAI補助確認まで実施。[検証記録](DELIVERY_QC_JA.md)、[絵コンテ兼編集レビュー](EDITING_REVIEW_JA.md)。人の最終試聴、ユーザー採用、公開は未実施。
- Driveのファイル名・容量・親・非共有状態を読戻し済み。PCのプレビューは読み込みが継続し、再生進行は未確認。スマホ実機も未確認。接続ツールでの保存確認を再生成功へ読み替えない。私的なURL・受領はoutputs/_privateへ。
- 次の作業：ユーザーによる2本のレビュー。言い方、声とBGM、噂の区分への返答を記録し、修正があれば該当箇所だけ別版へ。Drive再生可否の確認も残す。動画と記事の公開、mainマージは別依頼。

| 動画ID・版 | 見出し | 実尺と仕様 | 所在と状態 |
| --- | --- | --- | --- |
| model-race-short / v01 | 【ChatGPT・Claude】Fable 5→GPT-6！AI競争で変わった3つのこと | 59.750秒、1080×1920、24fps | outputs/content-projects/CONTENT_20261103_model_race/release/v01/short/ai-model-race-short-v01.mp4。Drive保存済み、未採用 |
| model-race-full / v02 | 【ChatGPT・Claude】Fable 5からGPT-6.1 Solまで｜新モデル競争と次世代の噂 | 578.958秒、1920×1080、24fps、末尾10秒 | outputs/content-projects/CONTENT_20261103_model_race/release/v02/full/ai-model-race-full-v02.mp4。Drive保存済み、未採用 |

フルv01はf02の誤読があり、完成候補として共有せず保持。最新ショートはv01のまま。両動画の版番号を一律に繰り上げない。

## 制作原本と再開方法

コードと軽量資料は本worktree。ignored素材はcloneに付属しない。原本はoutputs/content-projects/CONTENT_20261103_model_race/以下。

- _private/captures：Computer Use撮影の原本。公式原本幅約1237pxで1400px到達とはしない。Claudeのモデルメニューは座標不整合で公開用撮影未取得。独自の性能対決は未実演。
- assets、motion-provenance.json、asset-manifest-v03.json：公式5引用、SNS2引用、既存アトラス、6動作の元hashと派生を追跡。Fable製品画像の追加切り出し座標も保存。
- voice/v01：初回51台詞。voice/v02/f02：誤読した台詞だけの再生成。字幕はshort-dialogue-v03、full-dialogue-v04の表示、音声は別のreadingを使う。
- release/v01/short、release/v02/full：MP4、timeline、SRT、派生音声、ミックス計画、QC、全字幕状態と最終復号画像。旧フルv01は保存。
- article/v04、review/v04：記事本文v03、10画像、alt、出典、hashとZIP。v04は同梱の公開準備文書を生成後の状態へ整合させた包装版。旧v03包装は保持。[素材引き渡し](ASSET_HANDOFF_JA.md)。記事のMDX組み込みと公開は未実施。
- _private/media-review：音声パイロット、初回AV、f02単独の初回／修正、最新版AVの受領。人の最終試聴と区別する。

実行の構成とコマンドは[独立設計](ARCHITECTURE.md)、[Mermaid図](ARCHITECTURE_DIAGRAM.md)。有料呼び出しは完了受領を再利用し、自動再送しない。既存版を再現するときは現在の既定がshort v01／full v02であることに注意する。

## 個別ノウハウと共通化

1. 「画面操作と仕事」を、公式の「コンピューター操作」とフォーム入力等へ具体化。公式語の並べ直しだけで終わらず動作と結果を伝える。AGENTSと総覧へ共通化した。
2. TTS原稿が正しくても番号の実音声が誤る。GPT-6→5を実AVと台詞単独で検出し、元を残して1台詞だけ修正。文字検査と実音声検査を分ける判断を総覧へ追加した。
3. 価格は標準APIの入力／出力の別軸。公式の実数を表示し、月額や作業総額への拡張を防ぐ。噂は色と線と音声で区分。
4. 長尺の全字幕画像抽出はFFmpeg式の深さに注意。単純な長い加算式が失敗したため二分木に修正。完成MP4の不良とは別のローカル検査処理の問題だった。
5. 名称、日付、出所に差があれば精度と限界を残す。6.2原投稿は初回403後に実ブラウザで閲覧できたが、元の出所不明という補足がある。閲覧成功を真正性の証明にはしない。

共通CLIはrevision 104、storyboard_ready、構成採用済み、媒体品質や公開はfalseのまま。報道／未確認、短尺の物語分類、原案540秒と実尺の差のwarningは保持する。共通字幕には任意保護語を追加し、8回帰テストが成功。新しいStudio画面や自動Drive送信を追加したわけではない。

S3代替は現行設定の許可範囲外でdry-run拒否、AWS送信0件。設定を変更したり、別の成果物フォルダーへ移して制限を迂回したりしない。Drive保存済みMP4を共有する。

## 更新履歴とGit保存

| 日付・版 | 変更理由と検証 | 残り |
| --- | --- | --- |
| 2026-11-03 初回準備 | 19出典、公式／SNS引用、企画、草稿v02、Drive資料。[当時の記録](PREPRODUCTION_HISTORY_JA.md) | 当時は構成返答待ち |
| 同日 構成v01採用 | 返答原文を共通CLIへ記録。日本語公式2出典追加、表現v03と記事v03 | 完成品採用は別 |
| 同日 ショートv01 | 7台詞、実尺59.75秒、動く標準API価格、公式画像、既存人物。全decodeと音量、AI補助AV確認 | 人の試聴、Drive再生進行、採用 |
| 同日 フルv01→v02 | 44台詞、誤読1台詞のみ修正。実尺578.958秒、終了画面10秒。全decode、音量、全字幕状態、AI補助AV確認 | 同上。記事組み込み、公開は別 |

専用ブランチcodex/model-race-short-full-20261103、個人fork benriworks/MiniMax-H3の[Draft PR #18](https://github.com/benriworks/MiniMax-H3/pull/18)へ軽量資料を保存する。baseは20チャンネル比較のcodex/youtube-20channel-benchmark-20261103（PR #17）。実際のcommitとpush照合は今回の保存結果を下に追記する。公式upstreamへの書き込み、mainマージ、媒体公開は行わない。
'''
    (HERE/'RESUME_AND_KNOWHOW_JA.md').write_text(resume,encoding='utf-8')
    print(json.dumps(dict(technical_candidates=2,ai_material_issues=0,drive_readbacks_verified=2,human_reviewed=False,published=False),ensure_ascii=False))

if __name__=='__main__':build()
