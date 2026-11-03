"""Publish a curated, linkable research report from locally verified receipts."""
import collections
import hashlib
import json
from pathlib import Path
import re
from analyze_video import OUT, ROOT, save

HERE=Path(__file__).resolve().parent
REPORT=ROOT/'docs/video-production/research/YOUTUBE_EXPLAINERS_20_20261103_JA.md'
ENDINGS=[
    'ツール紹介を終えて短い番組ロゴと挨拶。本編とプロモーションを分けて読む。',
    '本編の発話を終えて、支援者クレジット・関連枠・BGMの余韻へ。',
    '本編後に別企画の告知があり、スポンサー表示とロゴで閉じる。',
    '本編の締め・予告から、末尾はスポンサーサービスの画面とリンク案内へ。',
    '本編後は広告表示のある公式グッズ案内と、鳥のアニメーションの終了画面。',
    '末尾は技術誌の購読告知。割引・QR・URLを保持して行動を示す。',
    '制作の裏話とニュースレター案内を、本編の結論とは分けて見せる。',
    '人物と支援者表示から、別動画・登録・支援を分けた終了画面へ。',
    '動く回路を残し、次回の予告と支援への感謝。顔出しや派手な締めに頼らない。',
    'コードと結果を振り返り、作品共有へ誘導して固有アニメーションへ。',
    '実務的な意味までまとめ、人物イラストとSNS・推奨動画の終了画面へ。',
    '二人の会話と礼から、登録・おすすめ枠を持つ固定カードへ。',
    '講義の締めと、支援者・SNS・登録・おすすめ枠を分ける。',
    '分解した部品を前に総括した後、電子工作グッズと関連動画の告知へ。',
    '本編のまとめを終え、SNSアカウントのカードとBGMを残す。',
    '注意点と行動をまとめ、人物の礼から次動画・登録の領域を分けたカードへ。',
    '向き不向きを総括し、Excelの成果物を残したままキャラが挨拶する。',
    '本編まとめの後に宣伝表示を付け、告知と挨拶からCGアウトロへ。',
    '購入時の条件・実際の困りごとを示し、次のPC制作案とコメントへつなぐ。',
    '結果をまとめ、動きのある光るシミュレーションを余韻として見せる。'
]

def clock(value):
    value=int(round(value));return f'{value//60:02}:{value%60:02}'

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest().upper()

