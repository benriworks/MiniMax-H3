"""Native landscape article figures and a hashed, public-only handoff ZIP."""
import hashlib,importlib.util,json,shutil,zipfile
from PIL import Image,ImageDraw
import produce as p
def figures(folder):
    c=p.Canvas();paths=[]
    for name,title in [('shared-pool','12月予定：ChatGPTとCodexの利用枠を共通化へ'),('instant-bypass','Instant chatは、この共通枠を消費しない'),('known-unknown','確認できた予定と、まだ記載のない条件')]:
        im=Image.new('RGB',(1920,1080),p.BG);c.text(im,title,(70,50,1850,150),58,p.INK)
        if name=='shared-pool':
            for x,value,color in [(120,'ChatGPT',p.TEAL),(1220,'Codex',p.BLUE)]:p.box(im,(x,250,x+580,390),color);c.text(im,value,(x+20,270,x+560,365),70,'white');p.arrow(im,[(x+290,410),(x+290,490),(960,590)],color,15)
            p.box(im,(550,640,1370,890),'#D6EAF2',30,p.BLUE,5);c.text(im,'共通の利用枠',(580,690,1340,800),80,p.INK)
        elif name=='instant-bypass':
            p.box(im,(150,260,870,430),p.GREEN);c.text(im,'Instant chat',(175,295,845,395),78,'white');p.box(im,(1080,570,1770,810),'#D6EAF2',25,p.BLUE,5);c.text(im,'共通の利用枠',(1110,630,1740,740),69)
            p.arrow(im,[(510,470),(510,800),(900,800)],p.GREEN,18);c.text(im,'この枠を通らない',(150,860,1010,945),58,p.GREEN)
        else:
            for i,(a,b,color) in enumerate([('提供時期','12月予定',p.TEAL),('開始日・具体枠','今回の本文に記載なし',p.GOLD),('値上げ・実質削減','この説明だけでは断定不可',p.MUTED)]):
                y=245+i*210;p.box(im,(140,y,1780,y+165),'white');c.text(im,a,(170,y+20,800,y+140),58);c.text(im,b,(830,y+20,1750,y+140),54,color)
        c.text(im,'2026年11月2日確認／仕組みの整理。量・消費比率の実測ではありません。',(100,985,1820,1050),34,p.MUTED)
        path=folder/(name+'.jpg');im.save(path,quality=96);paths.append(path)
    return paths,list(c.audit.values())
