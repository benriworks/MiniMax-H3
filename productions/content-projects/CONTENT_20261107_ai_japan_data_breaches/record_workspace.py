"""Link actual captures, scene records and private candidates to ContentWorkspace."""
import json
from pathlib import Path

from produce import CASE, ROOT, OUT, folder, hash_file, save
from visuals import PEOPLE, RANK, SCORES, PRIOR
from tools.studio.content_workspace import ContentWorkspace
from tools.studio.database import StudioDatabase

PROJECT = CASE.name
CAPTURES = OUT/'research/captures-v01'
ARTICLE = OUT/'blog-handoff/v02'
RECORDS = OUT/'_private/workspace/production-v02'
ART_SOURCE_IDS = ('arara-third','cuenote-second','muji-second-pdf','ncsc-ai-2026')
DATE = '2026-11-07'


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def relative(path):
    return Path(path).relative_to(ROOT).as_posix()


def operation_writer(service, records, prefix):
    def apply(action, identifier, data):
        operation = prefix+'_'+identifier
        request = records/(operation+'-request.json')
        result = records/(operation+'-receipt.json')
        if result.exists():
            return
        if request.exists():
            body = load(request)
            if body['data'] != data:
                raise RuntimeError('Workspace request changed after submission: '+identifier)
        else:
            body = dict(operation_id=operation,expected_revision=service.get(PROJECT)['project']['revision'],data=data)
            save(request,body)
        save(result,service.apply(PROJECT,action,body))
    return apply


