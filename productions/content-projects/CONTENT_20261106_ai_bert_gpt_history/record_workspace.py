"""Record this case's actual assets and storyboards; never approve or publish."""
import json
import sys
from pathlib import Path

from produce import ROOT, HERE, OUT, REVISIONS, sha, save, dest

sys.path.insert(0, str(ROOT))
from tools.studio.database import StudioDatabase
from tools.studio.content_workspace import ContentWorkspace

PROJECT = HERE.name


def record():
    service = ContentWorkspace(ROOT, StudioDatabase(ROOT / 'outputs/studio/studio.sqlite3', workspace=ROOT, recover=False))
    operations = OUT / 'work/workspace-operations'
    def apply(action, identifier, data):
        operation = 'review_' + identifier
        receipt = operations / (operation + '-result.json')
        if receipt.exists():
            return
        state = service.get(PROJECT)
        body = dict(operation_id=operation, expected_revision=state['project']['revision'], data=data)
        save(operations / (operation + '.json'), body)
        save(receipt, service.apply(PROJECT, action, body))
    for proof_path in sorted((OUT / 'motions/v03-q2').glob('*/verification.json')):
        proof = json.loads(proof_path.read_text(encoding='utf-8'))
        who = proof['job'].split('-')[0]
        apply('asset', proof['job'], dict(asset_id='ai-history-' + proof['job'], kind='generated_video',
              path=proof['artifact']['path'], visibility='private', provider='minimax',
              character_id='ai-history-toru' if who=='male' else 'ai-history-rin', character_version=1,
              generation_record=proof_path.relative_to(ROOT).as_posix(),
              context='Native local MiniMax reaction; separate head framing in edit; not phoneme lip-sync.'))
    articles = json.loads((HERE / 'article-assets-v03.json').read_text(encoding='utf-8'))
    for asset in articles['items']:
        if not asset['asset_id'].startswith('article-'):
            continue  # Paper quote originals were registered before approval.
        apply('asset', asset['asset_id'], dict(asset_id=asset['asset_id'], kind='original',
              path=(OUT / 'article/v03' / asset['path']).relative_to(ROOT).as_posix(),
              visibility='public', privacy_review='passed', context=asset['alt']))
    sources = [s['source_id'] for s in json.loads((HERE/'sources.json').read_text(encoding='utf-8'))['sources']]
    for kind in ['short','full']:
        folder = dest(kind)
        qc = json.loads((folder/'qc.json').read_text(encoding='utf-8'))
        final = folder / ('ai-bert-gpt-history-'+kind+'-'+REVISIONS[kind]+'.mp4')
        assert sha(final)==qc['sha256'] and qc['full_decode']
        apply('asset',kind+'-candidate-'+REVISIONS[kind],dict(asset_id='ai-history-'+kind+'-'+REVISIONS[kind],
              kind='original',path=final.relative_to(ROOT).as_posix(),visibility='private',
              context='Technically verified review candidate, final user adoption and publication pending.',
              qc_record=(folder/'qc.json').relative_to(ROOT).as_posix()))
        timeline=json.loads((folder/'timeline.json').read_text(encoding='utf-8'));scenes=[]
        for index, turn in enumerate(timeline['turns']):
            people = turn['visual'] in {'hook','closing','not_chat'} or (kind=='full' and turn['id'] in {'f04','f08','f18','f33','f35'}) or (kind=='short' and turn['id']=='s05')
            scene=dict(scene_id=turn['id'],purpose='視聴者の疑問と、'+turn['visual']+'の説明',
                       narration=turn['display'],visual=turn['visual']+'／同じ実尺timeline・字幕・原本来歴を参照',
                       duration_seconds=turn['end']-turn['start'],source_ids=sources,asset_ids=[],
                       beat='problem' if index==0 else 'try' if index==1 else 'insight' if index==2 else 'action' if turn['visual'] in {'gpt','bert','example','masked'} else 'evidence')
            if people:
                scene.update(character_ids=['ai-history-toru','ai-history-rin'],presenter_layout='fullscreen',
                             face_caption_separated=True,character_action='左の透が具体的に尋ね、右の凛が応答。生成リアクションを最初の数秒に表示して図へ退避。音素同期のPIPではない。')
            scenes.append(scene)
        scenes.append(dict(scene_id='ending',purpose='本編への導線' if kind=='short' else 'YouTube終了画面用の余白',
                           narration='無発話、BGMと終了表示',visual='完成した終了表示を保持',
                           duration_seconds=timeline['ending_seconds'],beat='transition'))
        apply('storyboard',kind+'-storyboard-'+REVISIONS[kind],dict(episode_id='ai-bert-gpt-history-'+kind,scenes=scenes))
    apply('article','article-v03',dict(slug='ai-language-model-history-bert-gpt',
          draft_path=(HERE/'ARTICLE_DRAFT_V03_JA.md').relative_to(ROOT).as_posix(),published=False,
          sections=[dict(section_id='history-and-context',title='単語表現からAttentionへ',source_ids=sources,
                         asset_ids=['article-word-vectors','article-bank-context','article-self-attention','transformer-2017-paper-title-quote']),
                    dict(section_id='gpt-and-bert',title='2018年のGPTとBERT',source_ids=sources,
                         asset_ids=['article-gpt-next','article-bert-mask','gpt-2018-paper-title-quote','bert-2018-paper-title-quote']),
                    dict(section_id='comparison-and-limits',title='違い・歴史・説明の限界',source_ids=sources,
                         asset_ids=['article-transformer-branches','article-initial-gpt-vs-bert','article-history-timeline'])]))
    final=service.get(PROJECT)
    save(OUT/'work/workspace-review-v03.json',final)
    summary=dict(revision=final['project']['revision'],assets=len(final['project']['assets']),
                 characters_approved=all(c['approval'] for c in final['project']['characters']),
                 accepted_proposal=final['project']['accepted_proposal']['proposal_id'],
                 scenes={e['episode_id']:len(e['storyboard']) for e in final['project']['episodes']},
                 actual_render_seconds={k:json.loads((dest(k)/'qc.json').read_text())['seconds'] for k in ['short','full']},
                 article_draft='ARTICLE_DRAFT_V03_JA.md',publication=False,
                 note='Shared workflow registration is distinct from MP4 QC. Proposed approximate duration is preserved; actual timelines differ. Public export and publication not performed.')
    save(HERE/'workspace-review-summary-v03.json',summary)
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':
    record()