def main():
    folder=p.OUT/'blog-handoff/v01';images=folder/'images';images.mkdir(parents=True,exist_ok=True);figs,audit=figures(images)
    for name in ['official-heading','official-instant','usage-navigation','usage-heading']:shutil.copy2(p.ASSETS/(name+'.png'),images/(name+'.png'))
    plan=json.loads((p.DEST/'timeline.json').read_text(encoding='utf-8'));qc=json.loads((p.DEST/'qc.json').read_text(encoding='utf-8'));review=json.loads((p.OUT/'_private/ai-listening-v01/review.json').read_text(encoding='utf-8'));assert not review['audible_issues']
    lines=['# YouTubeショート投稿案','',p.SCRIPT['title'],'','Plus・Pro・Businessで、12月からChatGPTとCodexの利用枠を共通化する予定が公式に説明されています。Instant chatはこの枠を消費しません。','Workのエージェント機能の統合、トークンによる計測、Settings → Usageでの確認先を47秒で整理します。','','2026年11月2日に公式本文を確認。正式発表日・具体的な開始日・プラン別の枠量・OS／地域別の展開は、今回の本文に記載されていません。値上げや実質削減とは断定しません。','仕組みの図は上限や消費比率の実測ではありません。設定の入口は現在の実画面で、12月の適用やInstantの消費を実演したものではありません。','','出典：'+p.SCRIPT['source_url'],'','#ChatGPT #Codex #AIニュース']
    (p.HERE/'UPLOAD_TEXT_JA.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    measured=qc['loudness'];layout=json.loads((p.DEST/'text-layout-render.json').read_text(encoding='utf-8'));assert layout and all(x['fits'] for x in layout)
    report=['# v01 検証と残り','','確認日：2026-11-02。技術確認、AIによる点検、人の試聴、採用、公開を分ける。','',f"- 最終MP4：{qc['seconds']}秒、1080×1920・24fps・{qc['frames']}フレーム、H.264／AACステレオ48kHz。全decode通過。",f"- 実測音量：{measured['input_i']} LUFS、true peak {measured['input_tp']} dBTP。共通explanation_v1の発話中減音と頭尾強調を使用。",f"- 最終MP4から25確認画像を取得。文字収まり{len(layout)}項目を確認。製品名の途中分割を避ける字幕調整は3カットのみ再描画、8発話のPCMは再生成せず保持。",'- 台本を渡さない独立AI音声点検でaudible_issuesなし。人の試聴合格とはしない。','- 公式ページの短い引用は計14語。現在の使用状況の個人残量・請求・会話・リセットは公開用から除外。図は模式表現で、12月の変更後の消費実験ではない。','- 記事用の図3点は新規ネイティブ1920×1080で描画。公式・設定の短い切り出し4点は原寸とcropを台帳へ記録し、拡大を新規高解像度撮影と呼ばない。','- 最終試聴・完成品採用・スマホ実機再生・YouTube投稿・ブログ公開は未実施。共有結果は再開記録へ別途追記。']
    (p.HERE/'VALIDATION_JA.md').write_text('\n'.join(report)+'\n',encoding='utf-8')
    for name in ['article-draft.md','SOURCES_JA.md','UPLOAD_TEXT_JA.md','VALIDATION_JA.md']:shutil.copy2(p.HERE/name,folder/name)
    shutil.copy2(p.DEST/'captions.srt',folder/'captions.srt');(folder/'narration-ja.txt').write_text('\n\n'.join(t['speaker']+'：'+t['text'] for t in plan['turns'])+'\n',encoding='utf-8')
    spec=importlib.util.spec_from_file_location('reuse_markdown_html',p.ROOT/'productions/content-projects/CONTENT_20261101_dots_blender_tokyo/package.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);body=module.md_html((folder/'article-draft.md').read_text(encoding='utf-8'))
    (folder/'index.html').write_text('<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ChatGPT・Codex利用枠共通化の記事草稿</title><style>body{max-width:780px;margin:32px auto;padding:0 20px;background:#fafaf6;color:#173246;font:18px/1.9 sans-serif}h1{font-size:30px;line-height:1.5}h2{margin-top:2em;font-size:25px}figure{margin:1.5em 0}img{max-width:100%;height:auto}a{color:#087e82;overflow-wrap:anywhere}</style>'+body+'</html>',encoding='utf-8')
    manifest=[dict(path=x.relative_to(folder).as_posix(),bytes=x.stat().st_size,sha256=p.sha(x),size=list(Image.open(x).size)) for x in sorted(images.iterdir())];p.save(folder/'asset-manifest.json',dict(images=manifest,private_originals_included=False,official_quoted_words=14));p.save(p.OUT/'article-text-layout.json',audit)
    (folder/'README_JA.md').write_text('# 記事・画像・字幕のレビュー用\n\nindex.htmlが記事草稿。図3点・短い公式引用2点・現在の設定入口2点、読み原稿、字幕、投稿文、出典と検証要約を含む。私的原本、API応答、動画、音声、署名URLは含めない。blogを基本に準備し、MDX組込・ブログ固有の案内役・掲載先のスマホ表示・最終採用と公開は別。\n',encoding='utf-8')
    files=sorted(x for x in folder.rglob('*') if x.is_file() and x.name!='MANIFEST.sha256');entries='\n'.join(hashlib.sha256(x.read_bytes()).hexdigest()+'  '+x.relative_to(folder).as_posix() for x in files)+'\n';(folder/'MANIFEST.sha256').write_text(entries,encoding='utf-8');target=p.OUT/'blog-handoff/chatgpt-codex-shared-usage-article-v01.zip'
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
        for x in sorted(folder.rglob('*')):
            if x.is_file():z.write(x,x.relative_to(folder).as_posix())
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None
        for line in entries.splitlines():digest,name=line.split('  ',1);assert hashlib.sha256(z.read(name)).hexdigest()==digest
        count=len(z.namelist())
    p.save(p.OUT/'blog-handoff/verification-v01.json',dict(file=p.rec(target),members=count,all_member_hashes_verified=True,crc_verified=True,private_originals_included=False));print('article images',len(manifest),'ZIP members',count,flush=True)
if __name__=='__main__':main()
