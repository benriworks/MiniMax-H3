"""Append the scoped Tokyo voice revision without accepting the finished video."""
import json
from PIL import Image
import revise_v03_soft_dialogue as r
from tools.studio.content_workspace import ContentWorkspace
from tools.studio.database import StudioDatabase

def main():
    pid='CONTENT_20261101_dots_blender_tokyo';db=StudioDatabase(r.ROOT/'outputs/studio/studio.sqlite3',workspace=r.ROOT,recover=False);s=ContentWorkspace(r.ROOT,db)
    def apply(action,data,token):
        op='op_tokyo_soft_v03_'+token
        with db.session() as c:
            if c.execute('SELECT 1 FROM content_project_revisions WHERE project_id=? AND operation_id=?',(pid,op)).fetchone():return
        s.apply(pid,action,dict(operation_id=op,expected_revision=s.get(pid)['project']['revision'],data=data))
    project=s.get(pid)['project'];proposal=project['accepted_proposal']['proposal_id']
    apply('feedback',dict(feedback_id='feedback_tokyo_soft_v03',proposal_id=proposal,kind='comment',text='女性キャラクターの言葉遣い、特に語尾が硬い。もう少し柔らかくしてほしい。視聴者向けにも、男性キャラクター向けにも伝わるような言葉にして。立体ではなく3D、簡略模型ではなく簡略モデル。一旦そういった視点で東京駅の動画のみ作り直して。',interpretation='東京駅full v03だけ制作。女性10台詞を同じAoedeで生成し男性5台詞は再利用。新版の最終採用・公開とはしない。'),'feedback')
    p=json.loads((r.DEST/'timeline.json').read_text(encoding='utf-8'));ep=next(x for x in s.get(pid)['project']['episodes'] if x['episode_id']=='full');old={x['scene_id'].replace('editorial_','').replace('soft_v03_',''):x for x in ep['storyboard']};scenes=[]
    for tid,filename in [('main','f11-middle.jpg'),('ending','ending.jpg')]:
        path=r.DEST/'qc-actual'/filename;im=Image.open(path);aid='asset_tokyo_soft_v03_'+tid
        apply('asset',dict(asset_id=aid,kind='original',path=path.relative_to(r.ROOT).as_posix(),bytes=path.stat().st_size,sha256=r.e.sha(path),width=im.width,height=im.height,visibility='public',privacy_review='passed',blog_usage_review='passed',description='東京駅full v03の実MP4からの確認画像。新規製品実演ではない。'),tid+'_asset')
    for t in p['turns']:
        prior=old[t['id']];scenes.append(dict(scene_id='soft_v03_'+t['id'],purpose=t['heading'],narration=t['text'],visual=t['visual']+' / 柔らかい返答と視聴者への案内・3Dと簡略モデル・v02構図継承',duration_seconds=t['end']-t['start'],source_ids=prior.get('source_ids',[]),claim_ids=prior.get('claim_ids',[]),asset_ids=list(dict.fromkeys(prior.get('asset_ids',[])+['asset_tokyo_soft_v03_main'])),character_ids=prior.get('character_ids',[]),beat=prior.get('beat','evidence')))
    scenes.append(dict(scene_id='soft_v03_ending',purpose='10秒の終了画面',narration='発話なし。BGMのみ。',visual='v02から継承した終了画面',duration_seconds=10,source_ids=[],claim_ids=[],asset_ids=['asset_tokyo_soft_v03_ending'],character_ids=[],beat='transition'))
    apply('storyboard',dict(episode_id='full',scenes=scenes),'storyboard')
    apply('article',dict(status='draft',published=False,sections=[dict(section_id='article_v03',title='dotsとBlenderで東京駅の簡略モデルを制作・修正',episode_ids=['full'],source_ids=['dots_computer','dots_controls'],asset_ids=['asset_tokyo_soft_v03_main'],draft_path=(r.HERE/'article-draft-v03.md').relative_to(r.ROOT).as_posix())]),'article')
    current=s.get(pid);r.e.save(r.DEST/'content-workspace.json',current);print(json.dumps(dict(revision=current['project']['revision'],checks=current['checks']),ensure_ascii=False))
if __name__=='__main__':main()
