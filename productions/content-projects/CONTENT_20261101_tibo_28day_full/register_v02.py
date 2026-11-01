"""Keep original scope/history; attach the requested ending revision and observation metadata."""
import copy,json
import register_workspace as base
from tools.studio.content_workspace import ContentWorkspace
from tools.studio.database import StudioDatabase

def main():
    base.main()
    db=StudioDatabase(base.ROOT/'outputs/studio/studio.sqlite3',workspace=base.ROOT,recover=False)
    service=ContentWorkspace(base.ROOT,db);pid=base.HERE.name
    def apply(action,data,token):
        op='op_tibo_full_v02_'+token
        with db.session() as c:
            if c.execute('SELECT 1 FROM content_project_revisions WHERE project_id=? AND operation_id=?',(pid,op)).fetchone():return
        service.apply(pid,action,dict(operation_id=op,expected_revision=service.get(pid)['project']['revision'],data=data))
    apply('feedback',dict(feedback_id='feedback_ending_v02',proposal_id='proposal_full_v01',kind='revision_request',text='内容は良い感じです。最後に少し余韻を設けて、関連動画やチャンネル登録画面を10秒程度表示できるようにして下さい。あと、途中の賞賛のキラキラをもう少し派手に綺麗な演出にして。',interpretation='v01の内容への肯定を引き継ぐ。最後10秒の音楽のみの終了画面と称賛2カットの光演出を改訂。完成v02の最終採用、YouTubeの実リンク設定・公開への許可には拡張しない。'),'feedback')
    apply('research',dict(research_id='research_end_screen_v02',checked_at='2026-11-01',summary='公式ヘルプで最後5〜20秒、16:9最大4要素、動画と登録の追加・タイミング・位置の調整を確認。今回の10秒と3要素は制作側の配置案。',sources=[dict(source_id='youtube_end_screen',url='https://support.google.com/youtube/answer/6388789?hl=ja',title='動画に終了画面を追加する',kind='official',checked_at='2026-11-01')]),'research')
    episode=service.get(pid)['project']['episodes'][0]
    revised={k:copy.deepcopy(episode[k]) for k in ['episode_id','title','overview','intended_message','demo_idea','article_role','capture_inspection_id']}
    revised['duration_seconds']=444.33333333333337
    revised['demo_idea']='公式抜粋・実画面観察・CPU図解・既存MiniMax人物を継承。称賛の光を強化し、最後10秒に関連動画2枠と登録1枠の余白を追加。実リンク設定は別。'
    apply('proposal',dict(proposal_id='proposal_full_v02_ending',based_on_feedback=['feedback_ending_v02'],count_reason='フル版1本を維持し、ユーザー指定の称賛と最後10秒だけ改訂する。',episodes=[revised]),'proposal_ending')
    apply('feedback',dict(feedback_id='feedback_ending_scope_v02',proposal_id='proposal_full_v02_ending',kind='acceptance',text='内容は良い感じです。最後に少し余韻を設けて、関連動画やチャンネル登録画面を10秒程度表示できるようにして下さい。あと、途中の賞賛のキラキラをもう少し派手に綺麗な演出にして。',interpretation='修正を実装する明示的な指示を採用範囲として記録。2枠と登録1枠の具体配置は助手の制作判断による候補で、v02完成物の最終採用ではない。'),'scope')
    apply('accept',dict(proposal_id='proposal_full_v02_ending',feedback_id='feedback_ending_scope_v02',confirm_acceptance=True),'accept_scope')
    project=service.get(pid)['project']
    inspection=copy.deepcopy(next(i for i in project['capture_inspections'] if i['inspection_id']=='inspection_full_usage'))
    inspection['episode_id']='tibo-full'
    apply('capture',inspection,'observation_after_plan')
    for name in ['09-01','09-02','end-screen']:
        path=base.OUT/'release/v02'/(name+'.mp4');proof=json.loads(path.with_suffix('.json').read_text())
        apply('asset',dict(asset_id='cut_v02_'+name.replace('-','_'),kind='original',path=proof['path'],bytes=proof['bytes'],sha256=proof['sha256'],width=1920,height=1080,visibility='public',privacy_review='passed',blog_usage_review='passed',description='ローカルで描画・編集した改訂カット。新規AI人物動画ではない。'),'asset_'+name)
    scenes=copy.deepcopy(service.get(pid)['project']['episodes'][0]['storyboard'])
    scenes=[s for s in scenes if s['scene_id']!='scene_end_screen_v02']
    for s in scenes:
        if s['scene_id'] in ['scene_09_01','scene_09_02']:
            s['asset_ids']=['cut_v02_'+s['scene_id'][6:]];s['visual']='金・白の粒子と光の帯・glow。顔と字幕を保護し、声はv01の同じPCM。'
    scenes.append(dict(scene_id='scene_end_screen_v02',purpose='最後10秒の関連動画2枠とチャンネル登録1枠',narration='発話なし。BGMのみ。',visual='YouTube Studioの要素を後から置く背景。余白と案内文、穏やかな音楽フェード。',duration_seconds=10,source_ids=['youtube_end_screen'],claim_ids=[],asset_ids=['cut_v02_end_screen'],character_ids=[],beat='transition'))
    apply('storyboard',dict(episode_id='tibo-full',scenes=scenes),'storyboard_after_plan')
    article=copy.deepcopy(service.get(pid)['project']['article']);article['status']='draft';article['published']=False
    apply('article',article,'article_after_plan')
    current=service.get(pid)
    (base.OUT/'content-workspace-v02.json').write_text(json.dumps(current,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(revision=current['project']['revision'],checks=current['checks']),ensure_ascii=False))

if __name__=='__main__':main()
