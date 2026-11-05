"""Compensate camera push-in in these plain-background character reactions only.

This tracks a head-region template, not a face identity or a scientific result.
Native video/cache stay unchanged; corrected frames are separate derivatives.
"""
from pathlib import Path
import hashlib,json
import cv2
import numpy as np

ALGORITHM='ai-history-head-template-v1'

def head_template(first):
    grey=cv2.cvtColor(first,cv2.COLOR_BGR2GRAY);mask=grey<140
    yy,xx=np.where(mask[:180])
    if not len(yy):raise ValueError('No head anchor in expected top region')
    top=int(yy.min());_,xx=np.where(mask[top:top+90]);x0=max(0,int(xx.min())-8);x1=min(first.shape[1],int(xx.max())+9)
    y0=max(0,top-6);y1=min(280,top+round((x1-x0)*1.22)+8)
    return grey[y0:y1,x0:x1],(x0,y0,x1,y1)

def prepare(native,framed,source_sha256):
    framed=Path(framed);receipt=framed/'complete.json';files=sorted(Path(native).glob('*.jpg'))
    if receipt.exists():
        data=json.loads(receipt.read_text(encoding='utf-8'))
        if data['source_sha256']!=source_sha256 or data['algorithm']!=ALGORITHM or len(list(framed.glob('*.png')))!=len(files):
            raise RuntimeError('Framed cache differs; use a new derivative revision')
        return data
    if not files:raise ValueError('Native decoded frames are required')
    framed.mkdir(parents=True,exist_ok=True);first=cv2.imread(str(files[0]));template,bbox=head_template(first);samples=[]
    indices=sorted(set(list(range(0,len(files),6))+[len(files)-1]))
    for index in indices:
        grey=cv2.cvtColor(cv2.imread(str(files[index])),cv2.COLOR_BGR2GRAY)[:430]
        best=(-1,1,(bbox[0],bbox[1]))
        for scale in np.arange(.85,1.91,.05):
            scaled=cv2.resize(template,None,fx=float(scale),fy=float(scale),interpolation=cv2.INTER_LINEAR)
            if scaled.shape[0]>=grey.shape[0] or scaled.shape[1]>=grey.shape[1]:continue
            _,score,_,xy=cv2.minMaxLoc(cv2.matchTemplate(grey,scaled,cv2.TM_CCOEFF_NORMED))
            if score>best[0]:best=(score,float(scale),xy)
        samples.append(dict(frame=index,score=float(best[0]),scale=round(best[1],3),x=best[2][0],y=best[2][1]))
    data=dict(algorithm=ALGORITHM,source_sha256=source_sha256,template_bbox=bbox,samples=samples,scope='Only this fictional character shot; not valid for UI or measured comparisons',native_video_unchanged=True)
    (framed/'tracking.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if min(s['score'] for s in samples)<.58:raise RuntimeError('Low-confidence head tracking requires visual review before framing')
    scales=np.array([s['scale'] for s in samples]);centers=np.array([[s['x']+template.shape[1]*s['scale']/2,s['y']+template.shape[0]*s['scale']/2] for s in samples])
    # A three-sample median reduces scale-grid flicker while preserving onset.
    scales=np.array([np.median(scales[max(0,i-1):min(len(scales),i+2)]) for i in range(len(scales))])
    apply=bool(scales.max()>1.12 or scales.min()<.9)
    target=np.array([(bbox[0]+bbox[2])/2,(bbox[1]+bbox[3])/2]);points=np.array(indices)
    for i,file in enumerate(files):
        im=cv2.imread(str(file))
        if apply:
            scale=float(np.interp(i,points,scales));center=np.array([np.interp(i,points,centers[:,k]) for k in range(2)])
            factor=1/scale;offset=target-center*factor
            matrix=np.array([[factor,0,offset[0]],[0,factor,offset[1]]],dtype=np.float32)
            im=cv2.warpAffine(im,matrix,(im.shape[1],im.shape[0]),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT,borderValue=(255,255,255))
        target_file=framed/(file.stem+'.png');cv2.imwrite(str(target_file),im)
    data.update(applied=apply,frames=len(files),scale_range=[float(scales.min()),float(scales.max())],minimum_template_score=min(s['score'] for s in samples),opencv_version=cv2.__version__)
    receipt.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');return data
