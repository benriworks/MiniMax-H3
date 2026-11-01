"""CPU-authored celebration bloom and an unobstructed 10-second YouTube end slate.

These are video artwork and placement guides, not clickable YouTube elements.
"""
import math
from functools import lru_cache
import numpy as np
from PIL import Image,ImageDraw,ImageFilter,ImageChops

END_SCREEN_LAYOUT=dict(
    width=1920,height=1080,seconds=10.0,
    videos=[dict(id='related_left',rect=[148,430,708,745]),dict(id='related_right',rect=[1212,430,1772,745])],
    subscribe=dict(center=[960,590],radius=120),
    requires_youtube_studio_elements=True)

@lru_cache(maxsize=4)
def _particles(seed):
    rng=np.random.default_rng(seed)
    return rng.random((340,8))

def celebration_layer(seconds,*,bounds=(335,282,1585,837),faces=(),size=(1920,1080)):
    """Gold/pearl flowing ribbons, bokeh and glints; soft exclusion around faces."""
    width,height=size;scale=1.0;sw,sh=round(width*scale),round(height*scale)
    layer=Image.new('RGBA',(sw,sh));d=ImageDraw.Draw(layer);t=seconds
    haze=Image.new('RGBA',(sw,sh));hd=ImageDraw.Draw(haze)
    x1,y1,x2,y2=[v*scale for v in bounds]
    colors=[(255,204,102),(255,239,188),(255,255,239),(135,232,238)]
    for i,v in enumerate(_particles(2026110102)):
        life=4+v[2]*5;phase=(t/life+v[1])%1
        x=x1+v[0]*(x2-x1)+math.sin(t*.6+v[3]*math.tau)*18
        y=y2-phase*(y2-y1);alpha=(math.sin(math.pi*phase)**.8)*(80+v[4]*140)
        color=colors[min(3,int(v[5]*3.25))]
        radius=(1.2+v[6]*2) if i<270 else 6+v[6]*16
        if i>=270:alpha*=.24
        (d if i<270 else hd).ellipse((x-radius,y-radius,x+radius,y+radius),fill=(*color,round(alpha)))
        if i<90:d.line((x,y+3+v[7]*7,x+1.4,y),fill=(*color,round(alpha*.45)),width=1)
    # Two luminous comet ribbons travel around the subjects rather than through text.
    for ribbon in range(2):
        for k in range(74):
            a=t*.48+ribbon*math.pi-k*.014
            xx=960+600*math.cos(a);yy=560+256*math.sin(a)
            aa=1-k/74;color=(255,219,142,round(aa**1.6*155))
            rr=1.5+aa*2.0;d.ellipse((xx-rr,yy-rr,xx+rr,yy+rr),fill=color)
        a=t*.48+ribbon*math.pi;xx=960+600*math.cos(a);yy=560+256*math.sin(a)
        d.polygon([(xx-37,yy),(xx-4,yy-3),(xx,yy-20),(xx+4,yy-3),(xx+37,yy),(xx+4,yy+3),(xx,yy+20),(xx-4,yy+3)],fill=(255,247,216,225))
    for i,v in enumerate(_particles(2026110103)[:20]):
        x=x1+v[0]*(x2-x1);y=y1+v[1]*(y2-y1)
        pulse=.5+.5*math.sin(t*(1.1+v[2])+(v[3]*math.tau));a=round(70+170*pulse);r=5+13*pulse
        points=[]
        for k in range(8):
            angle=k*math.pi/4;rad=r if k%2==0 else r*.19
            points.append((x+math.cos(angle)*rad,y+math.sin(angle)*rad))
        d.polygon(points,fill=(255,249,217,a));d.ellipse((x-1.2,y-1.2,x+1.2,y+1.2),fill=(255,255,255,a))
    glow=layer.filter(ImageFilter.GaussianBlur(9.6));glow=Image.blend(Image.new('RGBA',glow.size),glow,.75)
    combined=Image.alpha_composite(Image.alpha_composite(haze.filter(ImageFilter.GaussianBlur(5)),glow),layer)
    mask=Image.new('L',(sw,sh));md=ImageDraw.Draw(mask)
    md.rectangle((x1,y1,x2,y2),fill=255)
    for rect in faces:md.ellipse(tuple(v*scale for v in rect),fill=0)
    mask=mask.filter(ImageFilter.GaussianBlur(14))
    # Reapply the exact panel boundary after feathering to protect header/captions.
    clip=Image.new('L',(sw,sh));ImageDraw.Draw(clip).rectangle((x1,y1,x2,y2),fill=255)
    alpha=ImageChops.multiply(combined.getchannel('A'),ImageChops.multiply(mask,clip))
    combined.putalpha(alpha)
    return combined.resize((width,height),Image.Resampling.BICUBIC)

def end_screen(seconds,*,label):
    """Two 16:9 reserved video areas plus a centered subscription area."""
    im=Image.new('RGB',(1920,1080),'#0C1C31');d=ImageDraw.Draw(im)
    for y in range(1080):
        z=y/1080;d.line((0,y,1920,y),fill=(round(12+8*z),round(28+13*z),round(49+14*z)))
    # Restrained floating ambience. Reserved areas are painted opaque afterward.
    glow=Image.new('RGBA',im.size);gd=ImageDraw.Draw(glow)
    for v in _particles(2026110104)[:55]:
        x=v[0]*1920+math.sin(seconds*.16+v[1]*6)*20
        y=(v[2]*1080-seconds*(2+v[3]*5))%1080;r=6+v[4]*24
        gd.ellipse((x-r,y-r,x+r,y+r),fill=(255,214,139,round(9+v[5]*15)))
    im=Image.alpha_composite(im.convert('RGBA'),glow.filter(ImageFilter.GaussianBlur(9))).convert('RGB');d=ImageDraw.Draw(im)
    label(im,'ご視聴ありがとうございました',(180,125,1740,230),66,'#FFF2D3')
    label(im,'Codex・ChatGPTを、毎日の仕事へ。',(230,260,1690,330),40,'#BBD7E5')
    for item,title in zip(END_SCREEN_LAYOUT['videos'],['次の動画はこちら','こちらもおすすめ']):
        x,y,x2,y2=item['rect']
        d.rounded_rectangle((x-8,y-8,x2+8,y2+8),radius=22,fill='#142B42',outline='#41677A',width=2)
        d.rectangle((x,y,x2,y2),fill='#10243A')
        label(im,title,(x-20,345,x2+20,405),41,'#E5F3F4')
    c=END_SCREEN_LAYOUT['subscribe'];cx,cy=c['center'];r=c['radius']
    d.ellipse((cx-r-8,cy-r-8,cx+r+8,cy+r+8),fill='#142B42',outline='#C8AA6B',width=3)
    d.ellipse((cx-r,cy-r,cx+r,cy+r),fill='#10243A')
    label(im,'チャンネル登録',(750,760,1170,825),43,'#FFF0C3')
    label(im,'これからの改善も、一緒に楽しみましょう。',(210,920,1710,995),41,'#BBD7E5')
    return im
