"""Export two named cover images and paste-ready descriptions from the timed scripts."""
import json
import sys
from pathlib import Path
import cv2
from PIL import Image,ImageDraw,ImageOps

from art import Board,GREEN,MINT,ORANGE,INK,WHITE,NAVY,xy
from render import make_plan
HERE=Path(__file__).resolve().parent
NOTES="https://help.openai.com/en/articles/6825453-chatgpt-release-notes"
LAUNCH="https://openai.com/index/introducing-gpt-6-2-astra-sol/"
TITLES={"short":"【ChatGPT】GPT-6.2に宿の料金表を見せたら、徒歩5分で答えが変わった #Shorts",
        "full":"【ChatGPT】GPT-6.2がチャットに登場｜宿の料金表で試す画像理解と条件比較"}
def cover(media,short,dest):
    art=Board(short,media)
    art.begin(NAVY)
    if short:
        art.text(47,114,"ChatGPT",32,800,MINT)
        art.text(43,259,"GPT-6.2",104,870,WHITE,641)
        art.rect((47,403,79,7),ORANGE)
        art.text(45,449,"この宿、予算内？",64,840,WHITE,640)
        bounds=(40,594,640,414)
        art.text(46,1046,"料金表の画像で実演",34,735,MINT,636)
    else:
        art.text(52,56,"ChatGPT",30,800,MINT)
        art.rect((53,122,88,8),ORANGE)
        art.text(48,187,"GPT-6.2",113,870,WHITE,603)
        art.text(49,370,"料金表で",77,830,WHITE,568)
        art.text(49,483,"宿を選ぶ",77,830,WHITE,568)
        bounds=(625,0,655,720)
    vid=cv2.VideoCapture(str(media/"motion"/("winter-study" if short else "winter-duet")/"source.mp4"))
    vid.set(cv2.CAP_PROP_POS_FRAMES,68 if short else 87)
    ok,frame=vid.read();vid.release()
    if not ok:raise IOError("Missing cover frame")
    pic=Image.fromarray(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB))
    if short:
        x,y,ww,hh=bounds
        image=ImageOps.fit(pic,xy(ww,hh),method=Image.Resampling.LANCZOS,centering=(.5,.2))
        art.im.paste(image,xy(x,y))
    else:
        # Two closely cropped portraits preserve both faces on the landscape thumbnail.
        x,y,ww,hh=bounds
        for i in (0,1):
            im=pic.crop((i*pic.width//2,0,(i+1)*pic.width//2,pic.height))
            tile=ImageOps.fit(im,xy(ww//2+1,hh),method=Image.Resampling.LANCZOS,centering=(.5,.12))
            art.im.paste(tile,xy(x+i*(ww//2),y))
        art.rect((621,0,4,720),ORANGE)
    art.im.save(dest,quality=91,subsampling=0,optimize=True)
    assert dest.stat().st_size<2_000_000
    art.im.thumbnail((180,320) if short else (320,180),Image.Resampling.LANCZOS)
    return art.im

def clock(t):
    sec=int(t)
    return f"{sec//60}:{sec%60:02}"

def main(media):
    out=media/"youtube/v01";out.mkdir(parents=True,exist_ok=True)
    thumbs=[]
    markdown=["# YouTube投稿用｜チャット版GPT-6.2","","2026-11-25制作。各本文は概要欄に貼り付けられる。"]
    for kind in ("short","full"):
        short=kind=="short"
        thumbs.append(cover(media,short,out/(kind+"-cover.jpg")))
        plan=make_plan(media,kind)
        if short:
            body=("ChatGPTのChatタブにGPT-6.2が登場。架空の宿の料金表を1枚渡して、朝食付き2泊で22,000円以内、駅から徒歩15分以内と頼みました。徒歩5分以内に変えると、同じ画像から違う答えが返ってきます。実際の選択画面と回答を収録しました。\n\n出典　OpenAI「ChatGPT release notes」2026年11月23日\n"+NOTES+"\n\n#ChatGPT #GPT62 #Shorts")
        else:
            chapters={c["id"]:c["start"] for c in plan["chapters"]}
            marks=[("lead","チャットに来たGPT-6.2"),("entry","Web版でモデルを選ぶ"),("criteria","料金表を画像で渡す"),("answer","朝食2回の料金を検算する"),("ext","徒歩15分を5分に変える"),("stat1","OpenAIの画像理解・指示追従の評価"),("available","対象プランと使い方")]
            body=("11月23日、OpenAIはChatGPTのChatタブ向けに、日常会話用に調整したGPT-6.2 Solの提供を開始しました。冬服の二人が、架空の宿の料金表を使って画像理解と条件比較を実演します。\n\n朝食付き2泊で22,000円、駅から徒歩15分という条件に合うのはどの宿か。徒歩5分に絞ると何が変わるか。実際の回答と元の料金を照合し、OpenAIが公表した2種類の評価、対象プラン、11月17日のWork・Codex向け発表との違いを紹介します。\n\nチャプター\n"+"\n".join((("0:00" if i==0 else clock(chapters[key]))+" "+title) for i,(key,title) in enumerate(marks))+"\n\n公式資料\nOpenAI「ChatGPT release notes」2026年11月23日\n"+NOTES+"\nOpenAI「Introducing GPT-6.2 Astra and Sol」2026年11月17日\n"+LAUNCH+"\n\n#ChatGPT #GPT62 #AI活用")
        (out/(kind+"-description.txt")).write_text(body+"\n",encoding="utf-8-sig")
        (out/(kind+"-title.txt")).write_text(TITLES[kind]+"\n",encoding="utf-8-sig")
        markdown.extend(["","## "+("ショート" if short else "フル"),"",TITLES[kind],"","~~~text",body,"~~~","","サムネイル　`youtube/v01/"+kind+"-cover.jpg`。"])
    (HERE/"YOUTUBE_DRAFTS_JA.md").write_text("\n".join(markdown)+"\n",encoding="utf-8")
    sheet=Image.new("RGB",(520,330),NAVY);sheet.paste(thumbs[0],(3,4));sheet.paste(thumbs[1],(191,64))
    sheet.save(out/"mobile-preview.jpg",quality=93)
if __name__=="__main__": main(Path(sys.argv[1]))
