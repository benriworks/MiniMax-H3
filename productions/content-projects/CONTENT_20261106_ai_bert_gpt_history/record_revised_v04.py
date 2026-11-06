"""Persist the editorial rebuild without changing the accepted identity/outline."""
import json,sys
from produce_v04 import ROOT,HERE,OUT,old,shots
from tools.studio.database import StudioDatabase
from tools.studio.content_workspace import ContentWorkspace


def record():
    service=ContentWorkspace(ROOT,StudioDatabase(ROOT/'outputs/studio/studio.sqlite3',workspace=ROOT,recover=False))
    ops=OUT/'work/workspace-editorial-v04'
    def apply(action,key,data):
        receipt=ops/(key+'-result.json')
        if receipt.exists():return
        state=service.get(HERE.name)
        body=dict(operation_id='editorial_'+key,expected_revision=state['project']['revision'],data=data)
        old.save(ops/(key+'.json'),body);old.save(receipt,service.apply(HERE.name,action,body))
    for p in (OUT/'motions/v04-closeups').glob('*/verification.json'):
        proof=json.loads(p.read_text(encoding='utf-8'));who=proof['job'].split('-')[0]
        apply('asset',proof['job'],dict(asset_id='ai-history-'+proof['job'],kind='generated_video',visibility='private',
              path=proof['artifact']['path'],provider='minimax',character_id='ai-history-toru' if who=='male' else 'ai-history-rin',
              character_version=1,generation_record=p.relative_to(ROOT).as_posix(),
              context='Same accepted white-coat identity, new chest-up pose derivative; native video, not lip sync. Bottom generated letters excluded by a separate edit crop.'))
    articles=json.loads((HERE/'article-assets-v04.json').read_text(encoding='utf-8'))['items']
    for a in articles:
        aid=a['asset_id']+'-v04'
        apply('asset',aid,dict(asset_id=aid,kind='original',visibility='public',privacy_review='passed',
              path=(OUT/'article/v04'/a['path']).relative_to(ROOT).as_posix(),context=a.get('caption',a['alt']),
              source_url=a.get('source_url'),original_url=a.get('original_url')))
    source_ids=[x['source_id'] for x in json.loads((HERE/'sources.json').read_text(encoding='utf-8'))['sources']]
    for kind in ['short','full']:
        version=old.REVISIONS[kind];folder=old.dest(kind);qc=json.loads((folder/'qc.json').read_text(encoding='utf-8'))
        final=folder/('ai-bert-gpt-history-'+kind+'-'+version+'.mp4');assert old.sha(final)==qc['sha256'] and qc['full_decode']
        aid='ai-history-'+kind+'-'+version
        apply('asset',kind+'-'+version,dict(asset_id=aid,kind='original',visibility='private',path=final.relative_to(ROOT).as_posix(),
              qc_record=(folder/'qc.json').relative_to(ROOT).as_posix(),context='Editorial rebuild review candidate; previous user-rejected versions preserved. Final user adoption/publication pending.'))
        timeline=json.loads((folder/'timeline.json').read_text(encoding='utf-8'));scenes=[]
        for t in timeline['turns']:
            schedule=shots(t,kind)
            for i,(at,visual) in enumerate(schedule):
                end=schedule[i+1][0] if i+1<len(schedule) else t['end']-t['start']
                scene=dict(scene_id=t['id']+'-'+str(i),purpose='今回の疑問・具体例・根拠を'+visual+'で示す',
                    narration=t['display'] if i==0 else '同じ台詞の継続：'+t['id'],visual=visual,
                    duration_seconds=end-at,source_ids=source_ids,asset_ids=[aid],beat='problem' if t['id'] in {'s01','f01'} else 'try' if t['id'] in {'s02','f02'} else 'insight' if t['id'] in {'s10','f33'} else 'action')
                if visual.startswith(('male_','female_')) or visual=='duo':
                    who='male' if visual.startswith('male_') else 'female';people=['male','female'] if visual=='duo' else [who]
                    scene['character_ids']=['ai-history-toru' if w=='male' else 'ai-history-rin' for w in people]
                    scene.update(presenter_layout='fullscreen',face_caption_separated=True,character_action='顔アップ・胸上・対話を意味に合わせる。原図や比較では人物を退避。生成された動きで、音素同期ではない。')
                    for w in people:
                        if visual.endswith('medium'):
                            pose=('thinking' if w=='male' else 'enjoyment') if kind=='short' else {'f05':'enjoyment','f08':'frustration','f10':'sadness','f18':'frustration','f33':'joy'}.get(t['id'],t['emotion'])
                            if pose not in {'joy','frustration','sadness','enjoyment','thinking'}:pose='thinking' if w=='male' else 'enjoyment'
                            scene['asset_ids'].append('ai-history-'+w+'-'+pose)
                        else:scene['asset_ids'].append('ai-history-'+w+'-close-'+('thinking' if w=='male' else 'insight'))
                if visual=='tasks':
                    scene['native_presenter_inset']='Female local video inset alongside task diagrams; shared audio-envelope PIP gate is not used or claimed.'
                    scene['asset_ids'].append('ai-history-female-close-insight')
                scenes.append(scene)
        scenes.append(dict(scene_id='ending',purpose='終了表示を保持',narration='無発話、BGMのみ',visual='終了表示',duration_seconds=timeline['ending_seconds'],asset_ids=[aid],beat='transition'))
        apply('storyboard',kind+'-'+version+'-scenes',dict(episode_id='ai-bert-gpt-history-'+kind,scenes=scenes))
    apply('article','article-v04',dict(slug='ai-language-model-history-bert-gpt',published=False,draft_path=(HERE/'ARTICLE_DRAFT_V04_JA.md').relative_to(ROOT).as_posix(),
          sections=[dict(section_id='history-context',title='言葉の表現と文脈・Attention',source_ids=source_ids,asset_ids=[x['asset_id']+'-v04' for x in articles[:3]]),
                    dict(section_id='gpt-bert',title='初代GPTとBERT・公式原図',source_ids=source_ids,asset_ids=[x['asset_id']+'-v04' for x in articles[3:]] )]))
    final=service.get(HERE.name);old.save(OUT/'work/workspace-editorial-v04-final.json',final)
    summary=dict(revision=final['project']['revision'],assets=len(final['project']['assets']),accepted_proposal=final['project']['accepted_proposal']['proposal_id'],
                 scenes={e['episode_id']:len(e['storyboard']) for e in final['project']['episodes']},checks=final['checks'],
                 note='Decoded-media QC is separate. Approximate planned durations are retained. User rejected old visual editing; new candidates await adoption.')
    old.save(HERE/'workspace-editorial-summary-v04.json',summary);print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    record()
