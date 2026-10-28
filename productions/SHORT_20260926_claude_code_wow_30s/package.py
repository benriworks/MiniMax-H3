from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, shutil, sys, zipfile

PROD=Path(__file__).resolve().parent
ROOT=PROD.parents[1]
out=Path(sys.argv[1]).resolve(strict=True)
assert out.is_relative_to(ROOT/'outputs/productions'/PROD.name)
def record(p):
    return {'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest().upper()}
verified=json.loads((out/'verification.json').read_text(encoding='utf-8'))
assert verified['review_status']=='verified_candidate_awaiting_user_review'
assert record(out/'claude-code-wow-30s.mp4')['sha256']==verified['delivery']['sha256']
shutil.copyfile(out/'design-72.png',out/'cover.png')
description='''タイトル案
Claude Code、何がすごい？「つくりたい」が動き出す30秒

概要欄
日本語で依頼して、ファイルを編集。エラー修正やテストまで。
Claude Codeで進める開発の流れを、30秒の図解にしました。
まずは、小さなアプリから。最後は自分で変更内容と動作を確認しましょう。

非公式の紹介動画です。開発画面は説明用の図解で、実操作の録画や所要時間の実測ではありません。
人物映像はオリジナルの生成キャラクター素材です。

公式出典（2026-09-26確認）
https://code.claude.com/docs/en/overview

#ClaudeCode #AI開発 #プログラミング #Shorts
'''
(out/'YOUTUBE_JA.txt').write_text(description,encoding='utf-8')
(out/'README_JA.txt').write_text('''Claude Code、何がすごい？ 30秒ショート

claude-code-wow-30s.mp4：完成候補（ナレーション・BGM・字幕あり）
cover.png：カバー画像
captions.srt：ナレーションの字幕ファイル
YOUTUBE_JA.txt：タイトル・概要欄案と公式出典
story.json：台本
SOURCES_JA.md：出典と表現範囲
verification.json：形式・音量・目視の検証記録

1080×1920、24fps、30秒、H.264／AAC 48kHz。
声はMicrosoft Sayaka、速度1。男女キャラクターは既存MiniMax H3素材。
中盤は独自の図解アニメーション。BGM・切り替え音は今回用の独自合成音源。
利用者指定により、動画とカバーには生成ツール名のテロップを表示しません。
技術と目視確認済み。利用者による採用・聴感の最終確認待ち。YouTubeへの投稿はしていません。
''',encoding='utf-8')
html='''<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Claude Code、何がすごい？</title>
<style>*{box-sizing:border-box}body{margin:0;background:#101c29;color:#fff8ec;font-family:"Yu Gothic UI","Meiryo",sans-serif}main{max-width:1000px;margin:auto;padding:32px 22px;display:grid;grid-template-columns:minmax(260px,390px) 1fr;gap:36px}video{width:100%;max-height:82vh;background:#09131d;border-radius:18px}h1{font-size:34px;line-height:1.4}p,li{font-size:18px;line-height:1.8}a{color:#ffcb9d}.buttons{display:flex;flex-wrap:wrap;gap:12px}.buttons a{padding:12px 18px;background:#263b4c;border-radius:12px;text-decoration:none}.note{color:#b7c7ce;font-size:16px}@media(max-width:720px){main{grid-template-columns:1fr}video{max-height:70vh}h1{font-size:28px}}</style>
<main><video controls playsinline preload="metadata" poster="cover.png" src="claude-code-wow-30s.mp4"></video><section><p style="color:#a9f0d2">30秒ショート ／ 1080×1920</p><h1>Claude Code、<br>何がすごい？</h1><p>日本語で依頼し、まとめて編集。<br>エラー修正とテスト、対話での仕上げまで。</p><div class="buttons"><a href="claude-code-wow-30s.mp4" download>動画を保存</a><a href="claude-code-wow-30s-review.zip" download>一式を保存</a></div><ul><li>これまでの男女キャラクターを使用</li><li>大きな文字・ナレーション・BGM付き</li><li>開発の流れは図解で紹介</li></ul><p><a href="YOUTUBE_JA.txt">YouTube用のタイトル・概要欄案</a><br><a href="captions.srt" download>字幕を保存</a></p><p class="note">非公式の解説。図解は実操作の録画ではありません。<br>出典：<a href="https://code.claude.com/docs/en/overview">Claude Code公式ドキュメント</a></p></section></main></html>'''
(out/'index.html').write_text(html,encoding='utf-8')
files={n:out/n for n in ['claude-code-wow-30s.mp4','cover.png','captions.srt','YOUTUBE_JA.txt','README_JA.txt','verification.json']}
files.update({'story.json':PROD/'story.json','SOURCES_JA.md':PROD/'SOURCES_JA.md'})
manifest={n:record(p) for n,p in files.items()}
bundle=out/'claude-code-wow-30s-review.zip'
with zipfile.ZipFile(bundle,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=3) as z:
    for n,p in files.items():z.write(p,n)
    z.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
with zipfile.ZipFile(bundle) as z:
    assert z.testzip() is None and set(z.namelist())==set(files)|{'manifest.json'}
    for n,item in manifest.items():
        b=z.read(n)
        assert len(b)==item['bytes'] and hashlib.sha256(b).hexdigest().upper()==item['sha256']
result={'verified_at':datetime.now(timezone.utc).isoformat(),'zip':record(bundle),'entries':len(files)+1,'crc_and_hashes_verified':True,'review_page':record(out/'index.html')}
(out/'package-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result))
