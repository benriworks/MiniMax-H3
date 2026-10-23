"""Versioned Docs and dots message revisions; shared verified speech/render path."""
from pathlib import Path
import argparse, copy, importlib.util, json, sys
ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).parent
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('previous_delivery', ROOT/'productions/SERIES_20261023_dots_final_delivery/produce.py')
previous = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)
from tools.studio.shorts_creator import read, record, check, prepare, finish, run, validate_story
save = previous.save

def scene(layout, headline, parts, body='', items=None, action=None):
    result = previous.scene(layout, headline, ''.join(parts).replace('\n',''), body, items, action)
    result['captions'] = parts
    return result

def source(baseline, index, headline, parts):
    result = copy.deepcopy(baseline['scenes'][index])
    result.update(headline=headline, narration=''.join(parts).replace('\n',''), captions=parts)
    return result

def build(number):
    if number == 1:
        base = ROOT/'productions/content-projects/CONTENT_20261023_claude_docs_reuse'
        baseline = read(base/'creator-story.json')
        state = read(base/'pilot-state.json')
        voice = check(state['voice_source'])
        delivery = {'video':state['video']}
    elif number == 7:
        state = read(ROOT/'productions/SERIES_20261023_dots_final_delivery/07/final-state.json')
        baseline = read(check(state['visual_revision']))
        voice = ROOT/state['generation']/'voice-source.json'
        delivery = {'video':read(ROOT/state['output']/'verification.json')['delivery']}
    else:
        baseline, voice, delivery = previous.original(number)
    story = copy.deepcopy(baseline)
    story['id'] = 'SHORT_20261023_claude_docs_collaboration_v02' if number == 1 else f'SHORT_20261023_dots_{number:02d}_message_v02'
    if number == 1:
        story['title'] = '【Claude】メモからDocsへ！資料をつなぎ、人とAIで仕上げる'
        story['duration_seconds'] = 45
        scenes = [
            scene('hook','下書きの先まで、\nClaudeと。',['栞さんの企画書。','下書きの先まで、','Claudeと進めます。'],'同じ文書を仕上げる'),
            source(baseline,1,'会話の横で、\n文書を育てる。',['Docsは、人とClaudeが','同じ文書に','手を入れる作業場所。']),
            scene('research','メモも資料も、\n下書きの材料に。',['ファイルや会話、','接続した資料を、','下書きに生かします。'],'参照元を具体的に',[('元メモ','目的・日程'),('関連資料','決まっている条件')],'公式機能の解説'),
            source(baseline,3,'見出しと表で、\n文書を見渡す。',['見出しや表で','文書を見渡し、','内容を確かめます。']),
            scene('contrast','自分で直す。\nClaudeに相談する。',['細かな言葉は直接編集。','考え直したい箇所は、','コメントで相談できます。'],'同じ文書への編集',[('自分の手で','言葉を直接直す'),('Claudeと','コメントで相談')],'公式機能の解説'),
            source(baseline,4,'ここを、\nもっと読みやすく。',['今回の実演では、','予算の見出しと書式を','直すよう頼みました。']),
            source(baseline,5,'依頼した修正を、\n文書で確認。',['修正が文書に反映。','元の金額が','変わっていないかも確認。']),
            scene('recap','人の編集と相談を、\n同じ文書で。',['人の編集と\nClaudeへの相談で、','同じ文書を','完成へ近づけます。'],'下書きから仕上げへ',[('参照する','材料をそろえる'),('直して確認','同じ文書を磨く')]),
            scene('closing','一緒に仕上げる、\nClaude Docs。',['資料を集めて、','直して、確かめる。','詳しい手順は記事へ。'],'詳しい手順と入力例',action='動画と記事で確認'),
        ]
        note = '公式機能説明と2026-10-22の実演記録を区別。複数資料・直接編集・同時編集の追加実演は未撮影。公開用ブログ導線は公開後に設定。'
    elif number == 8:
        story['title'] = '【ChatGPT】頼む前に次の一手！dotsの「先回り提案」'
        story['duration_seconds'] = 30
        scenes = [
            scene('contrast','頼む前に、\n次の一手を提案。',['頼む前に、','次の一手を提案。'],'先回り提案',[('気づく','変化を見つける'),('提案する','次にすること')]),
            source(baseline,1,'メールや予定から、\n仕事の変化を知る。',['接続したメールや\n予定表を、','読める範囲で調べます。']),
            scene('research','仕事の文脈と、\n変化をつなぐ。',['毎回指示しなくても、','仕事の文脈と','変化をつなぎます。'],'使える情報をもとに',[('これまで','仕事の文脈'),('新しい情報','変わった予定')]),
            scene('calendar','会議は前倒し。\n資料の準備は？',['たとえば、会議は前倒し。','資料の締切はそのまま。'],'架空の例',[('会議','水曜へ変更'),('資料の締切','木曜のまま')]),
            scene('statement','「準備を早めませんか？」',['準備を早めませんか？と、','次の一手を提案します。'],'予定の変化から\n次の行動を提案',action='提案の例'),
            scene('permissions','提案を受けて、\n次の行動を決める。',['提案を受けて、','実行するかは\nあなたが判断。'],'提案から次の一歩へ',[('dots','気づきを届ける'),('あなた','次の行動を選ぶ')]),
            scene('recap','気づきを、\n行動のきっかけに。',['気づきを、','行動のきっかけに。','dotsの先回り提案。'],'先回り提案',[('気づく','仕事の変化'),('提案する','次の一手')],'次回：実行前の確認'),
        ]
        note = 'Proactive researchの価値を先回り提案として説明。許可された情報が対象で、個別の調査依頼を毎回必要としない。カレンダー例は架空。接続だけで全イベントの監視予約ができるとは主張しない。'
    elif number == 9:
        story['title'] = '【ChatGPT】dotsに任せても、決めるのはあなた！実行前の確認と判断'
        story['duration_seconds'] = 30
        scenes = [
            scene('contrast','大切な操作は、\n確認してから。',['大事なメール、','送る前に\n確認したいですよね。'],'実行前に判断',[('送る前に','内容を確認'),('決める人','あなた')]),
            scene('permissions','承認が必要なら、\nあなたへ確認。',['dotsは、承認が必要な','操作の前に、','あなたへ確認します。'],'内容を見て判断',[('確認する','相手と内容'),('判断する','実行するか')]),
            source(baseline,2,'「メール送信は、\n毎回確認して」',['たとえば、メール送信は','毎回確認、\nとルールで指定。']),
            scene('recap','送る・直す・やめる。\n決めるのはあなた。',['宛先と内容を見て、','送るか、\n修正するかを判断。'],'判断の例',[('送る','内容を確認して実行'),('直す','修正して再確認'),('やめる','今回は送らない')]),
            scene('contrast','下書きの依頼と、\n送信の許可は別。',['下書きを作って、だけでは','送信の許可になりません。'],'依頼の範囲を確認',[('作って','文面を準備'),('送って','相手へ送信')]),
            scene('statement','許可や設定によって、\n確認の扱いは変わる。',['事前の許可や設定で、','確認なしに進む','場合もあります。'],'常に毎回聞くとは\n限りません',action='許可する範囲を決める'),
            scene('recap','確認が来たら、\nあなたが判断。',['確認が来たら、\nあなたが判断。','dotsと、\n一緒に進めましょう。'],'任せる範囲を決める',[('確認する','相手と内容'),('判断する','実行・修正・中止')],'dotsと仕事を進めよう'),
        ]
        # The existing official quote is identified by kind, not a guessed index.
        quote = next(s for s in baseline['scenes'] if s.get('capture',{}).get('origin','official') == 'official' and 'capture' in s)
        scenes[2]['kind']='source'; scenes[2]['capture']=copy.deepcopy(quote['capture'])
        scenes[2].pop('media',None)
        note = '承認が必要な操作ではユーザーが判断。許可・設定・自動レビューにより確認なしで進む場合もある。表示する選択肢は判断の例であり実際のUIボタンの再現ではない。'
    else:
        scenes=copy.deepcopy(baseline['scenes'])
        scenes[-1]['narration']=scenes[-1]['narration'].replace('先回り調査','先回り提案')
        scenes[-1]['captions']=[s.replace('先回り調査','先回り提案') for s in scenes[-1]['captions']]
        scenes[-1]['action']=scenes[-1]['action'].replace('先回り調査','先回り提案')
        note = '第8回予告を先回り提案へ統一。他の音声は同一の検証済みPCMを再利用。'
    for index, item in enumerate(scenes):
        item.setdefault('eyebrow', baseline['scenes'][0]['eyebrow'])
        item.setdefault('source_ids',baseline['scenes'][0]['source_ids'])
        if 'visual_style' in baseline['scenes'][0]: item.setdefault('visual_style',baseline['scenes'][0]['visual_style'])
        item['eyebrow']=item['eyebrow'].replace('先回り調査','先回り提案')
        if index in [0,len(scenes)-1]:
            item['media']=copy.deepcopy(baseline['scenes'][0 if index==0 else -1]['media'])
            item['mediaStart']=0
    story['scenes']=scenes
    story.setdefault('editorial',{}).update(checked_date='2026-10-23',availability_note=note,user_approved=False)
    validate_story(story)
    folder=HERE/f'{number:02d}'
    folder.mkdir(exist_ok=True)
    path=folder/'creator-story.json'
    if path.exists() and read(path)!=story: raise ValueError('Frozen revision changed')
    if not path.exists():
        save(path,story)
        save(folder/'baseline.json',{'voice_source':record(voice),'video':delivery['video']})
    print(json.dumps({'event':'validated','episode':number}),flush=True)
    return path,story

