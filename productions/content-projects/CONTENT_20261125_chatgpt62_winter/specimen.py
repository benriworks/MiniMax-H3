"""Create the fictional two-hotel rate card used as the actual image input."""
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[3]
FONT = ROOT / "studio/public/template-assets/NotoSansJP-Variable.ttf"

def font(size, weight=600):
    f = ImageFont.truetype(str(FONT), size)
    f.set_variation_by_axes([weight])
    return f

def create(target):
    target.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (1440, 900), "#F6F0E5")
    d = ImageDraw.Draw(image)
    ink = "#192E38"
    d.rectangle((0, 0, 1440, 17), fill="#1D726B")
    d.text((78, 48), "冬の宿泊プラン", font=font(76,800),fill=ink)
    d.text((80, 165), "1名・1泊あたり／税込　　比較用の架空の料金表", font=font(33), fill="#536468")
    for i, (name, walk, room, meal, accent) in enumerate([
        ("駅前館","徒歩3分","11,800円","宿泊料金に含む","#AB4B3E"),
        ("雪灯り館","徒歩12分","10,400円","1人1回 600円","#1D726B")]):
        x=78+i*655
        d.rounded_rectangle((x,260,x+625,805),radius=22,fill="#FFFCF6",outline="#C7C6B9",width=3)
        d.rounded_rectangle((x+26,286,x+35,372),radius=3,fill=accent)
        d.text((x+60,289),name,font=font(58,800),fill=ink)
        for j,(label,val) in enumerate([("駅から",walk),("宿泊料金",room),("朝食",meal)]):
            y=417+j*118
            d.line((x+40,y-19,x+580,y-19),fill="#D6D3C8",width=2)
            d.text((x+45,y),label,font=font(30),fill="#5D6E70")
            d.text((x+230,y-6),val,font=font(35,720),fill=ink)
    image.save(target)

if __name__ == "__main__":
    create(Path(sys.argv[1]))
