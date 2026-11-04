"""Regenerate only the confirmed misread f02. Keep every initial output."""
import json,os,sys
from narrate import ROOT,HERE,OUT,cli,synthesize

def repair():
    assert cli('get',project_id=HERE.name)['project']['accepted_proposal']['proposal_id']=='proposal-v01'
    script=json.loads((HERE/'full-dialogue-v03.json').read_text(encoding='utf-8'))
    turn=next(x for x in script['turns'] if x['id']=='f02')
    turn['reading']=turn['reading'].replace('ジーピーティーシックス アストラ','ジーピーティー ろく アストラ')
    script.update(status='v01_structure_accepted_f02_reading_repaired_media_review_pending',revision_note='完成音声でGPT-6をGPT-5と読んだことを二つのAI音声確認で検出。f02だけ明示した数字の読みへ変更。表示原稿は同じ。')
    target=HERE/'full-dialogue-v04.json';value=json.dumps(script,ensure_ascii=False,indent=2)+'\n'
    if target.exists():assert target.read_text(encoding='utf-8')==value
    else:target.write_text(value,encoding='utf-8')
    if not os.getenv('GEMINI_API_KEY'):
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,'Environment') as registry:os.environ['GEMINI_API_KEY']=winreg.QueryValueEx(registry,'GEMINI_API_KEY')[0]
    result=synthesize(OUT/'voice/v02/f02',turn['reading'],'male',profile='conversational_v3')
    print(json.dumps(dict(id='f02',revision='v02',seconds=result['seconds']),ensure_ascii=False),flush=True)

if __name__=='__main__':repair()
