"""Register actual H3 pose proofs incrementally; never infer six completed clips."""
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).parent
OUT=ROOT/'outputs/content-projects'/HERE.name;sys.path.insert(0,str(ROOT))
from tools.studio.database import StudioDatabase
from tools.studio.content_workspace import ContentWorkspace

def main():
 svc=ContentWorkspace(ROOT,StudioDatabase(ROOT/'outputs/studio/studio.sqlite3',workspace=ROOT,recover=False));pid=HERE.name
 def current():return svc.get(pid)['project']
 def apply(action,data,token):return svc.apply(pid,action,dict(operation_id='op_pro_pose_'+token,expected_revision=current()['revision'],data=data))
 jobs=json.loads((HERE/'motion-jobs-v01.json').read_text(encoding='utf-8'))
 fid='feedback_pose_revision_20261031'
 if not any(f['feedback_id']==fid for f in current()['feedback']):
  apply('feedback',dict(feedback_id=fid,proposal_id='proposal_pro_usage_v01',kind='comment',text=jobs['user_request'],interpretation='採用済み48秒の構成と声・男女の外見を維持し、思考／喜び／納得の新規H3素材を各人3本追加する。新規動画の生成・差し替えの依頼であり、完成動画や公開の承認ではない。'),'request_20261031')
 states=[]
 for job,item in jobs['jobs'].items():
  d=OUT/'motions/v01'/job;proof=d/'verification.json';visual=d/'visual-review.json';aid='dots_'+job.replace('-','_')+'_motion_v01'
  status=dict(job=job,technical_proof=proof.exists(),ai_visual_review=False,registered=False)
  if proof.exists() and visual.exists():
   data=json.loads(proof.read_text(encoding='utf-8'));review=json.loads(visual.read_text(encoding='utf-8'))
   status['ai_visual_review']=review['status']=='visual_review_passed'
   if status['ai_visual_review'] and not any(a['asset_id']==aid for a in current()['assets']):
    c=next(c for c in current()['characters'] if c['character_id']=='dots_'+item['who'])
    video=data['artifact'];derivation=d/'public-derivative.json'
    if derivation.exists():video=json.loads(derivation.read_text(encoding='utf-8'))
    apply('asset',dict(asset_id=aid,kind='generated_video',path=video['path'],sha256=video['sha256'],bytes=video['bytes'],visibility='public',privacy_review='passed',character_id=c['character_id'],character_version=c['version'],provider='minimax',generation_record=proof.relative_to(ROOT).as_posix(),generation_context='generated_for_this_revision',pose=item['pose'],visual_review_record=visual.relative_to(ROOT).as_posix(),derivation_record=derivation.relative_to(ROOT).as_posix() if derivation.exists() else None,user_approved=False),job+'_v01')
   status['registered']=any(a['asset_id']==aid for a in current()['assets'])
  states.append(status)
 result=dict(revision=current()['revision'],expected_pose_count=6,generated_count=sum(s['technical_proof'] for s in states),ai_reviewed_count=sum(s['ai_visual_review'] for s in states),assets=states,final_v03_user_approved=False,published=False)
 (OUT/'production-status-v03.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
 (OUT/'content-workspace-current.json').write_text(json.dumps(svc.get(pid),ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(result))
if __name__=='__main__':main()
