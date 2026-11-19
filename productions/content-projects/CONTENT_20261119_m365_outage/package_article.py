"""Build a three-page linked PDF and a portable article handoff from the verified cut."""
import argparse
from hashlib import sha256
from html import escape
import json
import os
from pathlib import Path
import re
from zipfile import ZipFile, ZIP_DEFLATED
from xml.sax.saxutils import quoteattr

from markdown_it import MarkdownIt
from PIL import Image
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph, Table, TableStyle

HERE=Path(__file__).resolve().parent
SLUG="microsoft-365-outage-november-2026"
FIGS={"teams":"Teamsの通信がExchangeと同じゲートウェイに切り替わる経路。",
      "cascade":"応答しないサーバーから振り替えた通信で、残るサーバーも詰まる過程。"}
SHORT={"PIR":"Microsoft暫定報告（公開写し）","EVP":"Microsoft担当役員の説明","MEIJI":"明治薬科大学",
       "FEED":"Microsoft障害通知（大学掲載）","RELEASE":"Microsoft公表案内","RITS":"立命館大学",
       "OSAKA":"大阪医科薬科大学","LEMONDE":"Le Mondeの取材"}
SOURCES=json.loads((HERE/"sources.json").read_text(encoding="utf-8"))


def portable(text):
    for key,(name,url,kind) in SOURCES.items():
        text=text.replace(f"[{name}]({url})",f"[{SHORT[key]}]({url})")
    return text


def rich(text):
    # All input is editorial text from the companion Markdown, never remote HTML.
    text=escape(text)
    text=re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)",r'<a href="\2" color="#08716B"><u>\1</u></a>',text)
    return re.sub(r'\*\*(.+?)\*\*',r'<font color="#085954">\1</font>',text)


def article_pdf(path,pages,figures,descriptions=None):
    descriptions=FIGS if descriptions is None else descriptions
    fonts=Path(os.environ["WINDIR"])/"Fonts"
    pdfmetrics.registerFont(TTFont("ArticleJP",str(fonts/"BIZ-UDGothicR.ttc"),subfontIndex=1))
    pdfmetrics.registerFont(TTFont("ArticleJP-Bold",str(fonts/"BIZ-UDGothicB.ttc"),subfontIndex=1))
    styles={}
    for key,size,leading,col in [("main",27,38,"#173A3C"),("h2",17,26,"#145B59"),("body",12.8,20,"#183438"),("caption",10,15,"#486365"),("cell",10.8,16,"#183438")]:
        face="ArticleJP-Bold" if key in {"h2","main"} else "ArticleJP"
        styles[key]=ParagraphStyle(key,fontName=face,fontSize=size,leading=leading,textColor=colors.HexColor(col),wordWrap="CJK",alignment=TA_LEFT)
    canv=Canvas(str(path),pagesize=A4,pageCompression=1)
    canv.setTitle("Outlookの受信箱が開かなかった日")
    w,h=A4; left=46; width=w-left*2
    heights=[]
    for num,section in enumerate(pages,1):
        canv.setFillColor(colors.HexColor("#F9F8F3"));canv.rect(0,0,w,h,fill=1,stroke=0)
        canv.setFillColor(colors.HexColor("#086866"));canv.rect(0,h-9,w,9,fill=1,stroke=0)
        canv.setFont("ArticleJP",9);canv.drawString(left,h-36,"Microsoft 365  ／  2026年11月の障害記録")
        canv.drawRightString(w-left,h-36,"11月19日 調査  ／  暫定報告に基づく")
        canv.setStrokeColor(colors.HexColor("#BECAC3"));canv.line(left,h-47,w-left,h-47)
        y=h-63; table=[]
        def drawpara(text,style,space):
            nonlocal y
            para=Paragraph(rich(text),styles[style]);_,ph=para.wrap(width,900)
            y-=ph;para.drawOn(canv,left,y);y-=space
        def drawtable():
            nonlocal y,table
            if not table:return
            rows=[[Paragraph(rich(c),styles["cell"]) for c in row] for row in table]
            block=Table(rows,colWidths=[114,width-114],hAlign="LEFT")
            block.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#DCECE5")),
                ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.HexColor("#FFFFFF"),colors.HexColor("#F1F4EE")]),
                ("VALIGN",(0,0),(-1,-1),"MIDDLE"),("LEFTPADDING",(0,0),(-1,-1),8),
                ("RIGHTPADDING",(0,0),(-1,-1),8),("TOPPADDING",(0,0),(-1,-1),6),
                ("BOTTOMPADDING",(0,0),(-1,-1),6)]))
            _,th=block.wrapOn(canv,width,900);y-=th;block.drawOn(canv,left,y);y-=11;table=[]
        for line in section.splitlines():
            line=line.strip()
            if line.startswith("|"):
                if not re.match(r"^\|[ \-:|]+$",line):
                    table.append([t.strip() for t in line.strip("|").split("|")])
                continue
            drawtable()
            if not line: continue
            if line.startswith("<!-- figure:"):
                key=line.split(":")[1].split()[0]
                fig=figures[key]; iw,ih=Image.open(fig).size
                fh=width*ih/iw; y-=fh
                # ReportLab handles the PNG copy reliably across Pillow versions.
                with Image.open(fig) as img: canv.drawInlineImage(img.convert("RGB"),left,y,width,fh)
                y-=5;drawpara(descriptions[key],"caption",8)
            elif line.startswith("# "): drawpara(line[2:],"main",6)
            elif line.startswith("## "): drawpara(line[3:],"h2",6)
            else: drawpara(line,"body",9)
        drawtable(); heights.append(round(y,1))
        if y<44:raise ValueError(f"Page {num} exceeds the bottom margin ({y:.1f} pt)")
        canv.setStrokeColor(colors.HexColor("#BECAC3"));canv.line(left,38,w-left,38)
        canv.setFillColor(colors.HexColor("#486365"));canv.setFont("ArticleJP",8)
        canv.drawString(left,23,"EX1550543  /  MO1550821");canv.drawRightString(w-left,23,f"{num} / {len(pages)}")
        canv.showPage()
    canv.save();print("PDF lower margins",heights)


