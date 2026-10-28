"""Write source/asset ledger through the shared, versioned ContentWorkspace CLI."""
from pathlib import Path
import html,json,subprocess,sys,hashlib,shutil
from datetime import datetime,timezone
from PIL import Image
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];OUT=ROOT/'outputs/content-projects'/HERE.name/'v01'
PID=HERE.name;URL='https://learn.chatgpt.com/docs/whats-new/october-26-30-2026';DATE='2026-10-29'
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def rec(p):
    r=dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest().upper())
    if p.suffix=='.png':
        with Image.open(p) as im:r.update(width=im.width,height=im.height)
    return r
def viewer():
    r=json.loads((OUT/'terra-api/review.json').read_text(encoding='utf-8'))
    (OUT/'api-result-viewer.html').write_text('''<!doctype html><html lang="ja"><meta charset="utf-8"><title>Terra API画像確認・実行結果</title><style>body{margin:0;padding:36px 50px;background:#f6f7ef;color:#16382c;font:24px 'Yu Gothic',sans-serif}h1{font-size:42px;margin:0 0 8px}p{margin:10px 0}.grid{display:grid;grid-template-columns:1fr 1fr;gap:30px}img{width:100%;border:1px solid #c5d4bf}.box{background:#fff;padding:24px;border-radius:20px;margin:24px 0}small{font-size:18px}strong{font-size:32px}</style><h1>GPT-6.1 Terra：告知画像の確認</h1><small>今回のAPI検証結果を表示する自作ビューアー／ChatGPT・CodexのUIではありません</small><div class="box"><strong>Terraの実際の回答</strong><p>'''+html.escape(r['issue'])+'</p><p>'+html.escape(r['fix'])+'''</p><small>モデル提案：見出し x='''+str(r['title_x'])+'px / フォントサイズ '+str(r['title_font_size'])+'''px</small></div><div class="grid"><section><h2>入力画像</h2><img src="banner-before.png"></section><section><h2>提案値を制作側で反映</h2><img src="banner-after.png"></section></div><p>架空の素材のみ使用。APIへの画像入力と提案の取得を検証。PCの自動操作は未実施。</p></html>''',encoding='utf-8')
    print('Viewer created')
