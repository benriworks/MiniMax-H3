"""Separate video cover images, using the retained duo, without third-party art."""
from PIL import Image
from produce_v04 import Renderer,OUT,old,TEAL,CORAL,NAVY,box,fit

if __name__=='__main__':
    folder=OUT/'review/v04/covers';folder.mkdir(parents=True,exist_ok=True)
    r=Renderer('full');im=Image.new('RGB',(1920,1080),NAVY);r.dark=True
    for who,rect in [('male',(35,210,595,1040)),('female',(1325,210,1885,1040))]:
        src=Image.open(OUT/'characters/v04'/(who+'-close-reference.png')).convert('RGB')
        box(im,rect,'white',24);fit(im,src,(rect[0]+8,rect[1]+8,rect[2]-8,rect[3]-8),True)
    r.text(im,'GPTとBERT',(400,35,1520,185),125)
    r.text(im,'学び方が違う',(620,265,1300,420),84)
    r.badge(im,'次を予測',(625,515,1295,690),TEAL,86)
    r.badge(im,'隠して予測',(625,775,1295,950),CORAL,81)
    r.badge(im,'【AI】',(35,35,310,145),TEAL,53)
    im.save(folder/'thumbnail-full-v03.png');im.save(folder/'thumbnail-full-v03.jpg',quality=95)
    r=Renderer('short');im=r.background().copy();r.result(im,0)
    r.badge(im,'【AI】',(60,1590,1020,1730),TEAL,72)
    im.save(folder/'cover-short-v05.jpg',quality=95)
    old.save(folder/'manifest.json',[dict(path=p.name,bytes=p.stat().st_size,sha256=old.sha(p)) for p in folder.glob('*') if p.suffix in {'.png','.jpg'}])
    print('Separate full thumbnail and short cover created')