def main():
    ap=argparse.ArgumentParser();ap.add_argument("media",type=Path);ap.add_argument("--pair",action="store_true");args=ap.parse_args()
    media=args.media.resolve(); out=media/"article";out.mkdir(exist_ok=True)
    if args.pair:
        out=out/"v02";out.mkdir(exist_ok=True)
    target=out/"figures";target.mkdir(exist_ok=True)
    figures={}
    for key in FIGS:
        dest=target/(key+".webp")
        with Image.open(media/"preflight/v02"/(key+"-last.jpg")) as im:
            im.crop((108,294,1812,792)).save(dest,quality=94)
        figures[key]=dest
    txt=(HERE/"article-draft.md").read_text(encoding="utf-8")
    descriptions=dict(FIGS)
    if args.pair:
        txt+="\n<!-- page -->\n"+(HERE/"article-pair-addendum.md").read_text(encoding="utf-8")
        descriptions.update({"keynote-quote":"Microsoft Igniteの公式講演録から。2026年11月17日、1ページ目。",
                             "status":"Microsoftの公開サービス状態ページ。2026年11月19日撮影。"} )
        for key in ("keynote-quote","status"):
            figures[key]=target/(key+".webp")
            with Image.open(media/"captures/revision-03"/(key+".png")) as im:im.save(figures[key],lossless=True)
    condensed=portable(txt)
    article_pdf(out/"microsoft365-outage-article.pdf",condensed.split("<!-- page -->"),figures,descriptions)
    web=condensed.replace("<!-- page -->","")
    mdx=web
    for key,alt in descriptions.items():
        with Image.open(figures[key]) as pic:width,height=pic.size
        tag="<!-- figure:"+key+" -->"
        web=web.replace(tag,f'<figure><img src="figures/{key}.webp" width="{width}" height="{height}" alt={quoteattr(alt)}><figcaption>{alt}</figcaption></figure>')
        mdx=mdx.replace(tag,f'<Figure src="/images/articles/{SLUG}/{key}.webp" width={{{width}}} height={{{height}}} alt={quoteattr(alt)} caption={quoteattr(alt)} zoom />')
    rendered=MarkdownIt("commonmark",{"html":True}).enable("table").render(web)
    css="body{max-width:790px;margin:32px auto;padding:0 20px 60px;color:#183438;background:#f9f8f3;font:17px/1.85 system-ui,sans-serif}h1,h2{line-height:1.4}h2{margin-top:2em;color:#145b59}figure{margin:18px 0}img{width:100%;height:auto}figcaption{font-size:14px}a{color:#08645e}td,th{padding:5px;border-bottom:1px solid #b7c6bf;text-align:left}td:first-child{min-width:6.2em}table{border-collapse:collapse}"
    (out/"index.html").write_text('<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Outlookの受信箱が開かなかった日</title><style>'+css+"</style><main>"+rendered+"</main></html>",encoding="utf-8")
    head="---\nslug: "+SLUG+"\ntitle: Outlookの受信箱が開かなかった日。2026年11月のMicrosoft 365障害\ncontentType: development\npublishedAt: 2026-11-19\nupdatedAt: 2026-11-19\ndraft: true\ntopics: [business-efficiency]\n---\n"
    (out/(SLUG+".mdx")).write_text(head+mdx.split("\n",1)[1],encoding="utf-8")
    files={p.relative_to(out).as_posix():p for p in [out/"index.html",out/(SLUG+".mdx"),out/"microsoft365-outage-article.pdf",*figures.values()]}
    for key,path in figures.items():files[f"public/images/articles/{SLUG}/{key}.webp"]=path
    files["sources.md"]=HERE/"SOURCES_JA.md"
    digest=lambda data:sha256(data).hexdigest()
    manifest={name:digest(src.read_bytes()) for name,src in files.items()}
    with ZipFile(out/"blog-review.zip","w",ZIP_DEFLATED) as zipout:
        for name,src in files.items():zipout.write(src,name)
        zipout.writestr("sha256.json",json.dumps(manifest,indent=2)+"\n")
    with ZipFile(out/"blog-review.zip") as z:
        assert z.testzip() is None and all(digest(z.read(name))==val for name,val in manifest.items())
    print("Verified",len(manifest),"package members plus manifest")


if __name__=="__main__": main()