def build():
    channels={x['id']:x for x in json.loads((OUT/'channels-observed.json').read_text(encoding='utf-8'))}
    notes=json.loads((HERE/'editorial_observations.json').read_text(encoding='utf-8'))
    assert len(channels)==len(notes)==20
    records=[];samples=[];receipts=[];seconds_total=0;rejected_events=[]
    for index,note in enumerate(notes,1):
        item_id=note['id'];meta=channels[item_id];first=json.loads((OUT/'reviews'/f'{item_id}.json').read_text(encoding='utf-8'))
        focus=json.loads((OUT/'focus'/f'{item_id}.json').read_text(encoding='utf-8'))
        submission=json.loads((OUT/'_private'/item_id/'submission.json').read_text(encoding='utf-8'))
        focused=json.loads((OUT/'_private'/(item_id+'-focus-v02')/'submission.json').read_text(encoding='utf-8'))
        assert first['access_ok'] is True and focus['access_ok'] is True
        count=re.search(r'チャンネル登録者数 ([\d.]+)万人',meta['subscribers_display']);assert count
        assert float(count[1])*10000>=100000
        video_id=submission['url'].split('v=')[1]
        candidate=next(x for x in meta['video_candidates'] if 'v='+video_id in x)
        title=re.sub(r'^\d+ link Description: ','',candidate.split(', Value:')[0])
        title=re.sub(r' \d+ (?:時間|分|秒).*$', '',title)
        window=focused['windows'][0];valid=[]
        for event in focus['sample_changes']:
            at=event.get('absolute_seconds')
            if not isinstance(at,(int,float)) or not window['start']<=at<=window['end']:
                rejected_events.append({'id':item_id,'event':event,'reason':'outside requested sample window'});continue
            valid.append(event)
        boundaries=sorted(x['absolute_seconds'] for x in valid if x['kind'] in ('hard_cut','dissolve'))
        gaps=[b-a for a,b in zip(boundaries,boundaries[1:]) if b>a]
        if gaps:pacing=f'標本の隣接切替間は約{min(gaps):.1f}〜{max(gaps):.1f}秒。全編の平均ではない'
        elif boundaries:pacing='標本で画面転換は1件記録。他は保持・要素更新。平均尺は算出しない'
        else:pacing='標本で画面全体の切替は記録なし。同一画面の要素・視点・字幕等を更新'
        record={**note,'number':index,'name':meta['name'],'channel_url':meta['url'],'subscriber_display':count[1]+'万人','checked_date_jst':'2026-11-03','subscriber_source':'YouTube channel header, Computer Use','video_title':title,'video_url':submission['url'],'approx_duration_seconds':first['duration_seconds'],'ending':ENDINGS[index-1],'sample_window_seconds':window,'pacing':pacing,'timing_status':'AI-assisted approximate observations at requested 4 fps; not frame-exact measurements','human_full_listening':False}
        records.append(record);seconds_total+=first['duration_seconds']
        samples.append({'id':item_id,'url':submission['url'],'requested_window':window,'requested_fps':4,'events':valid,'counts_are_annotations_not_exhaustive_cut_measurement':True,'pacing_observation_ai':focus.get('pacing_observation'),'tail_window':focused['windows'][1]})
        for receipt in [OUT/'_private'/item_id/'response.json',OUT/'_private'/(item_id+'-focus-v02')/'response.json']:
            payload=json.loads(receipt.read_text(encoding='utf-8'))
            receipts.append({'id':item_id,'kind':'whole' if receipt.parent.name==item_id else 'focus','relative_path':receipt.relative_to(ROOT).as_posix(),'sha256':digest(receipt),'usage':payload.get('usage',payload.get('usageMetadata'))})
    save(HERE/'channels.json',records)
    save(HERE/'timeline-samples.json',samples)
    save(OUT/'validation.json',{'channels':20,'qualifying_subscriber_headers':20,'whole_video_success':20,'focused_video_success':20,'whole_input_approx_seconds':seconds_total,'excluded_timing_events':rejected_events,'raw_receipts':receipts,'initial_processing_schema_errors':20,'automatic_retry':False,'human_full_listening':False,'performance_causality_measured':False})
    lines=['# 技術・キャラクター解説20チャンネルの比較調査','',
      '確認日：2026-11-03（日本時間）。目的は、私たちの解説動画の構成・人物・字幕・音声・カット・締めを改善すること。再生数ランキングやチャンネルの優劣の採点ではない。','',
      '## 調査方法と確認範囲','',
      '- 20チャンネルすべてのYouTubeチャンネル画面をComputer Useで開き、公開登録者表示が10万人以上であることを確認。人数は丸め表示のスナップショット。検索結果の数字だけを根拠にしていない。',
      '- 日本語10・英語系10。技術解説を中心に、科学・数学・アニメーション・対話型を含め、1チャンネルにつき対象動画を1本選んだ。全投稿の網羅・無作為標本ではなく、ここに示す動画に限る観察。',
      f'- 20本の全編をGemini 3.8 Flashへ公開YouTube URLから映像・実音声として入力（合計のモデル報告尺は約{seconds_total/3600:.2f}時間）。静止画や検索文だけによる音声評価ではない。全編の文脈、冒頭、中盤、終盤を分析し、助手が結果を整理した。人間が20本を全編視聴したという意味ではない。',
      '- さらに全20本で、中盤30秒と末尾約40秒を4fps指定で独立に再分析。カット・カメラ移動・図の追加・字幕変更を分けた。秒数はAIによる概測であり、フレーム単位の計測や全編の平均カット長ではない。クリップはモデル報告尺の約1秒前までで、厳密な最終フレームは未測定。',
      '- ブラウザ実フレームは8チャンネル・12画像で追加照合。うち1画像は暗い章転換、1画像はスポンサー誌面だったため、説明図の証拠には使っていない。生キャプチャはログイン情報・関連欄を含むためローカルの私的記録だけに保存。',
      '- 音声の語り・間・抑揚はAIの実音声観察。正確な話速、ポーズ秒数、LUFS、声の製品名は測定・特定していない。声の聞きやすさの最終人間評価や維持率改善の因果は未検証。',
      '- 初回出力にあったMMSS混在・末尾と本編まとめの混同は、追加分析で照合。指定窓の外に出た1つの時刻注釈は除外した。動画内の技術ニュース・数値自体の正誤確認を目的とせず、今後のニュース出典として転用しない。','',
      '[次の制作へ適用する60項目](../EXPLAINER_EDITING_PLAYBOOK_JA.md)／[編集レビュー票](../templates/EDITING_REVIEW_JA.md)／[再開記録](../../../productions/research/RESEARCH_20261103_youtube_explainers/RESUME_AND_KNOWHOW_JA.md)','',
      '## 対象20チャンネルと対象動画','',
      '| # | チャンネル・登録者表示 | 今回確認した動画 | 得たい技法 |','| --- | --- | --- | --- |']
    for r in records:lines.append(f"| {r['number']:02} | [{r['name']}]({r['channel_url']})：{r['subscriber_display']} | [{r['video_title'].replace('|','／')}]({r['video_url']}) | {r['adaptation']} |")
    lines+=['','## カットと更新の30秒標本','',
      '「更新が多い」ことと「画面を切る回数が多い」ことは違う。以下の数はAIが注釈した境界の範囲であり、検出漏れがある。入口・出口を含む完成カットの長さ、各チャンネルの代表平均、成功に必要な秒数は算出していない。記録した切替にはハードカットとディゾルブを含む。','',
      '| # | 対象区間 | 観察したカット／保持の特徴 |','| --- | --- | --- |']
    for r in records:
        w=r['sample_window_seconds'];lines.append(f"| {r['number']:02} {r['name']} | {clock(w['start'])}〜{clock(w['end'])} | {r['pacing']} |")
    lines+=['','具体例：01では30秒の同じ図の中へ箱・矢印・反応画像を追加、02では数式とグラフを連続変化、09では波形とスイッチを保持して動作を見せる。一方、11では短い実写と資料・図を往復する。私たちの動画も、一律に3秒カットへせず、意味の転換と読む時間に合わせる。','',
      '詳しい時刻注釈は[timeline-samples.json](../../../productions/research/RESEARCH_20261103_youtube_explainers/timeline-samples.json)。4fps指定は元動画の撮影fpsを意味せず、厳密なカット計測精度も保証しない。','',
      '## チャンネル別の観察と取り入れ方','']
    for r in records:
        lines += [f"### {r['number']:02} {r['name']}",'',f"対象：[今回の動画]({r['video_url']})。公開登録者表示{r['subscriber_display']}。時刻は概数。",'',
          f"- 冒頭：{r['opening']}",f"- 本編・演出：{r['main']}",f"- テロップ：{r['captions']}",f"- ナレーション：{r['voice']}",f"- カット：{r['pacing']}",f"- 終盤：{r['ending']}",f"- 私たちへの適用：{r['adaptation']}",f"- 条件・留意点：{r['caution']}",'']
    lines+=['## 証拠・保存・今後の評価','',
      '- 公開用の要約データ：[channels.json](../../../productions/research/RESEARCH_20261103_youtube_explainers/channels.json)。各リンク・登録者表示・確認日・対象窓を保存。',
      '- 私的原本：`outputs/research/RESEARCH_20261103_youtube_explainers/`内のチャンネル画面記録、全編分析20件、追加分析20件、ブラウザ画像、検証JSON。APIキーは記録しない。',
      '- 区間分析の初回API形式はHTTP 400が20件発生。成功扱いにせず、公式APIリファレンスに合わせた別形式を1件で確認してから残りを実施した。失敗受領を保存し、自動再送はしない。今後は試験1件の成功を必須にして一括実行する。',
      '- 他チャンネルの映像・キャラ・音源・字幕を私たちの素材として取り込んでいない。画像原本・API生応答はGitへ入れず、軽量な観察・手順・検証要約だけ保存。',
      '- 本調査は構成改善の材料。次の新規制作・指定改訂で適用する。既存の完成動画の一括変更、公開・mainへのマージはしない。',
      '- 次回は対象動画・版と、冒頭離脱・視聴維持・完視聴・終了画面クリック等の取得済み指標を結ぶ。新旧題材・公開時期・視聴者条件が異なる比較の限界も残す。','',
      '方法の根拠：Google公式[動画理解の仕様](https://aistudio.google.com/docs/video-understanding)、[generateContentのVideoMetadata仕様](https://aistudio.google.com/api-reference/generate-content#Resource:Content)（2026-11-03確認）。これは分析方法の出典で、YouTube動画の内容の出典は各動画リンク。','']
    REPORT.write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps({'channels':len(records),'seconds_total_approx':seconds_total,'excluded_annotation_count':len(rejected_events),'report':str(REPORT)},ensure_ascii=False))

if __name__=='__main__':build()
