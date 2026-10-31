"""Persist this production's approved continuity and actual assets, without publishing."""
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).parent
OUT=ROOT/'outputs/content-projects'/HERE.name
sys.path.insert(0,str(ROOT))
from tools.studio.database import StudioDatabase
from tools.studio.content_workspace import ContentWorkspace

def main():
 svc=ContentWorkspace(ROOT,StudioDatabase(ROOT/'outputs/studio/studio.sqlite3',workspace=ROOT,recover=False));pid=HERE.name
 def current():return svc.get(pid)['project']
 def apply(action,data,token):
  result=svc.apply(pid,action,dict(operation_id='op_pro_news_'+token,expected_revision=current()['revision'],data=data))
  return result['project']
 response=json.loads((HERE/'approval-20261031.json').read_text(encoding='utf-8'))
 if not any(f['feedback_id']==response['feedback_id'] for f in current()['feedback']):apply('feedback',response,'acceptance_feedback')
 if not current()['accepted_proposal']:apply('accept',json.loads((HERE/'accept-20261031.json').read_text(encoding='utf-8')),'accept_v01')
 for who in ['male','female']:
  aid='dots_'+who+'_reference';cid='dots_'+who
  path=OUT/'characters'/f'{who}-reference.png'
  if not any(a['asset_id']==aid for a in current()['assets']):
   apply('asset',dict(asset_id=aid,kind='generated_still',path=path.relative_to(ROOT).as_posix(),visibility='public',privacy_review='passed',alt='既存dotsの架空の成人'+('男性' if who=='male' else '女性'),user_approved_for_blog=False,generation_record='productions/characters/motion-registry-20261022.json'),aid)
  if not any(c['character_id']==cid for c in current()['characters']):
   apply('character',dict(character_id=cid,fictional_adult=True,name='dots '+who,persona='既存シリーズの成人プログラマー。採用済み画像と衣装を継承。',role='対象条件に気づく質問役' if who=='male' else '条件を整理して確認先へ案内する解説役',clothing='既存参照画像を継承。男性は暗色パーカー、女性は明るいアイボリーと水色。',voice='Aoede単独解説。人物の独立した男性音声は今回なし。',continuity='既存dots男女を継続。新規人物生成なし。',reference_asset_id=aid),cid)
  c=next(c for c in current()['characters'] if c['character_id']==cid)
  if not c['approval']:apply('approve-character',dict(character_id=cid,version=c['version'],confirm_acceptance=True,user_response=response['text'],scope='今回の約48秒Proニュースに既存男女を継続。完成動画の採用・公開は含まない。'),cid+'_approval')
  mid='dots_'+who+'_motion'
  if not any(a['asset_id']==mid for a in current()['assets']):
   apply('asset',dict(asset_id=mid,kind='generated_video',path=(OUT/f'characters/dots-{who}-motion.mp4').relative_to(ROOT).as_posix(),visibility='public',privacy_review='passed',character_id=cid,character_version=c['version'],provider='minimax',generation_record='productions/characters/motion-registry-20261022.json',generation_context='reused_verified_minimax_clip'),mid)
 graph=OUT/'blog-handoff/v02/assets/relative-allowance.png'
 if graph.exists() and not any(a['asset_id']=='relative_allowance_chart_v02' for a in current()['assets']):
  apply('asset',dict(asset_id='relative_allowance_chart_v02',kind='original',path=graph.relative_to(ROOT).as_posix(),visibility='public',privacy_review='passed',alt='各対象プランの以前を1とする相対グラフ。Pro200の高い枠は据え置き。',user_approved_for_blog=False),'relative_chart_v02')
 if graph.exists() and current()['article'].get('draft_version')!='v02':
  apply('article',dict(title='ChatGPT ProのWork・Codex利用枠が拡大：2倍になる対象と設定の確認先',draft_version='v02',draft_path=(HERE/'article-draft-v02.md').relative_to(ROOT).as_posix(),status='common_draft_not_placed_in_blog',publication_approved=False,sections=[dict(section_id='plan_changes',title='対象別の変更と相対グラフ',episode_ids=['pro_usage_01'],asset_ids=['relative_allowance_chart_v02','official_quote']),dict(section_id='usage_settings',title='設定で確認する場所と実証の限界',episode_ids=['pro_usage_01'],asset_ids=['usage_header','plan_label'])]),'article_v02')
 (OUT/'content-workspace-current.json').write_text(json.dumps(svc.get(pid),ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(dict(revision=current()['revision'],accepted=current()['accepted_proposal'],characters=len(current()['characters']))))
if __name__=='__main__':main()
