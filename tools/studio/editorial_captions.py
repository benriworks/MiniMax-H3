"""Phrase-based captions with separate display text and measured fixed-size glyphs.

BudouX proposes boundaries; numeric expressions, product words and explicit protected
phrases may not be cut. An oversized phrase fails instead of splitting a word or
silently shrinking the type. Old renderers remain opt-in and reproducible.
"""
from functools import lru_cache
import re
import budoux
from .explainer_canvas import glyph

@lru_cache(maxsize=1)
def parser():return budoux.load_default_japanese_parser()

PROTECTED=('離す動き','注ぎ終わり','流体シミュレーション','バンクリセット','クラウドPC','約1.9倍','約1.91倍','ChatGPT','Blender','Python','Codex','dots','GPT-6.1','Pro 200')
DISPLAY_LEXICON={'ドッツ':'dots','ブレンダー':'Blender','パイソン':'Python','シージー':'CG','ティボ':'Tibo','約一点九倍':'約1.9倍'}
READING_LEXICON={'ChatGPT':'チャットジーピーティー','Blender':'ブレンダー','Python':'パイソン','Codex':'コーデックス','dots':'ドッツ','Tibo':'ティボ'}

def speech_text(display,explicit=None):
    """Optional reading draft; unusual names/numbers require an explicit per-turn reading."""
    if explicit is not None:return explicit
    value=display
    for word,reading in READING_LEXICON.items():
        value=re.sub(r'(?<![A-Za-z])'+re.escape(word)+r'(?![A-Za-z])',reading,value)
    digits='零一二三四五六七八九'
    # Deliberately bounded to one integer digit; never pretend to verbalize all numbers.
    value=re.sub(r'(?<![\d.])([0-9])\.([0-9]+)(?![\d.])',lambda m:digits[int(m[1])]+'点'+''.join(digits[int(c)] for c in m[2]),value)
    return value

def display_text(spoken,explicit=None):
    if explicit is not None:return explicit
    result=spoken
    for a,b in DISPLAY_LEXICON.items():result=result.replace(a,b)
    return result

def phrase_units(value,protected=PROTECTED):
    if '\n' in value:raise ValueError('Pass a paragraph; explicit lines are handled separately')
    spans=[(m.start(),m.end()) for m in re.finditer(r'[A-Za-z0-9]+(?:[.\-][A-Za-z0-9]+)*(?:[%倍秒円]|k)?',value)]
    for word in protected:
        spans.extend((m.start(),m.end()) for m in re.finditer(re.escape(word),value))
    units=[];cursor=0
    for unit in parser().parse(value):
        cursor+=len(unit)
        if units and any(a<cursor-len(unit)<b for a,b in spans):units[-1]+=unit
        elif units and unit and unit[0] in '、。？！ーゃゅょっァィゥェォャュョッ%倍':units[-1]+=unit
        else:units.append(unit)
    return units

def phrase_lines(value,max_width,font_size,protected=PROTECTED):
    lines=[]
    for paragraph in value.split('\n'):
        current=''
        for unit in phrase_units(paragraph,protected):
            if unit.isspace():
                current+=unit
                continue
            if glyph(unit,font_size,'white').width>max_width:
                raise ValueError(f'Phrase exceeds caption width; reword or explicitly divide: {unit!r}')
            if current and glyph(current+unit,font_size,'white').width>max_width:
                lines.append(current);current=unit
            else:current+=unit
        if current:lines.append(current)
    assert ''.join(lines)==value.replace('\n','')
    return lines

def caption_pages(value,max_width,font_size,max_lines=2):
    # Sentence boundaries are useful page boundaries, not hard character limits.
    pages=[]
    for sentence in re.findall(r'[^。？！]+[。？！]?|[。？！]',value):
        lines=phrase_lines(sentence,max_width,font_size)
        pages.extend('\n'.join(lines[i:i+max_lines]) for i in range(0,len(lines),max_lines))
    if not pages:raise ValueError('Empty caption')
    return pages

def timed_captions(value,start,seconds,max_width,font_size):
    pages=caption_pages(value,max_width,font_size);weights=[len(s.replace('\n','')) for s in pages];total=sum(weights);cursor=start;result=[]
    for i,(page,weight) in enumerate(zip(pages,weights)):
        end=start+seconds if i==len(pages)-1 else cursor+seconds*weight/total
        result.append(dict(start=cursor,end=end,text=page));cursor=end
    return result
