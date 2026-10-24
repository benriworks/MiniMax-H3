"""Record the user's revision, new primary sources and their dependent scenes."""
from pathlib import Path
import sys
import json
ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from tools.studio.content_workspace import ContentWorkspace
from tools.studio.database import StudioDatabase
from tools.studio.shorts_creator import read,record
PID=HERE.name
service=ContentWorkspace(ROOT,StudioDatabase(ROOT/'outputs/studio/studio.sqlite3',workspace=ROOT,recover=False))

def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def apply(action,data,operation):
    path=HERE/'inputs'/(operation+'.json')
    if path.exists():
        body=read(path)
        if body['data']!=data:raise ValueError('Recorded operation changed')
    else:
        body={'operation_id':operation,'expected_revision':service.get(PID)['project']['revision'],'data':data}
        save(path,body)
    return service.apply(PID,action,body)

feedback=read(HERE/'inputs/php_revision_v03_feedback.json')['data']['text']
apply('feedback',{'feedback_id':'php_user_revision_v03','proposal_id':'proposal_php_overview_v01','kind':'revision_request','text':feedback,
    'interpretation':'同じ動画の改訂として国内サーバーの利用率を正しい分母で追加。WordPress・PHPで作られたフォームや買い物の例を示し、アクセス者→サーバー内のPHPとアプリ→応答をイラスト化。読む時間を確保する60秒候補。採用人物と後半音声は維持し、最終動画のユーザー採用は未確認。'},'php_revision_v03_feedback')
sources=[
 {'source_id':'w3techs_japan_v03','title':'Usage of PHP broken down by server locations','url':'https://w3techs.com/technologies/breakdown/pl-php/server_location','kind':'official','publisher':'W3Techs / Q-Success','published_at':'2026-10-24','checked_at':'2026-10-25','summary':'日本にサーバーがあり、サーバー側言語を判別できたサイトの92.4%がPHP。日本の全サイトの割合や脆弱性の影響率ではない。'},
 {'source_id':'w3techs_method_v03','title':'W3Techs methodology','url':'https://w3techs.com/technologies','kind':'official','publisher':'W3Techs / Q-Success','checked_at':'2026-10-25','summary':'有効な内容・機能を持つサイトを対象とし、ページ単位ではなくサイト単位。判別可能なサーバー側言語とサーバー所在地による限定した集計として扱う。'},
 {'source_id':'wordpress_php_v03','title':'WordPress official requirements','url':'https://wordpress.org/about/requirements/','kind':'official','publisher':'WordPress.org','checked_at':'2026-10-25','summary':'WordPressはPHPとデータベースを利用する。一般的なPHP要件を今回の脆弱性に対する修正済み番号と混同しない。'},
 {'source_id':'php_intro_v03','title':'PHP公式入門：PHPとはなんでしょう','url':'https://www.php.net/manual/ja/introduction.php','kind':'official','publisher':'The PHP Group','checked_at':'2026-10-25','summary':'PHPのコードはサーバー側で実行され、結果がクライアントへ送信される。フォーム処理や動的コンテンツ生成に使うことができる。'},
]
apply('research',{'research_id':'php_research_v03','checked_at':'2026-10-25','summary':'国内との関係、WordPress依存とサーバー側の動作を一次資料で追加確認。統計を被害率・日本全体の利用率として表さない。','sources':sources},'php_revision_v03_research')
for claim,text,refs in [
 ('japan_usage','2026-10-24のW3Techs調査で、日本にサーバーがあり、サーバー側プログラミング言語を判別できたサイトの92.4%がPHPを使用。日本全体の全数調査でも、今回の影響率でもない。',['w3techs_japan_v03','w3techs_method_v03']),
 ('php_services','WordPressはPHPを利用する。フォームや買い物などの仕組みもPHPで実装される例がある。すべての対話的サイトがPHPを使うわけではない。',['wordpress_php_v03','php_intro_v03']),
 ('php_request_response','PHPはサーバー側で実行され、アクセスに応じた処理の結果をブラウザーへ返す。ブラウザーがサーバー側PHPコードを実行する図にはしない。',['php_intro_v03']),
]:
    apply('claim',{'claim_id':claim,'text':text,'basis':'official','source_ids':refs,'checked_at':'2026-10-25','asset_ids':[]},'php_v03_claim_'+claim)
