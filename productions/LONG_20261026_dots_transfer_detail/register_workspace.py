"""Record the explicitly requested long-form continuation in ContentWorkspace."""
from pathlib import Path
from copy import deepcopy
import json,sys

ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
OUT=ROOT/'outputs/productions'/HERE.name/'v01';ID='CONTENT_20261026_dots_transfer_detail'
sys.path.insert(0,str(ROOT))
from tools.studio.content_workspace import ContentWorkspace
from tools.studio.database import StudioDatabase


def main():
    service=ContentWorkspace(ROOT,StudioDatabase(ROOT/'outputs/studio/studio.sqlite3',workspace=ROOT,recover=False))
    def p():return service.get(ID)['project']
    def apply(action,data,op):
        body=dict(operation_id=op,expected_revision=p()['revision'],data=data)
        target=OUT/'workspace-inputs';target.mkdir(exist_ok=True)
        (target/(op+'.json')).write_text(json.dumps(body,ensure_ascii=False,indent=2),encoding='utf-8')
        return service.apply(ID,action,body)
    def asset(aid,kind,path,**extra):
        if any(a['asset_id']==aid for a in p()['assets']):return
        apply('asset',dict(asset_id=aid,kind=kind,path=path,visibility='public' if kind.endswith('capture') else 'private',
             privacy_review='passed',**extra),'long_asset_'+aid)
    if ID not in {x['content_project_id'] for x in service.list()['items']}:
        service.create(dict(content_project_id=ID,operation_id='longform_transfer_create_v01',
            title='dotsのExcelからWebシステムへの自動転記 詳細実演',topic='既存Shorts③を、添付の台本と音声原稿に基づく横長の詳細動画へ展開。BGM・ナレーション・記事素材を同時制作。',
            audience='仕事の転記をAIに任せたい人。入力手順と人の確認場所を具体的に見たい人。',format='longform_16_9'))
    if not p()['research']:
        apply('research',dict(research_id='transfer_detail_research_v01',checked_at='2026-10-26',
            summary='公式のクラウドPC説明を再確認し、実機で開いて表示・保存を確認。実物XLSX、架空フォーム、元表と保存結果を照合。前回は静止画のみのため、今回は独立コピーでGUI録画した。',
            sources=[dict(source_id='computers',title='Connect computers and apps to your dot',kind='official',checked_at='2026-10-26',url='https://learn.chatgpt.com/docs/dots/computers-and-apps')]),'long_research_v01')
    if not p()['proposals']:
        apply('proposal',dict(proposal_id='transfer_detail_proposal_v01',count_reason='ユーザーがShorts③の詳細動画1本を明示指定。約4分40秒の台本を、11章・45カットで1本へ構成する。',
            episodes=[dict(episode_id='transfer_detail_01',title=(HERE/'youtube-title.txt').read_text(encoding='utf-8').strip(),duration_seconds=280,
                overview='完成結果から、対象の限定・本人確認・入力・登録・保存後照合までを既存男女の掛け合いで伝える。',
                intended_message='繰り返し入力はdotsへ。人は登録対象と保存先を決め、登録前と保存後に確認する。',
                demo_idea='専用XLSXビューアと撮影用案件管理フォームで架空3件をGUI転記し、全15項目を照合する。',
                article_role='元15項目・依頼文の骨格・実画面・権限と実運用条件を詳述し、動画からの詳細な参照先を準備する。')]),'long_proposal_v01')
    if not p()['feedback']:
        apply('feedback',dict(feedback_id='transfer_detail_user_request',proposal_id='transfer_detail_proposal_v01',kind='acceptance',
            text='3のエクセルからシステム自動転記の詳細動画を作ってみたい。YouTubeのフルサイズ動画を想定。bgmとナレーションもお願いします。',
            interpretation='添付台本の詳細動画を制作する実行依頼。既存dotsの男女を継続し、登録前確認は本人の実返答を別途取得した。完成物の最終採用と公開の許可ではない。'),'long_feedback_v01')
    if not p()['accepted_proposal']:
        apply('accept',dict(proposal_id='transfer_detail_proposal_v01',feedback_id='transfer_detail_user_request',confirm_acceptance=True),'long_accept_v01')
    parent=service.get('CONTENT_20261025_dots_shared_desktop_pilot')['project']
    for gender in ('male','female'):
        cid='dots_pilot_'+gender
        character=deepcopy(next(c for c in parent['characters'] if c['character_id']==cid))
        reference=next(a for a in parent['assets'] if a['asset_id']==character['reference_asset_id'])
        asset(reference['asset_id'],'generated_still',reference['path'],caption='既存dots編からの人物参照。新規人物生成なし。')
        if not any(c['character_id']==cid for c in p()['characters']):
            old_approval=character.pop('approval');character.pop('version',None);character.pop('reference_sha256',None)
            apply('character',character,'long_character_'+gender)
            apply('approve-character',dict(character_id=cid,version=1,confirm_acceptance=True,user_response=old_approval['user_response'],
                scope='既存dots男女の外見と役割を継続する範囲だけ。今回の男性声Charonと完成動画は最終採用未確認。'),'long_character_continue_'+gender)
        motion=next(a for a in parent['assets'] if a['asset_id']==cid+'_motion')
        asset(cid+'_motion','generated_video',motion['path'],character_id=cid,character_version=1,
              provider='minimax',generation_record=motion['generation_record'],caption='既存MiniMax動画を消音で短く使用。ループや無断のフリーズ延長なし。')
    manifest=json.loads((OUT/'blog-handoff/v01/asset-manifest.json').read_text(encoding='utf-8'))
    aids=[]
    for item in manifest['assets']:
        name=Path(item['artifact']['path']).stem.replace('-','_');aid='transfer_'+name
        kind='demonstration_capture' if item['origin']=='demonstration_capture' else 'official_capture' if item['origin']=='official_quote' else 'original'
        extra=dict(caption=item['purpose'],user_approved_for_blog=False)
        if kind=='demonstration_capture':extra['fictional_materials_only']=True
        if kind=='official_capture':extra.update(source_url=manifest['official_source'],source_checked_at='2026-10-26')
        asset(aid,kind,item['artifact']['path'],**extra);aids.append(aid)
    if p()['episodes'][0]['capture_plan']['status']!='captured':
        apply('capture',dict(episode_id='transfer_detail_01',inspection_id='transfer_detail_live_v01',status='captured',checked_at='2026-10-26',
            app='ChromeからdotsクラウドPCのChromiumを表示',login_state='既存のログイン済み環境。新たな認証なし。',feature_entry='dotsプロフィールのコンピューターを開く。',
            route='ユーザーPCのChromeでクラウドPC表示・原本保存を実施後、独立した8766コピーで実GUIを連続収録しZIP受領。',
            result='本人の実承認後に3件を登録。根拠234ファイルのSHA256一致。全8本decode成功、実XLSXと保存JSONの15項目も受領側で一致確認。',
            display_result='実入力・確認・登録・再表示・拒否試験を取得。本人承認は制作チャットで取得し、転送であることを記録。',
            save_result='独立したoutputs/productions/LONG_20261026_dots_transfer_detail/v01/cloudに保存。旧デモ不変。',
            legibility='原録画1188x760、30fps。1400px目安には不足。詳細切り出しと編集図を併用し、元解像度を水増ししない。',
            shots=[dict(shot_id='transfer_source',purpose='実XLSXの3行',asset_id='transfer_source_table'),dict(shot_id='transfer_saved',purpose='保存後の3件と金額',asset_id='transfer_saved_list')]),'long_capture_v01')
    if not p()['episodes'][0]['storyboard']:
        plan=json.loads((OUT/'timeline.json').read_text(encoding='utf-8'))
        scenes=[]
        for i,c in enumerate(plan['chapters']):
            row=dict(scene_id=c['id'],purpose=c['title'],narration=' '.join(t['text'] for t in c['turns']),duration_seconds=c['end']-c['start'],
                visual='新規GUI録画と編集図。静止説明・操作省略は明示。' if i not in (0,10) else '完成物の実画面、既存人物動画を全面で使用し顔と字幕を分離。',
                beat='evidence' if i==0 else 'try' if i<7 else 'insight' if i<10 else 'action',
                asset_ids=['transfer_source_table','transfer_saved_list'],source_ids=['computers'],claim_ids=[],character_ids=[])
            if i in (0,10):row.update(character_ids=['dots_pilot_male','dots_pilot_female'],
                character_action='男性は疑問と照合を担い、女性は手順を案内。短い既存の身ぶりを使い、実操作担当者を撮影した人物とは扱わない。',
                presenter_layout='fullscreen',face_caption_separated=True,asset_ids=row['asset_ids']+['dots_pilot_male_motion','dots_pilot_female_motion'])
            scenes.append(row)
        apply('storyboard',dict(episode_id='transfer_detail_01',scenes=scenes),'long_storyboard_v01')
    if not p()['article'].get('draft_path'):
        apply('article',dict(title='Excelからシステムへの転記をdotsに任せる',slug='dots-excel-system-transfer-detail',publication_target='blog',
            draft_path=(HERE/'article-draft-v01.md').relative_to(ROOT).as_posix(),sections=[dict(section_id='transfer_detail_article',title='依頼・本人確認・入力・登録後照合',
                episode_ids=['transfer_detail_01'],asset_ids=aids,claim_ids=[],character_ids=[],source_ids=['computers'])]),'long_article_v01')
    state=service.get(ID)
    (OUT/'workspace-state-v01.json').write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
    print('ContentWorkspace revision',state['project']['revision'],state['checks'])


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');main()