def render(number):
    path,story=build(number)
    base_state=read(HERE/f'{number:02d}/state.json')
    state_path=HERE/f'{number:02d}/state.json'
    if number==1:
        # Preserve the first visual candidate and paid speech. Show the actual
        # table while narration discusses document structure, not a budget crop.
        visual=copy.deepcopy(story)
        capture_root=ROOT/'outputs/productions/SHORT_20261023_claude_docs_blog/captures'
        proof=read(capture_root/'first-output.json')
        adapted=ROOT/'outputs/productions/SHORT_20261023_claude_docs_collaboration_v02/captures/first-output.json'
        adapted.parent.mkdir(parents=True,exist_ok=True)
        proof['title']='初回文書の日程表と予算'
        proof['source_proof']=record(capture_root/'first-output.json')
        if not adapted.exists(): save(adapted,proof)
        visual['scenes'][3]['capture']={
            'path':proof['artifact']['path'],'proof':adapted.relative_to(ROOT).as_posix(),
            'origin':'demonstration','title':proof['title'],'product':proof['product'],'phase':proof['phase']}
        path=HERE/'01/visual-v03/creator-story.json'
        path.parent.mkdir(exist_ok=True)
        if not path.exists(): save(path,validate_story(visual))
        elif read(path)!=visual: raise ValueError('Frozen visual revision changed')
        state_path=HERE/'01/final-state.json'
    state=read(state_path) if state_path.exists() else {'generation':base_state['generation']}
    if 'output' not in state:
        out=prepare(path,narration_source=ROOT/state['generation']/'voice-source.json')
        state.update(output=out.relative_to(ROOT).as_posix(),status='prepared')
        save(state_path,state)
    out=ROOT/state['output']
    if not (out/'render.json').exists(): run('node',ROOT/'studio/creator-render.mjs',out)
    if not (out/'verification.json').exists(): finish(out)
    check(read(out/'verification.json')['delivery'])
    state['status']='rendered_awaiting_visual_review'
    save(state_path,state)
    print(json.dumps({'event':'rendered','episode':number,'output':state['output']}),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=['build','generate','render'])
    parser.add_argument('--episode',default='all')
    args=parser.parse_args()
    numbers=[1,8,9,7] if args.episode=='all' else [int(args.episode)]
    previous.HERE=HERE
    previous.build=build
    if args.command=='generate':
        for n in numbers: build(n)
        with previous.old.generation_lock():
            cadence=previous.old.SubmissionCadence()
            for n in numbers: previous.generate(n,cadence)
    else:
        for n in numbers: build(n) if args.command=='build' else render(n)
