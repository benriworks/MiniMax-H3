"""Offline article-review PDF with fixed-size figures that move together."""
import hashlib
import json
import re
import sys
from pathlib import Path

import fitz

from produce import OUT

sys.path.insert(0, str(OUT / '_private/pdf-lib'))
from bs4 import BeautifulSoup
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, KeepTogether, LongTable, TableStyle


def build(article_version='v03', pdf_version='v04'):
    folder = OUT / 'article' / article_version
    review = OUT / 'review' / article_version
    review.mkdir(parents=True, exist_ok=True)
    target = review / ('08_記事草稿_図入り_'+pdf_version+'.pdf')
    if target.exists():
        raise RuntimeError('Keep the completed PDF; use a new revision for changes')
    soup = BeautifulSoup((folder / 'index.html').read_text(encoding='utf-8'), 'html.parser')
    pdfmetrics.registerFont(TTFont('ReviewJapanese', r'C:\Windows\Fonts\meiryo.ttc', subfontIndex=0))
    styles = {key: ParagraphStyle(key, fontName='ReviewJapanese', fontSize=size, leading=leading,
                                textColor=colors.HexColor('#173246'), spaceAfter=10, wordWrap='CJK',
                                keepWithNext=key in {'h1', 'h2'})
              for key, size, leading in [('p',10,18),('h1',19,29),('h2',14,23),('caption',8,13),('cell',9,15)]}
    width = fitz.paper_rect('a4').width - 84
    def markup(node):
        for a in node.find_all('a'):
            a['href'] = a.get('href', '')
            a['color'] = '#087e82'
        return node.decode_contents().replace('<br/>', '<br/>')
    flow = []
    for element in soup.main.find_all(recursive=False):
        if element.name in {'h1','h2','p'}:
            flow.append(Paragraph(markup(element), styles[element.name]))
        elif element.name == 'figure':
            source = folder / element.img['src']
            with fitz.open(source) as image_doc:
                pix = image_doc[0].get_pixmap()
                picture_width = min(width, 285) if .95 < pix.width / pix.height < 1.05 else width
                height = picture_width * pix.height / pix.width
            # Keep the actual desired dimensions: defer the figure to the next
            # page instead of squeezing it into the remaining page height.
            picture = Image(str(source), width=picture_width, height=height)
            caption = Paragraph(markup(element.figcaption), styles['caption'])
            flow.extend([KeepTogether([picture, Spacer(1,6), caption]), Spacer(1,12)])
        elif element.name == 'table':
            rows = [[Paragraph(markup(cell), styles['cell']) for cell in row.find_all(['th','td'])]
                    for row in element.find_all('tr')]
            table = LongTable(rows, colWidths=[width*.23,width*.385,width*.385], repeatRows=1)
            table.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.5,colors.HexColor('#c6d7dc')),
                                      ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#edf4f4')),
                                      ('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),7),
                                      ('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),7),
                                      ('BOTTOMPADDING',(0,0),(-1,-1),7)]))
            flow.extend([table,Spacer(1,12)])
    def page_number(canvas, document):
        canvas.setFont('ReviewJapanese',8)
        canvas.drawRightString(width+42,22,str(document.page))
    document = SimpleDocTemplate(str(target), pagesize=tuple(fitz.paper_rect('a4'))[2:],
                                 leftMargin=42,rightMargin=42,topMargin=40,bottomMargin=40,
                                 title='記事草稿：BERT・GPTが生まれるまで',author='BenriWorks Lab')
    document.build(flow,onFirstPage=page_number,onLaterPages=page_number)
    with fitz.open(target) as checked:
        text = ''.join(page.get_text() for page in checked)
        assert 'BERT' in text and 'GPT' in text and '言葉' in text
        counts = [len(page.get_images()) for page in checked]
        for number in sorted({0, len(checked) // 2, len(checked) - 1}):
            checked[number].get_pixmap(matrix=fitz.Matrix(1.4, 1.4)).save(review / f'article-pdf-page-{number + 1}.png')
        result = dict(file=target.name, bytes=target.stat().st_size,
                      sha256=hashlib.sha256(target.read_bytes()).hexdigest(), pages=len(checked),
                      japanese_text_extractable=True, image_instances=sum(counts), images_per_page=counts,
                      generation='Offline ReportLab, embedded Japanese font; fixed-size figures; browser and mobile not verified')
        for page in checked:
            for image in page.get_image_info():
                bbox = fitz.Rect(image['bbox'])
                square=.95 < image['width']/image['height'] < 1.05
                assert bbox.width > (280 if square else 490), 'Unexpected squeezed figure'
    (review / ('article-pdf-checks-'+pdf_version+'.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--article-version',default='v03');parser.add_argument('--pdf-version',default='v04');args=parser.parse_args()
    build(args.article_version,args.pdf_version)
