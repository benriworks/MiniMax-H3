"""Record the user's authorized edits, without treating delivery as final approval."""
from copy import deepcopy
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
OUT = ROOT / 'outputs/content-projects' / HERE.name
sys.path.insert(0, str(ROOT))
from tools.studio.content_workspace import ContentWorkspace
from tools.studio.database import StudioDatabase
from tools.studio.shorts_creator import read
from produce import save

USER_TEXT = '''①の動画にこのdotsの画面キャプチャを入れてほしい。あと、dotsをdotと記載してナレーションしているので直して。
②どら焼きについては問題ないが、クラウドの共同作業領域にBlenderがインストールされていて、依頼すればモデリングしてくれることをはっきり伝えて
③疑似システムは、疑似システムとは言わなくていい。Webブラウザと表計算が使えるので、システムに自動転記が可能であるとはっきり伝えて。今回の画面は模擬システムで、実際にはシステムの権限が必要であることを補足するくらいでいい。あと表をおもてとナレーションしているので直して。'''


def main():
    service = ContentWorkspace(ROOT, StudioDatabase(ROOT / 'outputs/studio/studio.sqlite3', workspace=ROOT, recover=False))
    def project():
        return service.get(HERE.name)['project']
    def apply(action, data, operation):
        body = dict(operation_id=operation, expected_revision=project()['revision'], data=data)
        save(OUT / 'inputs' / (operation + '.json'), body)
        return service.apply(HERE.name, action, body)
    pid, fid = 'proposal_dots_shared_desktop_v03', 'feedback_dots_pilot_revision_v02'
    if not any(p['proposal_id'] == pid for p in project()['proposals']):
        proposal = deepcopy(project()['proposals'][-1])
        proposal['proposal_id'] = pid
        messages = [
            'ユーザー提供のクラウドPC画面を冒頭に使い、dotsの共有デスクトップと操作交代を伝える。dotsはドッツと読む。',
            'クラウドの共同作業領域にBlenderが入っており、dotsに依頼すればそこでモデリングできる。',
            'Webブラウザーと表計算を利用してシステムへ自動転記できる。模擬画面と実運用の権限条件を後半で補足。表はひょうと読む。',
        ]
        for n, (episode, message) in enumerate(zip(proposal['episodes'], messages, strict=True), 1):
            episode['intended_message'] = message
            episode['title'] = read(HERE / f'{n:02d}/creator-story-v02.json')['title']
        apply('proposal', proposal, 'pilot_revision_v02_proposal')
    if not any(f['feedback_id'] == fid for f in project()['feedback']):
        apply('feedback', dict(feedback_id=fid, proposal_id=pid, text=USER_TEXT,
            interpretation='明示された修正を制作へ適用する。完成動画の最終採用や公開の許可とは扱わない。', kind='revision_request'), 'pilot_revision_v02_feedback')
    if project()['accepted_proposal']['proposal_id'] != pid:
        apply('accept', dict(proposal_id=pid, feedback_id=fid, confirm_acceptance=True), 'pilot_revision_v02_authorized_scope')
    for n, episode in enumerate(deepcopy(project()['episodes']), 1):
        story = read(HERE / f'{n:02d}/creator-story-v02.json')
        state = read(OUT / f'render-state-{n:02d}-v02.json')
        props = read(ROOT / state['output'] / 'props.json')
        board = deepcopy(episode['storyboard'])
        for index, (row, scene, rendered) in enumerate(zip(board, story['scenes'], props['scenes'], strict=True)):
            row.update(purpose=scene['headline'].replace('\n', '・'), narration=scene['narration'], duration_seconds=rendered['duration']/24)
            if n == 1 and index in (0, 3):
                aid = f'pilot_01_scene_{index:02d}_v02'
                if not any(a['asset_id'] == aid for a in project()['assets']):
                    capture = scene['capture']
                    apply('asset', dict(asset_id=aid, kind='demonstration_capture', path=capture['path'], visibility='public',
                        privacy_review='passed', fictional_materials_only=True, capture_proof=capture['proof'],
                        caption='ユーザー提供のクラウドPC画面の切り出し。' if index == 0 else '既存の操作権返却画面。原画のUIは保持。',
                        user_approved_for_blog=False), f'pilot_revision_v02_asset_{index:02d}')
                row['asset_ids'] = [aid]
        apply('storyboard', dict(episode_id=episode['episode_id'], scenes=board), f'pilot_revision_v02_storyboard_{n:02d}')
    article = deepcopy(project()['article'])
    article['draft_path'] = (HERE / 'article-draft-v04.md').relative_to(ROOT).as_posix()
    article['sections'][0]['asset_ids'] += ['pilot_01_scene_00_v02']
    article['sections'][0]['asset_ids'] = list(dict.fromkeys(article['sections'][0]['asset_ids']))
    article['sections'][0]['title'] = '共有画面・モデリング依頼・システムへの自動転記'
    apply('article', article, 'pilot_revision_v02_article_v04')
    result = service.get(HERE.name)
    save(OUT / 'workspace-state-production-v02.json', result)
    print('Recorded revision', result['project']['revision'], result['checks'])


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
