"""Reusable music gain automation; narration is a separate, unchanged stem."""
import math
from types import MappingProxyType
import numpy as np

DEFAULT_BGM_PROFILE = MappingProxyType(dict(
    id='explanation_v1', base_gain=1.3*10**(4/20), duck_gain=.2,
    edge_boost_db=3., intro_seconds=1.4, outro_seconds=2.2,
    attack_seconds=.12, release_seconds=.25,
    fade_in_seconds=.08, fade_out_seconds=.25))
BGM_MIX_PROFILES = frozenset({DEFAULT_BGM_PROFILE['id'], 'legacy'})


def default_bgm_bed(samples, seconds, speech_spans, *, sample_rate=24000):
    """Apply the user-adopted Pro news v04 settings to an unfaded music stem."""
    profile=dict(DEFAULT_BGM_PROFILE)
    profile.pop('id')
    fade_in=profile.pop('fade_in_seconds');fade_out=profile.pop('fade_out_seconds')
    result=np.array(samples,copy=True)
    if result.shape != (round(seconds*sample_rate),2):
        raise ValueError('Expected a stereo music stem matching the timeline')
    n=len(result);t=np.arange(n)/sample_rate
    result*=np.minimum(t/fade_in,1)[:,None]
    result*=np.minimum((n-np.arange(n))/sample_rate/fade_out,1)[:,None]
    result*=music_gain_envelope(seconds,speech_spans,sample_rate=sample_rate,**profile)[:,None]
    return result


def music_gain_envelope(seconds, speech_spans, *, sample_rate=24000,
                        base_gain=DEFAULT_BGM_PROFILE['base_gain'], duck_gain=.2, edge_boost_db=3.,
                        intro_seconds=1.4, outro_seconds=2.2,
                        attack_seconds=.12, release_seconds=.25):
    values=(seconds,base_gain,duck_gain,edge_boost_db,intro_seconds,outro_seconds,attack_seconds,release_seconds)
    if not all(math.isfinite(v) for v in values) or seconds<=0 or sample_rate<=0:
        raise ValueError('Finite duration, gain and rate are required')
    if base_gain<0 or not 0<duck_gain<=1 or not 0<=edge_boost_db<=20:
        raise ValueError('Invalid music gain')
    if min(intro_seconds,outro_seconds,attack_seconds,release_seconds)<0:
        raise ValueError('Automation intervals cannot be negative')
    n=round(seconds*sample_rate);t=np.arange(n)/sample_rate
    edge=np.zeros(n,dtype=np.float64)
    if intro_seconds:edge=np.maximum(edge,np.clip(1-t/intro_seconds,0,1))
    if outro_seconds:
        edge=np.maximum(edge,np.clip((t-(seconds-outro_seconds))/min(outro_seconds,1.),0,1))
    envelope=base_gain*np.power(10.,edge*edge_boost_db/20.)
    duck=np.ones(n,dtype=np.float64)
    for start,end in speech_spans:
        if not math.isfinite(start) or not math.isfinite(end) or not 0<=start<end<=seconds:
            raise ValueError('Speech interval is outside the timeline')
        a=round(start*sample_rate);b=round(end*sample_rate)
        lo=max(0,a-round(attack_seconds*sample_rate));hi=min(n,b+round(release_seconds*sample_rate))
        local=np.full(hi-lo,duck_gain,dtype=np.float64)
        if a>lo:local[:a-lo]=np.linspace(1.,duck_gain,a-lo)
        if hi>b:local[b-lo:]=np.linspace(duck_gain,1.,hi-b)
        duck[lo:hi]=np.minimum(duck[lo:hi],local)
    return (envelope*duck).astype(np.float32)
