"""Register reviewed pilot assets and measured storyboards in the common CLI store."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
OUT = ROOT / 'outputs/content-projects' / HERE.name
sys.path.insert(0, str(ROOT))
from tools.studio.content_workspace import ContentWorkspace
from tools.studio.database import StudioDatabase
from tools.studio.shorts_creator import allocate_scenes, read
from produce import save


def register():
    service = ContentWorkspace(ROOT, StudioDatabase(ROOT / 'outputs/studio/studio.sqlite3', workspace=ROOT, recover=False))
    def project():
        return service.get(HERE.name)['project']
    def apply(action, data, operation):
        body = dict(operation_id=operation, expected_revision=project()['revision'], data=data)
        save(OUT / 'inputs' / (operation + '.json'), body)
        return service.apply(HERE.name, action, body)
    def asset(aid, kind, path, **extra):
        if any(a['asset_id'] == aid for a in project()['assets']):
            return
        apply('asset', dict(asset_id=aid, kind=kind, path=path, visibility='public' if kind.endswith('capture') else 'private',
            privacy_review='passed', **extra), 'register_' + aid.replace('-', '_'))
    registry = read(ROOT / 'productions/characters/motion-registry-20261022.json')['clips']
    for role in ('male', 'female'):
        cid = 'dots_pilot_' + role
        item = registry['dots-' + role]
        reference = cid + '_reference'
        asset(reference, 'generated_still', item['source_presenter']['path'], caption='既存dots人物の継続参照。新しい人物の生成ではない。')
        if not any(c['character_id'] == cid for c in project()['characters']):
            apply('character', dict(character_id=cid, fictional_adult=True,
                name='既存dots案内役・' + ('男性' if role == 'male' else '女性'),
                persona='架空の成人プログラマー。作業を自分でも確かめ、小さな気づきを次の行動へつなげる。',
                role='実演を見た気づきと、次に確認する点を短く伝える。',
                clothing='濃いグレーのパーカーと青いインナー' if role == 'male' else 'アイボリーのパーカーと水色のインナー',
                voice='Aoedeによる外部ナレーション。人物クリップは消音。',
                continuity='dots第1回からの既存男女の外見を継続。シリーズ共通の参照とMiniMax動画を再利用。',
                reference_asset_id=reference), 'pilot_character_' + role + '_v01')
        character = next(c for c in project()['characters'] if c['character_id'] == cid)
        if not character.get('approval'):
            apply('approve-character', dict(character_id=cid, version=character['version'], confirm_acceptance=True,
                user_response='dotsの5回目以降は、過去の第1回目からの二人のキャラクターで作り直して下さい。',
                scope='会話履歴にある既存二人の継続指定と今回v02の制作採用に基づく外見・役割の継続。新しい完成クリップの最終採用ではない。'),
                'pilot_continue_character_' + role + '_v01')
        asset(cid + '_motion', 'generated_video', item['video']['path'], character_id=cid,
            character_version=character['version'], provider='minimax', generation_record=item['proof']['path'],
            caption='既存MiniMax H3動画。今回の新規生成はゼロ。技術・AI画面確認済み、人の最終試聴と完成動画の採用は別。')

    episode_ids = ['dots_desktop_handoff_01', 'dots_desktop_blender_02', 'dots_desktop_entry_03']
    for episode_number, eid in enumerate(episode_ids, 1):
        story = read(HERE / f'{episode_number:02d}/creator-story-v01.json')
        shots, scene_assets = [], []
        for index, scene in enumerate(story['scenes']):
            aid = f'pilot_{episode_number:02d}_scene_{index:02d}'
            if scene.get('capture'):
                capture = scene['capture']
                asset(aid, 'demonstration_capture', capture['path'], fictional_materials_only=True,
                    caption='実際のクラウドPC静止画。編集で切り替える素材。', capture_proof=capture['proof'],
                    user_approved_for_blog=False)
                shots.append(dict(shot_id=aid, purpose=scene['headline'].replace('\n', '・'), asset_id=aid))
                scene_assets.append([aid])
            elif index == len(story['scenes']) - 1:
                scene_assets.append(['dots_pilot_' + ('female' if episode_number == 2 else 'male') + '_motion'])
            else:
                path = scene['media']['path'] if scene.get('media') else (HERE / f'{episode_number:02d}/creator-story-v01.json').relative_to(ROOT).as_posix()
                asset(aid, 'original', path, caption='Blenderレンダーから編集した比較映像。GUI録画ではない。' if scene.get('media') else '共通図解の構成定義。')
                scene_assets.append([aid])
        current = next(e for e in project()['episodes'] if e['episode_id'] == eid)
        if current['capture_plan']['status'] != 'captured':
            apply('capture', dict(episode_id=eid, inspection_id=f'pilot_capture_{episode_number:02d}_v03', status='captured', checked_at='2026-10-25',
                app='dotsクラウドPCのChromium' + ('とBlender 4.3.2' if episode_number == 2 else ''),
                login_state='既存のログイン済み環境。新たな認証なし。', feature_entry='dotsのクラウドコンピューターを開く。',
                route='Chrome上のdotsからクラウドPCを表示。独立デモの実画面を取得しZIPで受領。',
                result='架空実演の静止画を取得。操作録画は未実施。' + ('操作引き継ぎ、見出し編集、保存と再読み込み、操作権返却を撮影担当AIも実施。' if episode_number == 1 else
                    'Blender GUI表示・回転・別名保存・再表示はcloud側の記録と実画面を確認。' if episode_number == 2 else
                    '3件の実GUI登録、全15項目と合計25万円の照合記録。Microsoft Excelではなく専用XLSXビューア。'),
                display_result='初回・修正・確認・再表示を区別して画面を保存。', save_result='ローカルのcloud/v01とcapturesへ保存。59ファイルのSHA-256一致。',
                legibility='動画は360px幅の場面確認済み。アプリ原本1165/1180px、Blenderレンダー1400px。表の細かな照合は記事用原本で行う。', shots=shots),
                f'pilot_capture_{episode_number:02d}_v03')
        timing = read(OUT / f'voice/{episode_number:02d}/v01/timings.json')
        frames = allocate_scenes([s['duration_ms'] for s in timing['segments']], story['duration_seconds'] * 24)
        board = []
        for index, (scene, duration) in enumerate(zip(story['scenes'], frames, strict=True)):
            row = dict(scene_id=f'pilot_{episode_number:02d}_scene_{index:02d}', purpose=scene['headline'].replace('\n', '・'),
                narration=scene['narration'], visual='実画面キャプチャ' if scene.get('capture') else 'Blender完成レンダーの編集映像' if scene['kind']=='hero' else '図解' if scene['kind']=='diagram' else '既存dots人物動画を全面で使用し顔と字幕を分離',
                duration_seconds=duration/24, beat='evidence' if index==0 else 'try' if index<3 else 'insight' if index<5 else 'action',
                asset_ids=scene_assets[index], claim_ids=[], source_ids=['computers'], character_ids=[])
            if index == len(story['scenes']) - 1:
                row.update(character_ids=['dots_pilot_' + ('female' if episode_number == 2 else 'male')],
                    character_action='実演を見て小さく気づき、手を開いて確認すべき点を示す。', presenter_layout='fullscreen', face_caption_separated=True)
            board.append(row)
        if not current.get('storyboard'):
            apply('storyboard', dict(episode_id=eid, scenes=board), f'pilot_storyboard_{episode_number:02d}_v01')

    manifest = read(OUT / 'blog-handoff/v02/asset-manifest.json')
    article_assets = []
    for item in manifest['assets']:
        aid = 'pilot_article_' + item['asset_id'].replace('-', '_')
        kind = 'official_capture' if item.get('source_url') else 'generated_still' if item.get('generated_render') else 'demonstration_capture'
        extra = dict(caption=item['article_use'], alt=item['article_use'], blog_usage_review='pending', user_approved_for_blog=False)
        if kind == 'official_capture':
            extra.update(source_url=item['source_url'], source_checked_at=item['source_checked_at'])
        if kind == 'demonstration_capture':
            extra['fictional_materials_only'] = True
        asset(aid, kind, item['artifact']['path'], **extra)
        article_assets.append(aid)
    if project()['article'].get('draft_path') != (HERE / 'article-draft-v03.md').relative_to(ROOT).as_posix():
        apply('article', dict(title='dotsのクラウドPCで制作と入力作業を引き継ぐ', slug='dots-cloud-desktop-handoff-blender-excel',
            publication_target='blog', draft_path=(HERE / 'article-draft-v03.md').relative_to(ROOT).as_posix(),
            sections=[dict(section_id='pilot_actual_demos_v03', title='操作交代・Blender・案件入力の実演',
                episode_ids=episode_ids, asset_ids=article_assets, claim_ids=[], character_ids=[], source_ids=['computers','tasks','controls'])]),
            'pilot_article_actual_v03')
    state = service.get(HERE.name)
    save(OUT / 'workspace-state-production-v01.json', state)
    print('Registered production, revision', state['project']['revision'])
    print(state['checks'])


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    register()