capture=read(ROOT/'outputs/content-projects'/PID/'captures/revision-v03/capture-preflight.json')
for i,cap in enumerate(capture['captures']):
    apply('asset',{'asset_id':'php_v03_research_capture_'+str(i),'kind':'official_capture','path':cap['artifact']['path'],'visibility':'private','privacy_review':'passed','source_url':cap['source_url'],'source_checked_at':'2026-10-25','caption':cap['purpose'],'blog_usage_review':'pending','user_approved_for_blog':False},'php_v03_capture_'+str(i))
apply('capture',{'inspection_id':'php_v03_preflight','target_feature':'PHP国内利用統計とWordPressのPHP要件','status':'available','checked_at':'2026-10-25','route':'このPCのin-app browserで一次資料2ページを開き、実画面を保存','result':'Japan 92.4%とデータ日、WordPressのPHP要件を画面で確認。研究用原本を保存。新しい図解を実画面と呼ばない。','app':'in-app browser','login_state':'不要','feature_entry':'W3Techsの国別PHPページ、WordPress公式Requirements','display_result':'統計の分母・数値・データ日とPHP要件が表示された','save_result':'JPEG原本を案件captures/revision-v03へ保存しhash記録','legibility':'原本で数値・要件を確認。動画の日本語表示と図解は別に360pxで検証','shots':[]},'php_v03_capture_inspection')
script=read(HERE/'creator-story-v03.json')
allocation=read(ROOT/'outputs/content-projects'/PID/'voice/v03/allocation.json')['scene_frames']
claims=[['php_services'],['japan_usage'],['php_services'],['php_request_response'],['identity'],['impact'],['impact'],['response'],['fixes','response'],['response'],['followup'],['followup','response']]
refs=[['wordpress_php_v03'],['w3techs_japan_v03','w3techs_method_v03'],['wordpress_php_v03','php_intro_v03'],['php_intro_v03'],['php_oct21'],['php_oom','php_state'],['php_oom','php_state'],['jpcert_oct22'],['php_oct21','jpcert_oct22'],['jpcert_oct22'],['php_oct23'],['php_oct23','jpcert_oct22']]
board=[]
for i,(s,frames) in enumerate(zip(script['scenes'],allocation,strict=True)):
    row={'scene_id':f'php_v03_scene_{i:02d}','purpose':s['headline'].replace('\n','・'),'narration':s['narration'],'visual':'採用済みMiniMax人物動画の全面導入' if i==0 else 'PHPで使うサービス・利用者・サーバー・応答の自作イラスト' if i in (2,3) else '出典付きの統計表示' if i==1 else '公式画面の引用' if s['kind']=='source' else '自作の説明と確認項目','duration_seconds':frames/24,'beat':'problem' if i==0 else 'evidence' if i in (1,4,10) else 'insight' if i in (2,3,5,6) else 'action','claim_ids':claims[i],'source_ids':refs[i],'asset_ids':[],'character_ids':[]}
    if i==0:row.update(asset_ids=['miura-wataru-reference','miura-minimax-motion-v01'],character_ids=['miura_wataru'],character_action='確認済みの同じ人物動画を再利用。気づいて手を開く動作。',presenter_layout='fullscreen',face_caption_separated=True)
    if i==4:row['asset_ids']=['php-public-quote-v01']
    if i==10:row['asset_ids']=['php-followup-public-quote-v01']
    board.append(row)
apply('storyboard',{'episode_id':'php2shell_overview','scenes':board},'php_storyboard_v03')
figures_path=ROOT/'outputs/content-projects'/PID/'blog-assets/v03/figure-provenance.json'
if figures_path.exists():
    for figure,index in zip(read(figures_path)['figures'],[2,3],strict=True):
        apply('asset',{'asset_id':figure['asset_id'],'kind':'original','path':figure['artifact']['path'],'visibility':'public','privacy_review':'passed','alt':figure['alt'],
            'caption':'自作のコード図解。製品の実画面や公式のスクリーンショットではない。','source_type':'original_code_diagram','provenance':figures_path.relative_to(ROOT).as_posix(),
            'blog_usage_review':'pending','user_approved_for_blog':False},'php_v03_figure_'+str(index))
        board[index]['asset_ids'].append(figure['asset_id'])
    apply('storyboard',{'episode_id':'php2shell_overview','scenes':board},'php_storyboard_v03_figures')
save(HERE/'workspace-state-v03.json',service.get(PID))
print('User revision, sources, source captures and twelve-scene storyboard recorded')
