"""Fit explicitly authored semantic lines without splitting Japanese words."""
import math


def visible_glyph_bbox(value, font):
    """Measure actual Pillow raster ink, excluding advance-width side whitespace."""
    mask,offset=font.getmask2(value)
    bounds=mask.getbbox()
    if bounds is None:raise ValueError('Label has no visible glyphs')
    return (bounds[0]+offset[0],bounds[1]+offset[1],bounds[2]+offset[0],bounds[3]+offset[1])


def fit_explicit_lines(text, width, measure, *, preferred_size=42, minimum_size=32):
    """measure(line, size) returns pixel width; reject overflow instead of rewrapping."""
    if not isinstance(text,str) or not text.strip():raise ValueError('Expected nonempty text')
    if not math.isfinite(width) or width<=0:raise ValueError('Expected positive finite width')
    if not 1<=minimum_size<=preferred_size:raise ValueError('Invalid readable font size range')
    lines=text.splitlines()
    for size in range(preferred_size,minimum_size-1,-1):
        if all(measure(line,size)<=width for line in lines):return dict(lines=lines,font_size=size)
    raise ValueError('Semantic lines exceed the readable width; shorten the wording')


def box_text_layout(value, rect, measure_bbox, *, padding=8, line_gap=8):
    """Place visible glyphs centrally; authored multi-line labels stay top aligned.

    measure_bbox(line) returns (left, top, right, bottom) at drawing origin (0,0).
    Return drawing origins, accounting for font bearings rather than ascent alone.
    No wrapping or font reduction is performed: overflow needs editorial repair.
    """
    if not isinstance(value,str) or not value.strip():raise ValueError('Expected nonempty label')
    if len(rect)!=4 or not all(math.isfinite(v) for v in rect):raise ValueError('Invalid label rectangle')
    x,y,x2,y2=rect
    if not math.isfinite(padding) or padding<0 or not math.isfinite(line_gap) or line_gap<0:
        raise ValueError('Invalid label spacing')
    if x2-x<=2*padding or y2-y<=2*padding:raise ValueError('Label rectangle is too small')
    lines=value.splitlines()
    if any(not line.strip() for line in lines):raise ValueError('Empty label lines are not supported')
    bounds=[tuple(measure_bbox(line)) for line in lines]
    if any(len(v)!=4 or not all(math.isfinite(n) for n in v) for v in bounds):
        raise ValueError('Invalid glyph bounds')
    heights=[v[3]-v[1] for v in bounds];widths=[v[2]-v[0] for v in bounds]
    height=sum(heights)+line_gap*(len(lines)-1)
    if min(heights)<=0 or min(widths)<=0 or max(widths)>x2-x-2*padding or height>y2-y-2*padding:
        raise ValueError('Label exceeds its readable rectangle; shorten it or enlarge the box')
    cursor=(y+y2-height)/2 if len(lines)==1 else y+padding
    placements=[]
    for line,bounds_i,width,h in zip(lines,bounds,widths,heights):
        left=(x+x2-width)/2
        placements.append(dict(text=line,origin=(left-bounds_i[0],cursor-bounds_i[1]),ink_bounds=(left,cursor,left+width,cursor+h)))
        cursor+=h+line_gap
    return dict(placements=placements,vertical_alignment='center' if len(lines)==1 else 'top')
