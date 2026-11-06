"""Append revision feedback and storyboards to the existing three content projects."""
import copy,json
from PIL import Image
import revise as r
from tools.studio.content_workspace import ContentWorkspace
from tools.studio.database import StudioDatabase

def main():
    db=StudioDatabase(r.ROOT/'outputs/studio/studio.sqlite3',workspace=r.ROOT,recover=False);s=ContentWorkspace(r.ROOT,db)
    for pid,keys in [('CONTENT_20261102_dots_blender_wine',['wine-short','wine-full']),('CONTENT_20261101_dots_blender_tokyo',['tokyo-full']),('CONTENT_20261101_tibo_28day_full',['tibo-full'])]:
        def apply(action,data,token):
            op='op_editorial_20261103_'+token
            with db.session() as c:
                if c.execute('SELECT 1 FROM content_project_revisions WHERE project_id=? AND operation_id=?',(pid,op)).fetchone():return
            s.apply(pid,action,dict(operation_id=op,expected_revision=s.get(pid)['project']['revision'],data=data))
        proposal_id=s.get(pid)['project']['accepted_proposal']['proposal_id']
        apply('feedback',dict(feedback_id='feedback_editorial_20261103',proposal_id=proposal_id,kind='comment',text='すでに動画はYouTube公開済だが、一旦、以下の内容を反映したバージョンを作ってみてほしい。',interpretation='字幕表示と読みの分離・文節改行・成果物拡大・縦の同位置切り替え・疑問役と意図別表情を比較版へ反映。旧版公開済みはユーザー申告で、新版の採用や公開には読み替えない。音質不良は断定しない。'),'feedback')
        for key in keys:
            cfg=r.CASES[key];plan=json.loads((r.OUT/'release'/cfg['version']/key/'timeline.json').read_text(encoding='utf-8'));project=s.get(pid)['project'];eid=cfg['kind'] if pid!='CONTENT_20261101_tibo_28day_full' else project['episodes'][0]['episode_id'];ep=next(e for e in project['episodes'] if e['episode_id']==eid);prior=ep.get('storyboard',[]);byid={t['scene_id']:t for t in prior};fallback=prior[0]
            frame=r.OUT/'release'/cfg['version']/key/'qc-actual'/('s04-middle.jpg' if key=='wine-short' else 'f11-middle.jpg' if key in ['wine-full','tokyo-full'] else '05-03-middle.jpg');im=Image.open(frame);aid='asset_editorial_'+key.replace('-','_')
            apply('asset',dict(asset_id=aid,kind='original',path=frame.relative_to(r.ROOT).as_posix(),bytes=frame.stat().st_size,sha256=r.sha(frame),width=im.width,height=im.height,visibility='public',privacy_review='passed',blog_usage_review='passed',description='改訂した完成MP4の実フレーム。原資料は旧版と共用。ブログのブランド人物バナーへの転用を意味しない。'),key+'_asset')
            scenes=[]
            for t in plan['turns']:
                old=byid.get(t['id'],next((x for x in prior if x.get('narration')==t['text']),fallback))
                scenes.append(dict(scene_id='editorial_'+t['id'].replace('-','_'),purpose=t.get('heading',t.get('caption','字幕と構図の改訂')),narration=t['text'],visual=t['visual']+' / 表示原稿は別管理・文節字幕・成果物優先・意図別PIP',duration_seconds=t['end']-t['start'],source_ids=old.get('source_ids',[]),claim_ids=old.get('claim_ids',[]),asset_ids=list(dict.fromkeys(old.get('asset_ids',[])+[aid])),character_ids=old.get('character_ids',[]),beat=old.get('beat','evidence')))
            endframe=r.OUT/'release'/cfg['version']/key/'qc-actual/ending.jpg';im=Image.open(endframe);end_id=aid+'_ending'
            apply('asset',dict(asset_id=end_id,kind='original',path=endframe.relative_to(r.ROOT).as_posix(),bytes=endframe.stat().st_size,sha256=r.sha(endframe),width=im.width,height=im.height,visibility='public',privacy_review='passed',blog_usage_review='passed',description='改訂MP4から取得した実際の終了フレーム'),key+'_ending_asset')
            ending_seconds=plan['seconds']-plan['turns'][-1]['end'];scenes.append(dict(scene_id='editorial_ending',purpose='元版から保持した終了画面',narration='発話なし。BGMのみ。',visual='末尾の余韻と関連動画・登録用領域',duration_seconds=ending_seconds,source_ids=[],claim_ids=[],asset_ids=[end_id],character_ids=[],beat='transition'))
            apply('storyboard',dict(episode_id=eid,scenes=scenes),key+'_storyboard')
        current=s.get(pid);r.save(r.OUT/'workspace-records'/f'{pid}.json',current);print(pid,current['project']['revision'],json.dumps(current['checks'],ensure_ascii=False),flush=True)
if __name__=='__main__':main()
