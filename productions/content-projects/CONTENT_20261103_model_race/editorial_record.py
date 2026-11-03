"""Record the real user response and production evidence through the shared CLI."""
from pathlib import Path
import json
from workspace_record import cli
HERE=Path(__file__).parent;ROOT=HERE.parents[2]
OUT=ROOT/'outputs/content-projects'/HERE.name
USER_RESPONSE='企画を確認しました。大筋は問題ありません。 「画面操作と仕事」のような名詞だとわかりにくい。他にXや公式サイトで使われている言葉にしてほしい。'

def event(action,op,data):
    log=OUT/'work/workspace-operations'/(op+'-result.json')
    if log.exists():return json.loads(log.read_text(encoding='utf-8'))
    state=cli('get',project_id=HERE.name)
    result=cli('apply',dict(operation_id=op,expected_revision=state['project']['revision'],data=data),project_id=HERE.name,action=action)
    log.parent.mkdir(parents=True,exist_ok=True);log.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return result

def accept_outline():
    sources=json.loads((HERE/'sources.json').read_text(encoding='utf-8'))['sources']
    event('research','research_official_wording_v03',dict(research_id='official-wording-v03',checked_at='2026-11-03',summary='ユーザーが企画v01の大筋を確認し、抽象的な名詞の並びを公式・Xで使う表現へ直すよう指定。日本語公式のコンピューター操作、ブラウジング、エージェント型コーディング、専門業務を照合。X検索のGrok集約は公式原投稿ではないため根拠にしない。',sources=[dict(source_id=s['source_id'],title=s['title'],url=s['url'],kind='official',checked_at='2026-11-03') for s in sources if s['source_id'] in ['astra-ja','sol61-ja']]))
    event('feedback','user_outline_acceptance_wording_v03',dict(feedback_id='outline-acceptance-wording-v03',proposal_id='proposal-v01',text=USER_RESPONSE,interpretation='大筋の構成、本数、既存男女の継続を採用。抽象的な見出しは未採用として公式用語と具体的な動作へ編集し、制作を継続する。変更語句そのものをユーザーが選んだと扱わず、完成動画・記事の採用や公開許可にも広げない。',kind='acceptance'))
    result=event('accept','accept_outline_v01_with_wording_revision',dict(proposal_id='proposal-v01',feedback_id='outline-acceptance-wording-v03',confirm_acceptance=True))
    print(json.dumps(dict(revision=result['project']['revision'],phase=result['project']['phase'],accepted=result['project']['accepted_proposal']),ensure_ascii=False))

if __name__=='__main__':accept_outline()
