"""Persist this chat's one-video brief and evidence without inventing final approval."""
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).parent;OUT=ROOT/'outputs/content-projects'/HERE.name
sys.path.insert(0,str(ROOT))
from tools.studio.content_workspace import ContentWorkspace
from tools.studio.database import StudioDatabase

def main():
    db=StudioDatabase(ROOT/'outputs/studio/studio.sqlite3',workspace=ROOT,recover=False)
    service=ContentWorkspace(ROOT,db);pid=HERE.name;plan=json.loads((HERE/'plan.json').read_text(encoding='utf-8'));ep=plan['episodes'][0]
    try:service.get(pid)
    except KeyError:service.create(dict(content_project_id=pid,operation_id='op_tibo_create',title='Tiboの28日間チャレンジまとめ',topic='Codex・Workの改善とリセットの振り返り',audience='ChatGPTやCodexを日常的に使う日本語視聴者'))
    def apply(action,data,token):
        op='op_tibo_'+token
        with db.session() as c:
            if c.execute('SELECT 1 FROM content_project_revisions WHERE project_id=? AND operation_id=?',(pid,op)).fetchone():return
        revision=service.get(pid)['project']['revision']
        service.apply(pid,action,dict(operation_id=op,expected_revision=revision,data=data))
    urls={
      'promise':('https://x.com/thsottiaux/status/2106845241357824205','Tibo本人の開始宣言'),
      'day26':('https://x.com/thsottiaux/status/2116405414921384099','Tibo Day26・最後の2日間の予告'),
      'resets':('https://help.openai.com/en/articles/20001498-how-resets-work-in-codex','公式リセット説明'),
      'speed':('https://help.openai.com/en/articles/20001596-response-speed-and-usage-resets-in-work-and-codex','公式速度説明'),
      'pro':('https://help.openai.com/en/articles/9793128-about-chatgpt-pro-tiers','公式Pro条件'),
      'release':('https://help.openai.com/en/articles/6825453-chatgpt-release-notes','公式リリースノート'),
      'tracker':('https://codex-resets.com/ja/tibo-28','原投稿を探す補助索引')}
    day_ids={2:'2107676072871600470',3:'2108040921044639779',7:'2109430343346581527',16:'2112712984644784534'}
    for n,x in day_ids.items():urls['day'+str(n)]=('https://x.com/thsottiaux/status/'+x,'Tibo Day'+str(n))
    apply('research',dict(research_id='research_tibo_v01',checked_at='2026-11-01',summary='原投稿・公式Help・リリースノートを照合。PacificではDay27進行中。最後の2日間は予告まで。Day18/20は予告と表示。各原投稿URLと限界はSOURCES_JA.md。',sources=[dict(source_id=k,url=u,title=t,kind='secondary' if k=='tracker' else 'official',checked_at='2026-11-01') for k,(u,t) in urls.items()]),'research')
    additional={4:'2108275041276420573',5:'2108645667451318747',6:'2109132167112782291',8:'2109873287853707513',9:'2110151780478927344',10:'2110618732666257557',11:'2110750421367287996',12:'2111244596131111253',13:'2111566005684289735',14:'2111990254408434095',15:'2112432076767289678',17:'2113162277688070445',18:'2113492502355562875',19:'2113770573994299544',20:'2114200291319124163',21:'2114588174249071102',22:'2114800277677092936',23:'2115273064481218829'}
    apply('research',dict(research_id='research_tibo_daily_primary',checked_at='2026-11-01',summary='日別主張から一次投稿へ直接たどれるよう出典IDを補完。Day9は訂正版、Day18/20は予告。',sources=[dict(source_id='day'+str(n),url='https://x.com/thsottiaux/status/'+x,title='Tibo Day'+str(n),kind='official',checked_at='2026-11-01') for n,x in additional.items()]),'research_daily')
    manifest=json.loads((OUT/'asset-manifest.json').read_text(encoding='utf-8'))['items']
    for item in manifest:
        if item['kind']!='source_excerpt':continue
        sid=item['source_id'];aid=Path(item['path']).stem.replace('-','_')
        data=dict(asset_id=aid,kind='demonstration_capture' if sid=='own_ui' else 'official_capture',path=item['path'],bytes=item['bytes'],sha256=item['sha256'],width=item['width'],height=item['height'],visibility='public',privacy_review='passed',blog_usage_review='passed',source_url='https://chatgpt.com/settings/usage' if sid=='own_ui' else urls[sid][0],source_checked_at='2026-11-01')
        if sid=='own_ui':data['fictional_materials_only']=True
        apply('asset',data,'asset_'+aid)
    apply('capture',dict(inspection_id='inspection_reset_settings',target_feature='ChatGPT Webの使用状況・リセットの確認入口',status='captured',checked_at='2026-11-01',route='Computer UseでChromeのChatGPT設定→使用状況を開く',result='説明欄と完全リセットの入口を撮影。個人の残量と保有数を公開用から除き、使用・購入は行っていない。',app='Chrome / ChatGPT Web',login_state='ログイン済み',feature_entry='設定→使用状況',display_result='利用上限のリセット欄と説明を観察',save_result='原本は_private/captures、公開用はassets/usage-reset-description.png',legibility='原本幅約1253px。1400px目安は未達、汎用説明の短い切出しを使用。',shots=[dict(shot_id='usage_description',purpose='リセットの確認入口と説明。付与の実証ではない。',asset_id='usage_reset_description')]),'capture')
    apply('proposal',dict(proposal_id='proposal_tibo_v01',count_reason='ユーザーが指定した振り返り1本。全機能の詳細は記事に分け、日別の流れと2種類のリセットを動画にする。',episodes=[dict(episode_id=ep['id'],title=ep['title'],overview=ep['conclusion'],intended_message=ep['conclusion'],duration_seconds=76,demo_idea='実際の使用は行わず、公式抜粋とボタン・券の動きで仕組みを示す。',article_role='日別表、原投稿URL、対象条件と確認範囲を補足',capture_inspection_id='inspection_reset_settings')]),'proposal')
    apply('feedback',dict(feedback_id='feedback_tibo_request',proposal_id='proposal_tibo_v01',kind='acceptance',text='Tiboの28日間チャレンジまとめをショート動画にしてください。リセットの日はリセットボタンを押す動画を、バンクリセットの日はそれを表す動画を差し込んで下さい。公式サイトやTiboのツイートの画像なども引用して下さい。',interpretation='1本の制作と指定演出を採用範囲とする。助手が選んだ尺・日別整理・完成候補・記事や動画の公開まで承認されたとは扱わない。既存の採用人物・声・BGMを継承。'),'brief')
    apply('accept',dict(proposal_id='proposal_tibo_v01',feedback_id='feedback_tibo_request',confirm_acceptance=True),'accept_scope')
    apply('feedback',dict(feedback_id='feedback_tibo_center_celebrate',proposal_id='proposal_tibo_v01',kind='revision_request',text='大枠は大丈夫です。添付画像のようにボタンの中のテキストの位置を、上下中央揃えにしてほしい。ただし、複数行出てくる可能性があるなら上寄せで構わない。あと、動画の最後でTiboのチャレンジを賞賛してほしい。キラキラとした演出もお願い。',interpretation='v04の大枠への肯定を記録。1行ボタンは実グリフで中央、複数行の説明は上寄せを維持。終端に称賛のAoedeと金色のきらめきを追加したv06をレビュー候補とする。未確定日を完結扱いにせず、完成物採用や公開へ拡張しない。'),'feedback_center_celebrate')
    apply('feedback',dict(feedback_id='feedback_tibo_music_cues',proposal_id='proposal_tibo_v01',kind='revision_request',text='曲も今回は明るめのループに作り替えたいし、リセット、バンクリセット、それ以外の改善に分けて効果音をつけたい。',interpretation='v06の映像と声を維持し、今回専用の明るい8小節ループと3種類の効果音へ更新したv07を制作。押下・保管・改善カード表示の時刻へ配置し、発話中は抑える。音楽の全体既定や完成動画の採用・公開には拡張しない。'),'feedback_music_cues')
    sources=[['promise','resets'],['promise'],['speed','day2','day3','day4','day5','day6','day7'],['day8','day9','day10','day11','day12','day13','day14','resets'],['day15','day16','day17','day18','day19','day20','day21','resets'],['day22','day23','release','pro'],['day26'],['resets'],['resets'],['promise']]
    for i,s in enumerate(ep['scenes']):
        if s['kind']=='celebration':continue  # Editorial appreciation is not a new official factual claim.
        apply('claim',dict(claim_id='claim_'+str(i),text=s['spoken'],basis='official',source_ids=sources[i],asset_ids=[],checked_at='2026-11-01'),'claim_v04_'+str(i))
    actual=json.loads((OUT/'tibo-recap/release/v07/timeline.json').read_text(encoding='utf-8'))
    apply('storyboard',dict(episode_id=ep['id'],scenes=[dict(scene_id='scene_'+str(i),purpose=s['headline'],narration=s['spoken'],visual=s['kind']+' / 既存人物、引用、自作モーション、1行中央・複数行上寄せ、称賛ときらめき、明るいループと3種SE',duration_seconds=actual[i]['end']-actual[i]['start'],source_ids=sources[i],claim_ids=[] if s['kind']=='celebration' else ['claim_'+str(i)],asset_ids=[],character_ids=[],beat='evidence') for i,s in enumerate(ep['scenes'])]),'storyboard_v07')
    apply('article',dict(status='draft',published=False,sections=[dict(section_id='article_tibo',title='Tiboの28日間チャレンジ：改善とリセットの違い',episode_ids=[ep['id']],source_ids=list(urls),draft_path=(HERE/'article-draft.md').relative_to(ROOT).as_posix())]),'article_v06')
    current=service.get(pid);(OUT/'content-workspace-current.json').write_text(json.dumps(current,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(revision=current['project']['revision'],episodes=len(current['project']['episodes']),claims=len(current['project']['claims']),assets=len(current['project']['assets']),final_approval=False)))

if __name__=='__main__':main()
