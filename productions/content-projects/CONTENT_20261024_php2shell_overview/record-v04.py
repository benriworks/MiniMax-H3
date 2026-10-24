"""Record a human-requested pose change without changing character adoption."""
from pathlib import Path
import copy,json,sys
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from tools.studio.content_workspace import ContentWorkspace
from tools.studio.database import StudioDatabase
from tools.studio.shorts_creator import read,check
PID=HERE.name
service=ContentWorkspace(ROOT,StudioDatabase(ROOT/'outputs/studio/studio.sqlite3',workspace=ROOT,recover=False))

def apply(action,data,operation):
    path=HERE/'inputs'/(operation+'.json')
    if path.exists():
        body=read(path)
        if body['data']!=data:raise ValueError('Frozen operation changed')
    else:
        body={'operation_id':operation,'expected_revision':service.get(PID)['project']['revision'],'data':data}
        path.write_text(json.dumps(body,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return service.apply(PID,action,body)

apply('feedback',{'feedback_id':'php_user_revision_v04','proposal_id':'proposal_php_overview_v01','kind':'revision_request',
    'text':(HERE/'inputs/user-feedback-v04.txt').read_text(encoding='utf-8').strip(),
    'interpretation':'v03改善の評価と、同じ男性への表情・動作修正依頼。軽い困り顔と緩い拳を顎の下に添える仕草でMiniMax人物動画を生成し、冒頭だけ差し替える。人物版1を維持し、音声・字幕・図解・事実・時刻を保存。全体や新生成結果への最終採用とは扱わない。'},'php_revision_v04_feedback')
proof_path=ROOT/'outputs/content-projects'/PID/'motion/v02/miura-concerned-chin-v04/visual-review.json'
if proof_path.exists():
    proof=read(proof_path);clip=check(proof['artifact'])
    if proof['review_status']!='visual_review_passed':raise ValueError('Actual generated gesture needs AI review')
    apply('asset',{'asset_id':'miura-concerned-chin-v04','kind':'generated_video','path':clip.relative_to(ROOT).as_posix(),
        'visibility':'private','privacy_review':'passed','character_id':'miura_wataru','character_version':1,'provider':'minimax',
        'generation_record':proof_path.relative_to(ROOT).as_posix(),'caption':'同じ採用画像から、軽い困り顔で緩い右拳を顎の下へ添える動作を生成。生成・AI確認と最終ユーザー採用は別。'},'php_v04_motion_asset')
    # Use the preserved v03 board so repeated invocations cannot adopt later edits.
    old=read(HERE/'workspace-state-v03.json')['project']
    episode=next(e for e in old['episodes'] if e['episode_id']=='php2shell_overview')
    board=[{k:v for k,v in s.items() if k not in {'needs_review','review_reasons','last_review'}} for s in copy.deepcopy(episode['storyboard'])]
    baseline=read(HERE/'creator-story-v03.json')
    assert [s['narration'] for s in board]==[s['narration'] for s in baseline['scenes']]
    board[0].update(asset_ids=['miura-wataru-reference','miura-concerned-chin-v04'],character_action='軽い困り顔。緩く握った右手を顎の下へそっと添えて考える。目・眼鏡・口と字幕を分離。',visual='新規MiniMax人物動画を全面表示。初期の元画像の笑顔を避けて使用区間を選ぶ。')
    apply('storyboard',{'episode_id':'php2shell_overview','scenes':board},'php_storyboard_v04')
state=service.get(PID)
(HERE/'workspace-state-v04.json').write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Pose revision feedback recorded; final motion adoption remains pending')
