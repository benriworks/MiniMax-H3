"""Recheck original and delivered bytes and publish only nonprivate QC summaries."""
import json,math,sys
from pathlib import Path
import produce as p
def main():
    original=json.loads((p.OUT/'source-inventory.json').read_text(encoding='utf-8'))
    for item in original['items']:
        path=p.SOURCE/item['path'];assert path.stat().st_size==item['bytes'] and p.sha(path)==item['sha256'],item['path']
    result={'source_files_unchanged':len(original['items']),'cuts':{},'human_reviewed':False,'user_approved':False,'published':False}
    for kind in ['short','full']:
        dest=p.OUT/'release/v01'/kind;qc=json.loads((dest/'qc.json').read_text(encoding='utf-8'));plan=json.loads((dest/'timeline.json').read_text(encoding='utf-8'));video=p.ROOT/qc['file']['path'];assert p.sha(video)==qc['file']['sha256']
        probe=json.loads(p.run(['ffprobe','-v','error','-count_frames','-show_streams','-show_format','-of','json',str(video)]).stdout);vs=next(s for s in probe['streams'] if s['codec_type']=='video');au=next(s for s in probe['streams'] if s['codec_type']=='audio')
        assert (vs['width'],vs['height'])==(plan['width'],plan['height']) and vs['r_frame_rate']=='24/1'
        assert abs(float(probe['format']['duration'])-plan['seconds'])<=1/p.FPS+.01
        assert au['codec_name']=='aac' and au['channels']==2 and au['sample_rate']=='48000'
        assert -17<float(qc['loudness']['input_i'])<-15 and float(qc['loudness']['input_tp'])<=-1
        layout=json.loads((dest/'text-layout.json').read_text(encoding='utf-8'));assert layout and all(x['fits'] for x in layout)
        listening=json.loads((p.OUT/'_private'/('ai-listening-'+kind+'-v01')/'review.json').read_text(encoding='utf-8'));assert not listening['audible_issues']
        samples=json.loads((dest/'qc-actual/frames.json').read_text(encoding='utf-8'))
        result['cuts'][kind]=dict(file=p.rec(video),seconds=float(probe['format']['duration']),dimensions=[vs['width'],vs['height']],frames=int(vs['nb_read_frames']),audio='AAC stereo 48kHz',loudness_lufs=qc['loudness']['input_i'],true_peak_dbtp=qc['loudness']['input_tp'],whole_decode='passed',decoded_samples=len(samples['samples'])+1,text_layouts=len(layout),ai_audio_issues=[],human_review='pending')
    article=p.OUT/'blog-handoff/v01'
    import re
    html=(article/'index.html').read_text(encoding='utf-8')
    for relative in re.findall(r'<img src="([^"]+)"',html):assert (article/relative).is_file()
    result['article_images']=len(list((article/'images').iterdir()));result['article_image_refs_verified']=True
    p.save(p.OUT/'technical-summary-v01.json',result)
    rows=['# v01の検証とレビュー範囲','','確認日：2026-11-01。媒体の技術検証、AIによる点検、人の試聴、採用、公開は別。','','| 項目 | ショート | フル |','| --- | --- | --- |']
    for label,key in [('実尺（秒）','seconds'),('実フレーム数','frames'),('実測LUFS','loudness_lufs'),('実測true peak dBTP','true_peak_dbtp'),('最終動画からの確認画像数','decoded_samples')]:rows.append('| '+label+' | '+' | '.join(str(result['cuts'][k][key]) for k in ['short','full'])+' |')
    rows+=['','- 両動画はH.264・24fps、AACステレオ48kHz。ショート1080×1920、フル1920×1080。全decode通過。','- 全20発話のPCMをhash照合。最終MP4の音声を台本無しで独立AI点検し、余分な台詞・聞き取り問題の指摘なし。「ドッツ」「ブレンダー」の読みを記録。AI点検は人の試聴ではない。','- 各発話の前・中・後と終了画面を最終MP4から採取。文字の収まり、顔・字幕・実画面の領域を確認。全フレームを人が確認したとの主張ではない。','- 元38ファイルの容量・SHA-256を終業時に再照合して一致。提供blendと制作コードは再実行せず、現在の未保存Blenderも変更しない。','- 記事用画像9点・草稿HTMLの画像参照を確認。ZIP20項目のCRCと各member SHA-256を照合。','- 共通企画台帳revision29：準備上のblocker・warningなし。台帳のtechnical_verifiedは媒体検査を自動取込しないためfalseのまま。実際の媒体検査の根拠は各qc.jsonとtechnical-summary-v01.json。','- Driveは本人所有で3ファイルの名前・サイズ・保存先・所有者権限を確認。ブラウザーのプレーヤーは読み込み中で、再生成功やスマホ実機での再生とは扱わない。S3代替はCLIのHEADと全GET・hash検証を通過。','- 最終試聴・完成版採用・YouTube投稿・ブログ実装と公開・mainマージは未実施。','','## 制約と編集判断','','依頼の原会話・連続操作録画がないため、依頼文は依頼例と明記し、工程は実画面の静止画と表示。モデルは独自の簡略模型、完成映像はCGカメラ移動。正確な復元、完全無人、準備を含む時短率を断定しない。縦元映像720×1280の拡大を新規高画質撮影とは呼ばない。既存MiniMax反応動画は再利用で、新規人物生成ではない。','', '終了画面は映像としての配置用。関連動画・登録の実際のクリック要素はYouTube Studioで設定する。']
    (p.HERE/'VALIDATION_JA.md').write_text('\n'.join(rows)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