def register():
    count=0
    def cli(cmd,data=None,action=None):
        nonlocal count
        args=[sys.executable,'-m','tools.studio.content_workspace',cmd,'--project-id',PID]
        if data is not None:
            p=HERE/'inputs'/f'{count:02d}-{action or cmd}.json';count+=1;save(p,data);args+=['--input',str(p)]
        if action:args+=['--action',action]
        p=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
        if p.returncode:raise RuntimeError(p.stderr)
        return json.loads(p.stdout)
    try:cli('get');raise RuntimeError('Project exists; preserve its history and inspect before re-running')
    except RuntimeError as e:
        if 'Project exists' in str(e):raise
    cli('create',{'operation_id':'terra_create_v01','content_project_id':PID,'title':'GPT-6.1 Terra発表・画像確認のショート','topic':'新しくgpt6.1 Terraが発表されたので、ショート動画を作りたい','format':'shorts_first'})
    def apply(action,data):
        p=cli('get')['project'];return cli('apply',{'operation_id':'terra_'+action.replace('-','_')+'_'+str(p['revision']),'expected_revision':p['revision'],'data':data},action)
    sources=[{'source_id':'official_launch','title':'October 26–30, 2026','url':URL,'kind':'official','checked_at':DATE,'event_at':'2026-10-26'}, {'source_id':'official_model','title':'GPT-6.1 Terra Model','url':'https://developers.openai.com/api/docs/models/gpt-6.1-terra','kind':'official','checked_at':DATE}]
    apply('research',{'research_id':'terra_research_v01','summary':'10月26日リリース。画像理解・PC操作・文章作成を公式確認。Work/Codex対応、通常Chat非対応。架空バナーをTerra APIで画像確認し、右端の見出し欠けを指摘。提案値をPythonで反映。PC操作の実測・モデル比較・時短率は未検証。','checked_at':DATE,'sources':sources})
    episode={'episode_id':'terra_short','title':'【ChatGPT】画像を理解してPC操作へ。GPT-6.1 Terra登場','overview':'画像のはみ出し確認と修正例、モデルの特徴、使える場所を示す単発ショート。','intended_message':'画像を見て問題を指摘し、次の修正へつなぐ。画面操作にはツール設定が必要。','duration_seconds':50,'demo_idea':'架空バナーの画像入力→実際の指摘→提案値による修正。PC自動操作の成功とは呼ばない。','article_role':'公式条件、入力条件、実回答、提案値、修正と未検証範囲を詳述。'}
    apply('proposal',{'proposal_id':'terra_proposal_v01','count_reason':'1つの中心メッセージと実例を50秒前後で示すため、まず単発1本。人物シリーズの新規立上げは行わない。','episodes':[episode]})
    apply('feedback',{'feedback_id':'terra_user_create','proposal_id':'terra_proposal_v01','kind':'acceptance','text':'作成して下さい','interpretation':'直前に提示した約50秒・特徴＋架空告知画像の実演＋利用場所の1本の制作依頼として記録。完成物採用・公開・新規人物採用は含めない。'})
    apply('accept',{'proposal_id':'terra_proposal_v01','feedback_id':'terra_user_create','confirm_acceptance':True})
    assets=[]
    for aid,name,kind in [('before_banner','banner-before.png','original'),('after_banner','banner-after.png','original'),('api_result','api-result-capture-v02.png','demonstration_capture'),('official_heading','official-heading.png','official_capture')]:
        p=OUT/name
        a={'asset_id':aid,'kind':kind,'visibility':'public','privacy_review':'passed','fictional_materials_only':True,**rec(p)}
        if kind=='official_capture':a.update(source_url=URL,source_checked_at=DATE)
        apply('asset',a);assets.append(a)
    apply('capture',{'episode_id':'terra_short','status':'captured','checked_at':DATE,'route':'ユーザーPCの独立Chromeから公式ページとchatgpt.comを開く。Workは独立セッションが未ログイン。Terra APIの実応答と前後画像を自作HTMLで表示しPlaywright撮影。','result':'1600px幅の公式原本とAPI結果画面を保存。ログイン済みWorkのモデル選択画面は未撮影。','app':'Chrome / OpenAI Responses API / 自作結果ビューアー','login_state':'API認証成功。独立ChromeはChatGPT未ログイン。既存ログイン情報へはアクセスしていない。','feature_entry':'Responses API gpt-6.1-terra + image input','display_result':'右端の見出し欠けを指摘。提案x780/60pxをコードで反映し画像を確認。','save_result':'案件v01配下へ実応答・画像・キャプチャを保存','legibility':'原本1600px幅。動画は全文と見出し拡大を別カットで使用。最終360px動画確認は別途。','shots':[{'shot_id':'api_response','purpose':'実API結果と前後画像を示す','asset_id':'api_result'}]})
    for cid,txt in [('official_capability','公式は画像理解とPC操作に強いモデルと説明。'),('official_access','WorkとCodexで対応。通常Chatでは利用不可。Advancedから選択し、プラン・管理者設定・対応ツールの条件を確認。')]:
        apply('claim',{'claim_id':cid,'text':txt,'basis':'official','checked_at':DATE,'source_ids':['official_launch'],'asset_ids':[]})
    apply('claim',{'claim_id':'tested_banner','text':'この架空バナー1枚をTerra APIへ渡すと右端の見出し欠けを指摘し、位置780・文字60pxを提案。制作側で反映して全文表示を確認。','basis':'tested','checked_at':DATE,'source_ids':[],'asset_ids':['api_result'],'test_conditions':'gpt-6.1-terra / Responses API / reasoning low / image1600x1000 / 正しい題名、x700-850、文字40-66の制約も入力。1件・1回。PC自動操作や修正後の再推論は未実施。'})
    story=json.loads((HERE/'story-v01.json').read_text(encoding='utf-8'))
    apply('storyboard',{'episode_id':'terra_short','scenes':[{'scene_id':s['id'],'purpose':s['label'],'narration':s['spoken'],'visual':'制作コードの同名場面。'+str(s['headline']),'duration_seconds':6.25,'claim_ids':['tested_banner'] if s['id'] in ['hook','before','after'] else ['official_capability','official_access'],'asset_ids':['before_banner','after_banner','api_result'] if s['id'] in ['hook','before','after'] else ['official_heading'],'character_ids':[],'source_ids':['official_launch']} for s in story['scenes']]})
    apply('article',{'slug':'gpt-61-terra-image-check','sections':[{'section_id':'facts','title':'Terraの特徴と利用場所','episode_ids':['terra_short'],'claim_ids':['official_capability','official_access'],'source_ids':['official_launch','official_model'],'asset_ids':['official_heading'],'character_ids':[]},{'section_id':'demo','title':'架空バナー1枚のAPI確認','episode_ids':['terra_short'],'claim_ids':['tested_banner'],'source_ids':[],'asset_ids':['api_result','before_banner','after_banner'],'character_ids':[]}]})
    state=cli('get');save(HERE/'workspace-state-v01.json',state)
    save(OUT/'asset-manifest.json',{'assets':assets,'article_destination':'benriworks/blog','blog_image_usage':'candidate_not_published','official_context':rec(ROOT/'output/playwright/terra-official-context-v01.png'),'raw_api':rec(OUT/'terra-api/response.json')})
    save(HERE/'verification-preparation-v01.json',{'status':'prepared','project_revision':state['project']['revision'],'checks':state['checks'],'api_model':json.loads((OUT/'terra-api/submission.json').read_text())['response_model'],'real_pc_automatic_operation':'not_tested','voice':'Aoede rejected 402 quota_exhausted; alternative approval pending'})
    print('Registered content project revision',state['project']['revision'])
if __name__=='__main__':{'viewer':viewer,'register':register}[sys.argv[1]]()
