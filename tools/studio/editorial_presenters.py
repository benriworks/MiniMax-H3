"""Shared presenter intent and manually measured atlas face framing.

Anchors apply to the approved 400px duo atlas only, not arbitrary generated faces.
No facial warping or new artwork: uniform scale and placement from source pixels.
"""
from PIL import Image

FACE_ANCHORS={'male':dict(face_height=164,eyes=(205,213)),'female':dict(face_height=171,eyes=(205,208))}

def face_geometry(speaker,size):
    a=FACE_ANCHORS[speaker];scale=size*.40/a['face_height']
    return dict(scale=scale,x=size*.50-a['eyes'][0]*scale,y=size*.54-a['eyes'][1]*scale,face_height=size*.40,eyes=(size*.50,size*.54))

def equalized_face(atlas,speaker,mood,opened,size):
    source=atlas.frame(mood,opened,400);g=face_geometry(speaker,size)
    tile=source.resize((round(400*g['scale']),round(400*g['scale'])),Image.Resampling.LANCZOS)
    output=Image.new('RGB',(size,size),'#0C1D31');output.paste(tile,(round(g['x']),round(g['y'])))
    return output

def intent_mood(intent,speaker,active):
    if intent in ('question','size_question','procedural_question','summary_question','bankq'):return 'curious' if active else 'serious'
    if intent in ('fix','size_fix','motion_fix','process','limits','check','usage','cache'):return 'serious'
    if intent in ('reaction','summary','result','understand','applause','closing'):return 'pleased'
    return 'neutral'
