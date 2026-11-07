"""Register the directly requested v03 edit and verified review candidates."""
import json

from produce import CASE, ROOT, OUT, hash_file, save
from rank_volume import AS_OF, POPULATIONS, RANKS, TITLES
from record_workspace import PROJECT, load, relative, operation_writer
from visuals import PEOPLE
from tools.studio.content_workspace import ContentWorkspace
from tools.studio.database import StudioDatabase

RECORDS = OUT/'_private/workspace/production-v03'
REPLY = """まぁまぁよいのですが、以下を改善しましょう
独自の点数化をやめて漏洩件数のみで順位評価
それに漏れた内容を詳しく解説
KDDIは外して
次に、インパクトが伝わらないので、演出を強めにしつつ、例えば漏洩件数は〇〇市の人口希望とか、分かりやすい例を示しましょう。"""
SCOPE = '公表件数降順、KDDI除外、情報項目の詳説、人口規模の比較と強い画面演出。最新版のレビュー・採用・公開は別。'
PROPOSAL = 'proposal_japan_breaches_v03'


def verified_media(kind):
    folder = OUT/'release/v03'/kind
    qc = load(folder/'qc.json')
    movie = folder/qc['file']
    assert qc['full_decode'] and hash_file(movie)==qc['sha256']
    return movie,qc,load(folder/'timeline.json')


