"""Fit explicitly authored semantic lines without splitting Japanese words."""
import math


def fit_explicit_lines(text, width, measure, *, preferred_size=42, minimum_size=32):
    """measure(line, size) returns pixel width; reject overflow instead of rewrapping."""
    if not isinstance(text,str) or not text.strip():raise ValueError('Expected nonempty text')
    if not math.isfinite(width) or width<=0:raise ValueError('Expected positive finite width')
    if not 1<=minimum_size<=preferred_size:raise ValueError('Invalid readable font size range')
    lines=text.splitlines()
    for size in range(preferred_size,minimum_size-1,-1):
        if all(measure(line,size)<=width for line in lines):return dict(lines=lines,font_size=size)
    raise ValueError('Semantic lines exceed the readable width; shorten the wording')
