"""Measured Japanese text and small raster primitives for exported explainer frames."""
from pathlib import Path
from functools import lru_cache
import math,re
from PIL import Image,ImageDraw,ImageFont,ImageOps
from .text_layout import visible_glyph_bbox
ROOT=Path(__file__).resolve().parents[2]
FONT=ROOT/'studio/public/template-assets/NotoSansJP-Variable.ttf'
INK='#173246';TEAL='#087E82';BG='#F7F4EC'
@lru_cache(maxsize=45)
def font(size):
    f=ImageFont.truetype(str(FONT),size);f.set_variation_by_axes([650]);return f
@lru_cache(maxsize=4000)
def glyph(text,size,color):
    b=visible_glyph_bbox(text,font(size));tile=Image.new('RGBA',(b[2]-b[0]+2,b[3]-b[1]+2));ImageDraw.Draw(tile).text((-b[0],-b[1]),text,font=font(size),fill=color);return tile
def wrap(text,limit):
    lines=[]
    while len(text)>limit:
        cut=limit
        for mark in '、。？！':
            k=text.rfind(mark,max(3,limit//2),limit+1)
            if k>=max(3,limit//2):cut=k+1;break
        if cut<len(text) and text[cut-1].isascii() and text[cut].isascii() and text[cut-1].isalnum() and text[cut].isalnum():
            word=re.search(r'[A-Za-z0-9]+$',text[:cut])
            if word and word.start()>=3:cut=word.start()
        lines.append(text[:cut]);text=text[cut:]
    return lines+([text] if text else [])
class Canvas:
    def __init__(self):self.audit={}
    def text(self,im,value,rect,size=54,color=INK,center=True):
        tiles=[glyph(s,size,color) for s in value.split('\n')];gap=round(size*.26);height=sum(t.height for t in tiles)+gap*(len(tiles)-1)
        max_width=max(t.width for t in tiles)
        if max_width>rect[2]-rect[0] or height>rect[3]-rect[1]:raise ValueError(f'Text overflow: {value!r} in {rect} at {size}px')
        y=rect[1]+((rect[3]-rect[1]-height)/2 if len(tiles)==1 else 6)
        for tile in tiles:
            x=rect[0]+(rect[2]-rect[0]-tile.width)/2 if center else rect[0];im.paste(tile,(round(x),round(y)),tile);y+=tile.height+gap
        self.audit[(value,tuple(rect),size)]=dict(text=value,rect=rect,size=size,max_ink_width=max_width,ink_height=height,fits=True)
def box(im,rect,color,radius=24,outline=None,width=3):ImageDraw.Draw(im).rounded_rectangle(tuple(round(x) for x in rect),radius=radius,fill=color,outline=outline,width=width)
def fit(im,src,rect,cover=False):
    size=(rect[2]-rect[0],rect[3]-rect[1]);tile=ImageOps.fit(src,size,method=Image.Resampling.BICUBIC) if cover else ImageOps.contain(src,size,Image.Resampling.BICUBIC)
    im.paste(tile,(round((rect[0]+rect[2]-tile.width)/2),round((rect[1]+rect[3]-tile.height)/2)))
def arrow(im,points,color=TEAL,width=10):
    d=ImageDraw.Draw(im);points=[tuple(round(v) for v in p) for p in points];d.line(points,fill=color,width=width,joint='curve');a,b=points[-2:];angle=math.atan2(b[1]-a[1],b[0]-a[0]);r=23
    d.polygon([b,(b[0]-r*math.cos(angle-.55),b[1]-r*math.sin(angle-.55)),(b[0]-r*math.cos(angle+.55),b[1]-r*math.sin(angle+.55))],fill=color)