def record():
    service = ContentWorkspace(ROOT,StudioDatabase(ROOT/'outputs/studio/studio.sqlite3',workspace=ROOT,recover=False))
    apply = operation_writer(service,RECORDS,'production_v03')
    apply('feedback','revision-request',dict(feedback_id='request_volume_v03',
        proposal_id='proposal_japan_breaches_v02',text=REPLY,interpretation=SCOPE,kind='revision_request'))
    stats = [
        dict(source_id='population-'+key,url=value['url'],title=value['source'],checked_at=AS_OF,kind='official')
        for key,value in POPULATIONS.items()
    ]
    daiichi = dict(source_id='daiichi-first-resolved',
        url='https://www.dkkaraoke.co.jp/news/newsletter/261008_2.html',
        title='第一興商の初報・対象区分の表',checked_at=AS_OF,kind='official',published_at='2026-10-08')
    apply('research','population-and-daiichi',dict(research_id='research_breach_volume_v03',checked_at=AS_OF,
        summary='同一基準日の4つの人口公表値と第一興商の初報・続報を照合し、公表件数の降順へ変更。',
        sources=[*stats,daiichi],incident_ledger=relative(CASE/'ranking-volume-v03.json')))
    cases = {kind:verified_media(kind) for kind in ('full','short')}
    episodes=[]
    for kind,(_,q,_) in cases.items():
        full=kind=='full'
        episodes.append(dict(episode_id='japan-breaches-'+kind,title=TITLES[kind],
            overview='国内の10事例を件数順に、情報区分と原因を解説' if full else 'アララと佐川急便の情報区分を比較',
            intended_message='公表件数の桁と、自分の何が対象なのかを確認できるようにする。',
            duration_seconds=round(q['seconds']),
            demo_idea='公表表と人口の数値を引用し、同じ目盛りのバーと対象項目図で説明。',
            article_role='全10事例の出典・詳しい項目・対処を参照する。'))
    apply('proposal','edited-scope',dict(proposal_id=PROPOSAL,
        count_reason='ユーザーの修正指示を縦横両方へ適用。フルは10事例、ショートは2例と対処。',
        based_on_feedback=['request_volume_v03'],episodes=episodes))
    apply('feedback','scope-instruction',dict(feedback_id='scope_volume_v03',
        proposal_id=PROPOSAL,text=REPLY,kind='acceptance',
        interpretation='具体的な改訂の実行を指示した返答を新しい制作範囲に関連付けた。'+SCOPE))
    apply('accept','scope',dict(proposal_id=PROPOSAL,feedback_id='scope_volume_v03',confirm_acceptance=True))

    capture=load(OUT/'research/captures-v03/manifest.json')
    first=next(i for i in capture['entries'] if i['source_id']=='daiichi-first')
    apply('asset','daiichi-table',dict(asset_id='breach-quote-daiichi-v03',kind='official_capture',
        path=first['excerpt']['path'],sha256=first['excerpt']['sha256'],visibility='private',
        source_url=daiichi['url'],source_checked_at=AS_OF,context='初報の対象区分。映像と記事は末尾3行の派生。'))
    article=OUT/'blog-handoff/v03'
    apply('asset','population-diagram',dict(asset_id='breach-population-compare-v03',kind='original',
        path=relative(article/'assets/article-population-comparison.png'),visibility='private',
        context='人口の単位と漏えい公表の単位を分けた図。'))
    for kind,(movie,q,timeline) in cases.items():
        eid='japan-breaches-'+kind
        aid=eid+'-v03'
        apply('capture',kind+'-capture',dict(episode_id=eid,status='available',checked_at=AS_OF,
            route='PCのEdgeで公式資料を開き、Playwrightで撮影。統計局のPDFは該当ページを画像化。',
            result='第一興商の初報・続報、佐川急便、自治体の人口をPCで確認。既存の公式引用も照合。',
            app='Microsoft Edge／公式PDF',login_state='公開ページ・利用者情報なし',
            feature_entry='各社の公表ページと統計局・自治体の公式統計',
            display_result='第一興商の初報の表と調査結果、各自治体の2026年10月値を表示。',
            save_result='research/captures-v03 と article-v03/assets',
            legibility='記事の引用画像は幅1,400px以上。動画は項目に寄って表示。',
            shots=[dict(shot_id=x['source_id'],purpose='公式資料の数値と確度') for x in capture['entries']]))
        apply('asset',aid,dict(asset_id=aid,kind='original',path=relative(movie),sha256=q['sha256'],
            bytes=q['bytes'],visibility='private',qc_record=relative(movie.parent/'qc.json'),
            context='媒体を技術確認したv03のレビュー候補。'))
        scenes=[]
        for turn in timeline['turns']:
            chapter,visual=turn['chapter'],turn['visual']
            assets=[aid]
            case = RANKS.get(chapter)
            if chapter=='examples':
                case=RANKS['r02' if visual.startswith('sagawa') else 'r01']
            if chapter=='opening':
                case=RANKS['r01']
            sources=list(case['source_ids']) if case else []
            if case and 'compare' in case and visual in ('impact','rank','population','sagawa-rank'):
                sources.append('population-'+case['compare'][0])
            if chapter=='ai':
                sources=['ncsc-ai-2026']
                if visual=='ai-source':
                    assets.append('breach-quote-ncsc-ai-2026')
            if chapter=='identity':
                sources=['times-fifth','ipa-response']
                if visual=='identity-source':
                    assets.append('breach-quote-ipa-response')
            if chapter in ('actions','ending'):
                sources=['ipa-response']
            if chapter=='r10' and visual=='fields':
                sources.append('daiichi-first-resolved')
                assets.append('breach-quote-daiichi-v03')
            if visual=='evidence' and chapter in ('r01','r03','r04','r09'):
                assets.append('breach-quote-'+{'r01':'arara-third','r03':'cuenote-second',
                             'r04':'muji-second-pdf','r09':'burger-king'}[chapter])
            scene=dict(scene_id=turn['id'],purpose='件数順の改訂 '+chapter,narration=turn['text'],
                visual=visual+'／v03の実尺と画面を参照',source_ids=sources,asset_ids=assets,
                duration_seconds=(turn['end_frame']-turn['start_frame'])/timeline['fps'],
                beat=('problem' if visual=='impact' else 'insight' if chapter=='method' or visual=='arara-fields' else
                      'try' if chapter in ('opening','examples') else 'action' if chapter=='actions' else 'evidence'))
            pair = PEOPLE.get(turn.get('motion_from'),())
            if visual=='impact' and kind=='full':
                pair=('male-close-thinking',)
            if pair:
                if kind=='short':
                    pair=(pair[int(turn['speaker']=='female')],)
                assets.extend('motion-'+job for job in pair)
                scene.update(character_ids=['ai-history-toru' if job.startswith('male') else 'ai-history-rin' for job in pair],
                    presenter_layout='fullscreen',face_caption_separated=True,
                    character_action='疑問、確認、納得に合わせ、白衣版の寄りや胸上を使用。')
            scenes.append(scene)
        scenes.append(dict(scene_id='end-hold-v03',purpose='確認したことを残す',narration='BGMのみ',
            visual='関連動画・登録の余白' if kind=='full' else '対処を3点で保持',
            duration_seconds=timeline['end_hold'],beat='transition',asset_ids=[aid]))
        operation = 'short-scenes-linked' if kind=='short' else 'full-scenes'
        apply('storyboard',operation,dict(episode_id=eid,scenes=scenes))

    apply('article','article-v03',dict(slug='ai-japan-data-breaches-2026',
        draft_path=relative(CASE/'ARTICLE_DRAFT_V03_JA.md'),published=False,sections=[
            dict(section_id='ranking',title='公表件数順と人口比較',episode_ids=['japan-breaches-full'],
                 source_ids=['arara-third','sagawa-fifth',*[s['source_id'] for s in stats]],
                 asset_ids=['breach-population-compare-v03']),
            dict(section_id='data',title='10事例で対象になった情報',
                 source_ids=['arara-third','cuenote-second','muji-second-pdf','daiichi-first-resolved','daiichi-final'],
                 asset_ids=['breach-quote-arara-third','breach-quote-cuenote-second',
                            'breach-quote-muji-second-pdf','breach-quote-daiichi-v03']),
            dict(section_id='response',title='情報に応じた対処',episode_ids=['japan-breaches-short'],
                 source_ids=['ncsc-ai-2026','ipa-response','times-fifth'],asset_ids=['breach-quote-ncsc-ai-2026']),
        ]))
    final=service.get(PROJECT)
    save(RECORDS/'state.json',final)
    summary=dict(revision=final['project']['revision'],accepted_proposal=PROPOSAL,
        feedback=REPLY,scope=SCOPE,checks=final['checks'],
        assets=len(final['project']['assets']),scenes={e['episode_id']:len(e['storyboard']) for e in final['project']['episodes']},
        final_candidate_adopted=False,published=False)
    save(CASE/'workspace-production-v03.json',summary)
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':
    record()
