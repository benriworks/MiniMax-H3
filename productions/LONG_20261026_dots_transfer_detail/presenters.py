"""Use the existing MiniMax people as short full-canvas interludes, without loops."""
from pathlib import Path
import json,subprocess
from PIL import Image,ImageDraw
from graphics import text,box,LIME,WHITE

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
OUT=ROOT/'outputs/productions'/HERE.name/'v01'


def main():
    registry=json.loads((ROOT/'productions/characters/motion-registry-20261022.json').read_text(encoding='utf-8'))['clips']
    target=OUT/'presenters';target.mkdir(exist_ok=True)
    male=ROOT/registry['dots-male']['video']['path'];female=ROOT/registry['dots-female']['video']['path']
    for slug,headline,middle in [('intro','同じ情報の入力を、dotsに任せる','入力は任せて\n人が確かめる'),
                                 ('outro','小さく試して、任せる範囲を広げる','対象を決める\n結果を確かめる')]:
        base=Image.new('RGB',(1920,1080),'#030514');d=ImageDraw.Draw(base)
        text(d,(70,40),'dots  /  実演でわかる自動転記',28,'#a5bbb5')
        text(d,(70,98),headline,57,WHITE)
        box(d,(1490,40,1850,93),LIME,r=25);text(d,(1513,48),'架空データ・デモ環境',28)
        text(d,(100,835),'疑問と照合を担当',33,WHITE);text(d,(1320,835),'手順の案内を担当',33,WHITE)
        text(d,(760,420),middle,48,WHITE)
        plate=target/f'{slug}-base.png';base.save(plate)
        dest=target/f'{slug}.mp4'
        if dest.exists():continue
        with (target/f'{slug}.log').open('w',encoding='utf-8') as log:
            subprocess.run(['ffmpeg','-v','warning','-nostdin','-y','-i',str(plate),'-i',str(male),'-i',str(female),
                '-filter_complex','[1:v]crop=768:900:0:250,scale=600:704,setsar=1[m];[2:v]crop=768:900:0:250,scale=600:704,setsar=1[f];[0:v][m]overlay=80:180[b];[b][f]overlay=1240:180,format=yuv420p',
                '-an','-t','5','-r','24','-c:v','libx264','-preset','fast','-crf','18','-threads','4',str(dest)],
                stdout=log,stderr=subprocess.STDOUT,check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    print('Prepared two five-second full-canvas character interludes, muted, no loops')


if __name__=='__main__':main()