def record():
    service = ContentWorkspace(ROOT, StudioDatabase(ROOT/'outputs/studio/studio.sqlite3',workspace=ROOT,recover=False))
    apply = operation_writer(service,RECORDS,'production_v02')
    raw = load(CAPTURES/'capture-manifest.json')
    supplements = load(CAPTURES/'selected-excerpts-v02.json')
    known_sources = {s['source_id'] for entry in service.get(PROJECT)['project']['research'] for s in entry['sources']}
    incident = {item['incident_id']:item for item in load(CASE/'incidents-v01.json')['incidents']}
    notes = {item['source_id']:item for item in raw['captures'] if 'excerpt' in item}
    notes.update({item['source_id']:item for item in supplements['items']})
    uses = {'arara-third','cuenote-second','muji-second-pdf','ncsc-ai-2026',
            'burger-king','kddi-isp','epark-second','ipa-response'}
    quote_assets = {}
    for source_id in sorted(uses):
        note = notes[source_id]
        asset_id = 'breach-quote-'+source_id
        quote_assets[source_id] = asset_id
        apply('asset',asset_id,dict(asset_id=asset_id,kind='official_capture',
            path=note['excerpt']['path'],sha256=note['excerpt']['sha256'],visibility='private',
            source_url=note['url'],source_checked_at=DATE,
            context='説明に必要な範囲の公式資料。Edgeの画面切り出しまたは公式PDFの画像化。レビュー用。'))
    apply('asset','article-decision-diagram',dict(asset_id='article-decision-diagram',
        kind='original',path=relative(ARTICLE/'assets/article-what-to-check.png'),visibility='private',
        context='IPAと日本クレジット協会の案内から対象別の対処を図示。'))

    registry = load(ROOT/'productions/characters/ai-history-guides-20261106/characters.json')
    character_by_role = {}
    for character in registry['characters']:
        cid = character['character_id']
        role = 'male' if cid.endswith('toru') else 'female'
        character_by_role[role] = cid
        ref = cid+'-white-reference'
        apply('asset',ref,dict(asset_id=ref,kind='generated_still',path=character['input_derivative'],
                               sha256=character['input_sha256'],visibility='private',
                               context='前作で採用された白衣v02の派生参照。'))
        apply('character',cid,dict(character_id=cid,fictional_adult=True,name=character['name'],
            persona=f"{character['age']}歳の架空の開発者・AIエンジニア",role=character['role'],
            clothing='前作の白衣v02',voice=character['voice_used'],
            continuity='2026-11-06の【AI】BERT・GPT誕生史から継承',
            reference_asset_id=ref))
        apply('approve-character',cid+'-prior-approval',dict(character_id=cid,version=1,confirm_acceptance=True,
            user_response=character['approved_by'],
            scope='2026-11-06の同一白衣v02の採用記録を転記。顔・衣装・役割の継承。今回の完成品採用とは別。'))

    provenance = {m['job']:m for m in load(PRIOR/'motion-provenance-v01.json')}
    provenance.update({m['job']:m for m in load(PRIOR/'motion-provenance-v04.json')})
    jobs = sorted({job for pair in PEOPLE.values() for job in pair})
    for job in jobs:
        row = provenance[job]
        role = job.split('-')[0]
        apply('asset','motion-'+job,dict(asset_id='motion-'+job,kind='generated_video',provider='minimax',
             path=row.get('path',row.get('source')),sha256=row['sha256'],visibility='private',
             character_id=character_by_role[role],character_version=1,
             generation_record=row.get('proof',relative(PRIOR/'motion-provenance-v04.json')),
             context='前作の同一人物のローカルMiniMax動画。胸上と顔の切り出しを使用。'))

    for kind in ('full','short'):
        episode = 'japan-breaches-'+kind
        apply('capture',kind+'-capture',dict(episode_id=episode,status='available',checked_at=DATE,
            route='PCのMicrosoft EdgeをPlaywrightで開き、公式発表へ直接移動。PDFは原資料の該当ページを描画。',
            result='公式発表の画面と原資料の切り出しを保存。事件の再現を伴わない説明。',
            app='Microsoft Edge／公式PDF',login_state='公開ページ。利用者アカウントなし。',
            feature_entry='事業者・公的機関のニュース・年次報告・利用者向け案内。',
            display_result='公式HTMLの本文と公式PDFを照合。Cuenoteは該当表を再撮影した。',
            save_result='research/captures-v01の原本、article-v02/assetsの引用候補。',
            legibility='記事用は幅1400px以上。縦・横の該当画面は別の切り出し。',
            shots=[dict(shot_id='source-'+sid,purpose='公式の範囲・数量と確認条件') for sid in sorted(uses)]))
        directory = folder(kind)
        q = load(directory/'qc.json')
        movie = directory/q['file']
        assert q['full_decode'] and hash_file(movie)==q['sha256']
        movie_id = episode+'-v02'
        apply('asset',movie_id,dict(asset_id=movie_id,kind='original',path=relative(movie),
            sha256=q['sha256'],bytes=q['bytes'],visibility='private',qc_record=relative(directory/'qc.json'),
            context='技術確認済みのレビュー候補。'))
        timeline = load(directory/'timeline.json')
        scenes = []
        for turn in timeline['turns']:
            chapter, tid = turn['chapter'],turn['id']
            key = ('r01' if tid=='s03' else 'r03') if chapter=='examples' else chapter
            asset_ids = [movie_id]
            if key in RANK:
                item = incident[SCORES[int(key[1:])]['incident_id']]
                sids = item['source_ids']
                quote = RANK[key][-1]
                if quote=='cuenote-second-v02':
                    quote = 'cuenote-second'
                if quote and (turn['visual']=='evidence' or kind=='short' or tid=='f28'):
                    asset_ids.append(quote_assets[quote])
            elif chapter=='ai':
                sids = ['ncsc-ai-2026']
                if turn['visual']=='ai-source':
                    asset_ids.append(quote_assets['ncsc-ai-2026'])
            elif chapter=='identity':
                sids = ['times-fifth','ipa-response']
                if turn['visual']=='identity-source':
                    asset_ids.append(quote_assets['ipa-response'])
            elif chapter in ('actions','ending','opening'):
                sids = ['ipa-response']
            else:
                sids = []
            if not set(sids)<=known_sources:
                raise ValueError(f'Unknown source ids {set(sids)-known_sources}')
            role = 'problem' if tid in ('f01','s01') else 'try' if tid in ('f02','s02') else (
                   'insight' if chapter in ('method','examples') else 'action' if chapter=='actions' else 'evidence')
            scene = dict(scene_id=tid,purpose='採用企画の'+chapter+'に対応する'+turn['visual'],
                narration=turn['text'],visual=turn['visual']+'／人物・図・公式引用の実尺はtimeline参照',
                duration_seconds=(turn['end_frame']-turn['start_frame'])/24,beat=role,
                source_ids=sids,asset_ids=asset_ids)
            if tid in PEOPLE:
                pair = PEOPLE[tid]
                if tid in ('f01','s01'):
                    pair = pair[:1]
                elif kind=='short':
                    pair = (pair[int(turn['speaker']=='female')],)
                asset_ids.extend('motion-'+job for job in pair)
                scene.update(character_ids=[character_by_role[job.split('-')[0]] for job in pair],
                    presenter_layout='fullscreen',face_caption_separated=True,
                    character_action='質問・確認・納得の動きを会話の役割に割り当て、数値・引用が主役の場面で退避する。')
            scenes.append(scene)
        scenes.append(dict(scene_id='end-hold',purpose='確認したことを残す',narration='BGMのみ',
            visual='関連動画と登録用の余白' if kind=='full' else '対処3点を保持',
            duration_seconds=timeline['end_hold'],beat='transition',asset_ids=[movie_id]))
        storyboard_op = 'full-storyboard-linked-v02' if kind=='full' else 'short-storyboard'
        apply('storyboard',storyboard_op,dict(episode_id=episode,scenes=scenes))

    apply('article','article-v02',dict(slug='ai-japan-data-breaches-2026',
        draft_path=relative(CASE/'ARTICLE_DRAFT_V02_JA.md'),published=False,
        sections=[
            dict(section_id='ranking',title='10事例と公表範囲',episode_ids=['japan-breaches-full'],
                 source_ids=list(ART_SOURCE_IDS[:3]),asset_ids=[quote_assets[s] for s in ART_SOURCE_IDS[:3]]),
            dict(section_id='background',title='AIが速める作業と個別事件の原因',source_ids=['ncsc-ai-2026'],
                 asset_ids=[quote_assets['ncsc-ai-2026']]),
            dict(section_id='response',title='情報に応じた対処',source_ids=['ipa-response','times-fifth'],
                 episode_ids=['japan-breaches-short'],asset_ids=['article-decision-diagram']),
        ]))
    final = service.get(PROJECT)
    save(RECORDS/'state.json',final)
    summary = dict(revision=final['project']['revision'],phase=final['project']['phase'],
        accepted_proposal=final['project']['accepted_proposal']['proposal_id'],
        assets=len(final['project']['assets']),
        scenes={e['episode_id']:len(e['storyboard']) for e in final['project']['episodes']},
        workspace_checks=final['checks'],render_qc_separate=True,adopted_release=False,published=False)
    save(CASE/'workspace-production-v02.json',summary)
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':
    record()
