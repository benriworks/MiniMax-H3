"""Readable offline article review PDF; contains public candidate images only."""
from pathlib import Path
import re
from markdown_it import MarkdownIt
from PIL import Image as PILImage
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Image, Spacer, HRFlowable

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
OUT = ROOT / 'outputs/content-projects' / HERE.name / 'blog-handoff/v02'


def build():
    target = OUT / 'dots-cloud-desktop-article-v03.pdf'
    if target.exists():
        raise ValueError('Keep old review PDF')
    pdfmetrics.registerFont(TTFont('JP', 'C:/Windows/Fonts/meiryo.ttc', subfontIndex=0))
    pdfmetrics.registerFont(TTFont('JPBold', 'C:/Windows/Fonts/meiryob.ttc', subfontIndex=0))
    pdfmetrics.registerFontFamily('JP', normal='JP', bold='JPBold', italic='JP', boldItalic='JPBold')
    body = ParagraphStyle('body', fontName='JP', fontSize=10.5, leading=18, textColor=HexColor('#233a32'),
        wordWrap='CJK', spaceAfter=10, allowWidows=0, allowOrphans=0)
    h1 = ParagraphStyle('title', parent=body, fontName='JPBold', fontSize=21, leading=32, spaceAfter=22, keepWithNext=True)
    h2 = ParagraphStyle('section', parent=body, fontName='JPBold', fontSize=15, leading=25, spaceBefore=18, spaceAfter=12, keepWithNext=True)
    caption = ParagraphStyle('caption', parent=body, fontSize=8.5, leading=15, textColor=HexColor('#536a60'))
    parser = MarkdownIt('commonmark', {'html': False})
    source = (OUT / 'article-draft-v03.md').read_text(encoding='utf-8').replace('――', ' - ')
    tokens = parser.parse(source)
    content = []
    current = body
    for token in tokens:
        if token.type == 'heading_open':
            current = h1 if token.tag == 'h1' else h2
        elif token.type == 'paragraph_open':
            current = body
        elif token.type == 'hr':
            content.append(HRFlowable(width='100%', color=HexColor('#c1d0c6'), spaceBefore=16, spaceAfter=16))
        elif token.type == 'inline':
            pictures = [child for child in token.children or [] if child.type == 'image']
            if pictures:
                for picture in pictures:
                    path = (OUT / picture.attrGet('src')).resolve(strict=True)
                    assert path.is_relative_to(OUT)
                    with PILImage.open(path) as image:
                        width, height = image.size
                    ratio = min(1, 463 / width, 350 / height)
                    content.append(Image(str(path), width=width*ratio, height=height*ratio))
                    content.append(Spacer(1, 8))
                    content.append(Paragraph(picture.content, caption))
            else:
                html = parser.renderer.renderInline(token.children or [], parser.options, {})
                html = html.replace('<strong>', '<b>').replace('</strong>', '</b>')
                html = re.sub(r'<code>(.*?)</code>', r'<font name="JP">\1</font>', html)
                content.append(Paragraph(html, current))
    def decorate(canvas, doc):
        canvas.saveState()
        canvas.setFont('JP', 8)
        canvas.setFillColor(HexColor('#536a60'))
        canvas.drawString(42, A4[1]-28, 'dotsクラウドデスクトップ / 記事草稿v03 / 未公開')
        canvas.drawRightString(A4[0]-42, 24, str(doc.page))
        canvas.restoreState()
    doc = SimpleDocTemplate(str(target), pagesize=A4, leftMargin=48, rightMargin=48, topMargin=48, bottomMargin=44,
        title='dotsクラウドPC - 操作交代・Blender・Excel入力の記事草稿', author='BenriWorks')
    doc.build(content, onFirstPage=decorate, onLaterPages=decorate)
    print(target)


if __name__ == '__main__':
    build()
