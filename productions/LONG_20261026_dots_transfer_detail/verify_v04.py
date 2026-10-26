"""Verify unchanged AAC, old finals and the three visual revision boundaries."""
from pathlib import Path
import hashlib,json,subprocess
import numpy as np
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
OUT=ROOT/'outputs/productions'/HERE.name/'v04';OLD=OUT.parent/'v03'


def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def main():
    movie=OUT/'dots-transfer-detail-v04.mp4';previous=OLD/'dots-transfer-detail-v03.mp4'
    revision=json.loads((OUT/'visual-revision.json').read_text(encoding='utf-8'))
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(movie)]))
    video=next(s for s in probe['streams'] if s['codec_type']=='video')
    audio=next(s for s in probe['streams'] if s['codec_type']=='audio')
    assert (video['width'],video['height'],video['avg_frame_rate'],int(video['nb_frames']))==(1920,1080,'24/1',5955)
    assert (audio['codec_name'],audio['sample_rate'],audio['channels'])==('aac','48000',2)
    decode=subprocess.run(['ffmpeg','-v','error','-nostdin','-xerror','-i',str(movie),'-f','null','-'],capture_output=True,text=True,check=True)
    assert not decode.stderr.strip()
    def aac(path):
        return hashlib.sha256(subprocess.check_output(['ffmpeg','-v','error','-nostdin','-i',str(path),'-map','0:a:0','-c','copy','-f','adts','pipe:1'])).hexdigest()
    a,b=aac(movie),aac(previous)
    assert a==b,'Adopted audio changed'
    assert hashlib.sha256(previous.read_bytes()).hexdigest()==revision['source_video']['sha256']
    for item in json.loads((OLD/'source-manifest.json').read_text(encoding='utf-8'))['old_videos_preserved']:
        assert hashlib.sha256((ROOT/item['path']).read_bytes()).hexdigest()==item['sha256']
    qa=OUT/'qa';qa.mkdir(exist_ok=True)
    times=[0,2,4.9,5,5.17,32.125,32.166666666666664,44,50.125,50.166666666666664,127.08333333333333,127.125,129,131.08333333333334,131.125,150,200,245]
    records=[]
    for i,time in enumerate(times):
        dest=qa/f'after-{i:02d}.png'
        subprocess.run(['ffmpeg','-v','error','-nostdin','-n','-ss',str(time),'-i',str(movie),'-frames:v','1',str(dest)],check=True)
        records.append(dict(path=dest.name,seconds=time))
    for page,start in enumerate(range(0,len(records),9),1):
        sheet=Image.new('RGB',(1440,876),'#eeeeee');draw=ImageDraw.Draw(sheet)
        for i,item in enumerate(records[start:start+9]):
            x,y=i%3*480,i//3*292;sheet.paste(Image.open(qa/item['path']).resize((480,270)),(x,y));draw.text((x+8,y+273),str(item['seconds'])+'s',fill='black')
        sheet.save(qa/f'contact-{page:02d}.jpg',quality=95)
    # Additional compression is allowed; unchanged content is checked at three outside samples.
    unchanged=[]
    for time in [60,150,200]:
        def frame(path):
            data=subprocess.check_output(['ffmpeg','-v','error','-nostdin','-ss',str(time),'-i',str(path),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'])
            return np.frombuffer(data,dtype=np.uint8).astype(np.float32)
        old,new=frame(previous),frame(movie);mae=float(np.mean(np.abs(old-new)))
        assert mae<2,'Unexpected visual change outside requested intervals'
        unchanged.append(dict(seconds=time,mean_absolute_pixel_error=mae,limit=2))
    save(qa/'frames.json',records)
    save(OUT/'technical-verification-v04.json',dict(status='technically_verified_review_pending',video=dict(path=movie.name,bytes=movie.stat().st_size,
        sha256=hashlib.sha256(movie.read_bytes()).hexdigest(),probe=probe),full_decode=True,aac_identical_to_adopted_v03=True,
        aac_sha256=a,old_v01_v02_v03_final_hashes_preserved=True,seconds=248.125,frames=5955,
        inspected_visual_samples=len(records),outside_edit_sample_comparison=unchanged,new_tts_calls=0,new_minimax_calls=0,
        new_imagegen_calls=0,human_final_review=False,user_v04_adoption=False,published=False,mobile_device_playback=False))
    print('Verified',5955,'frames; full decode; AAC identical; old three versions unchanged;',len(records),'visual samples',flush=True)


if __name__=='__main__':main()
