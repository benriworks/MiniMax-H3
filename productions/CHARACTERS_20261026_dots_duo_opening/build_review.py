"""Package the reviewed motion trial without changing the completed long-form."""
from pathlib import Path
import hashlib,json,subprocess
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'outputs/characters/dots-duo-opening-20261026/v01'


def main():
    proof=json.loads((OUT/'entrance/verification.json').read_text(encoding='utf-8'))
    raw=ROOT/proof['artifact']['path']
    if hashlib.sha256(raw.read_bytes()).hexdigest().upper()!=proof['artifact']['sha256']:
        raise ValueError('Changed generation')
    dest=OUT/'dots-duo-opening-v01.mp4'
    if dest.exists():raise ValueError('Preserve old review before replacing')
    subprocess.run(['ffmpeg','-v','error','-nostdin','-n','-i',str(raw),'-an','-c:v','copy',
        '-movflags','+faststart',str(dest)],check=True)
    subprocess.run(['ffmpeg','-v','error','-nostdin','-xerror','-i',str(dest),'-f','null','-'],check=True)
    entries=[]
    for path in sorted((OUT/'keyframes').glob('*.png')):
        entries.append(dict(path=path.relative_to(ROOT).as_posix(),bytes=path.stat().st_size,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),source='imagegen using existing fictional adult references',
            article_use='optional illustration candidate; not an actual product screen'))
    manifest=dict(created_at=datetime.now(timezone.utc).isoformat(),assets=entries,
        original_article='productions/LONG_20261026_dots_transfer_detail/article-draft-v01.md',
        article_text_changed=False,new_app_capture='not applicable; this revision only stages existing fictional characters',
        new_official_quotes='not applicable; no product claims added')
    (OUT/'article-reuse-candidates.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'index.html').write_text('''<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>dotsの2人・待ち合わせカット v01</title><style>body{max-width:1100px;margin:30px auto;padding:18px;background:#071026;color:#fafafa;font:18px/1.8 system-ui}video,img{max-width:100%}a{color:#8fd8ff}</style>
<h1>dotsの2人が待ち合わせる冒頭カット</h1><p>男の子が中央左で待ち、女の子が右から走り込み、中央右で止まって顔を合わせる約5秒の動作試作です。人物は架空の成人です。</p>
<video src="dots-duo-opening-v01.mp4" controls playsinline loop preload="metadata" poster="keyframes/start.png"></video>
<p>台詞なし・ミュート。生成原寸1024×576、24fps、124フレーム。高解像度の完成版ではありません。顔の一貫性・入ってくる方向・止まる位置・二人の関係をご確認ください。</p>
<p>既存の4分40秒版は保持しています。人物カットの採用と本編への最終反映は別記録です。記事本文は既存草稿を維持し、立ち姿は追加の挿絵候補として保存しました。</p>
<details><summary>0.5秒ごとの確認画像</summary><img src="entrance/contact-sheet.jpg"></details>
''',encoding='utf-8')
    (OUT/'review-packaging.json').write_text(json.dumps(dict(path=dest.relative_to(ROOT).as_posix(),
        bytes=dest.stat().st_size,sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),
        full_decode_verified=True,muted=True,native_width=1024,native_height=576,
        visual_review='pending',user_approved=False,long_form_replaced=False),indent=2),encoding='utf-8')
    print(dest)


if __name__=='__main__':main()
