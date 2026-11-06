import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.studio.shorts_creator import allocate_scenes, validate_story, load_reusable_audio, record
from tools.studio.announcement_video import (
    validate_announcement_recipe_payload, announcement_recipe_to_detailed_payload,
    announcement_narration_segment_starts, announcement_recipe_audit_summary,
)
from tools.studio.remotion_timeline_execution import validate_remotion_timeline_payload, RemotionTimelineValidationError
from tools.studio.assembly import _build_ass, _phrase_caption_cues, AssemblyValidationError
from tools.studio.assembly_execution import normalize_caption_style_preset
from tests.test_studio_announcement_video import recipe

class CreatorShortsTests(unittest.TestCase):
    def test_feature_diagrams_reject_unknown_icons_and_labels_that_would_overflow(self):
        root=Path(__file__).resolve().parents[1]
        story=json.loads((root/'productions/SHORT_20260930_claude_code_creator/creator-story.json').read_text(encoding='utf-8'))
        scene=story['scenes'][1]
        scene.update(kind='diagram',graphic='cloud',items=[{'label':'調査'},{'label':'資料作成'}])
        validate_story(story)
        scene['graphic']='arbitrary_svg'
        with self.assertRaisesRegex(ValueError,'Invalid feature diagram'):validate_story(story)
        scene['graphic']='cloud';scene['items'][0]['label']='表示領域を超える長い名前'
        with self.assertRaisesRegex(ValueError,'Shorten|Invalid feature'):validate_story(story)
        scene.update(kind='stat',stat='2026.09.29',items=[])
        validate_story(story)
        scene['stat']='2026年9月29日より順次提供開始'
        with self.assertRaisesRegex(ValueError,'statistic'):validate_story(story)

    def test_visual_revision_reuses_verified_audio_but_rejects_changed_speech_or_files(self):
        with tempfile.TemporaryDirectory() as temp, patch('tools.studio.shorts_creator.ROOT',Path(temp)):
            root=Path(temp);prior=root/'outputs/productions/example/previous';prior.mkdir(parents=True)
            story={'id':'example','duration_seconds':30,'voice':'Sayaka','rate':1,'pronunciations':[],
                   'scenes':[{'kind':'hero','narration':'こんにちは。','captions':['こんにちは。'],'headline':'前の見出し'}]}
            def save(name,value):
                (prior/name).write_text(json.dumps(value),encoding='utf-8')
            save('story.json',story);save('props.json',{'captions':[]})
            for name in ['narration.wav','music.wav','effects.wav','timings.json','captions.srt']:
                (prior/name).write_bytes(name.encode())
            raw=root/'raw.wav';raw.write_bytes(b'original speech')
            artifact={**record(raw),'name':'narration.wav'}
            save('voice-source.json',{'artifacts':[artifact]})
            sources=[record(p) for p in prior.iterdir()]+[record(raw)]
            save('preparation.json',{'sources':sources})
            (prior/'shorts-creator.mp4').write_bytes(b'verified delivery')
            save('verification.json',{'review_status':'verified_candidate_awaiting_user_review','delivery':record(prior/'shorts-creator.mp4')})
            visual=copy.deepcopy(story);visual['scenes'][0].update(headline='新しい見出し',media={'path':'new.mp4'})
            with self.assertRaisesRegex(ValueError,'Audio input changed'):load_reusable_audio(visual,prior)
            # Old PCM can only be reused when explicitly preserving its old mix.
            visual['bgm_mix_profile']='legacy'
            _,reuse,_,_=load_reusable_audio(visual,prior)
            self.assertEqual(reuse['method'],'aac_stream_copy')
            spoken=copy.deepcopy(visual);spoken['scenes'][0]['narration']='別の声。'
            with self.assertRaisesRegex(ValueError,'Audio input changed'):load_reusable_audio(spoken,prior)
            rhythm=copy.deepcopy(visual);rhythm['scenes'][0]['items']=[{'label':'追加'}]
            with self.assertRaisesRegex(ValueError,'Audio input changed'):load_reusable_audio(rhythm,prior)
            (prior/'narration.wav').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'Source changed'):load_reusable_audio(visual,prior)

    def test_phrase_captions_stay_inside_speech_and_use_readable_safe_margins(self):
        text='日本語で、つくりたいを伝える。'
        cues=_phrase_caption_cues([(500,3500,text)])
        self.assertEqual(cues[0][0],500)
        self.assertEqual(cues[-1][1],3500)
        self.assertEqual(''.join(c[2] for c in cues),text)
        self.assertTrue(all(a[1]==b[0] for a,b in zip(cues,cues[1:])))
        closing=_phrase_caption_cues([(0,3000,'さあ、アイデアを動く形に。')])
        self.assertTrue(all(c[2].strip('、。！？!?」』）)]') for c in closing))
        style=normalize_caption_style_preset('shorts_ja_phrase_v1')
        self.assertGreaterEqual(style['margin_vertical'],470)
        self.assertGreaterEqual(style['font_size'],54)
        ass=_build_ass(('1\n00:00:00,500 --> 00:00:03,500\n'+text+'\n').encode(),width=1080,height=1920,caption_style_preset='shorts_ja_phrase_v1').decode()
        self.assertEqual(ass.count('Dialogue:'),len(cues))
        self.assertIn(r'\fad(50,60)',ass)
        with self.assertRaises(AssemblyValidationError):_phrase_caption_cues([(0,100,text)])

    def test_measured_speech_is_never_cut_and_total_is_exact(self):
        speech=[1200,2300,3500,1400,1800,2400,3100,2200,2100,2600]
        frames=allocate_scenes(speech,720)
        self.assertEqual(sum(frames),720)
        self.assertTrue(all(n/24>ms/1000+.125 for n,ms in zip(frames,speech)))
        self.assertGreater(len(set(frames)),1)

    def test_overlong_speech_and_static_scenes_fail_before_render(self):
        with self.assertRaisesRegex(ValueError,'too long'):allocate_scenes([10000]*4,720)
        with self.assertRaisesRegex(ValueError,'exceeds 8 seconds'):allocate_scenes([1000]*3,720)

    def test_real_story_caption_text_and_readability(self):
        root=Path(__file__).resolve().parents[1]
        story=json.loads((root/'productions/SHORT_20260930_claude_code_creator/creator-story.json').read_text(encoding='utf-8'))
        validate_story(story)
        invalid=copy.deepcopy(story);invalid['scenes'][0]['captions']=['別の話']
        with self.assertRaisesRegex(ValueError,'match'):validate_story(invalid)
        invalid=copy.deepcopy(story);invalid['scenes'][0]['headline']='大きな文字'*10
        with self.assertRaisesRegex(ValueError,'readable'):validate_story(invalid)

    def test_studio_preset_uses_hard_cuts_and_starts_at_first_frame(self):
        value=recipe();value['template_preset']='shorts_creator_ja_v1'
        normalized=validate_announcement_recipe_payload(value)
        clips=announcement_recipe_to_detailed_payload(normalized)['clips']
        self.assertTrue(all(c['transition_to_next'] is None for c in clips))
        self.assertTrue(all(c['overlay']['start_ms']==0 and c['overlay']['style_preset']=='shorts_creator_v1' for c in clips))
        self.assertEqual(announcement_narration_segment_starts(value),(0,5000,10000))
        self.assertEqual(announcement_recipe_audit_summary(value)['overlay_policy'],'shorts_creator_safe_motion_v1')
        for s in value['scenes']:s['end_ms']=10000
        self.assertEqual(announcement_narration_segment_starts(value),(0,10000,20000))

    def test_unknown_style_and_too_long_creator_headline_are_rejected(self):
        value=recipe();value['template_preset']='shorts_creator_ja_v1'
        payload=announcement_recipe_to_detailed_payload(validate_announcement_recipe_payload(value))
        timeline={'schema_version':1,'clips':payload['clips']}
        timeline['clips'][0]['overlay']['text']='長い文'*9
        with self.assertRaises(RemotionTimelineValidationError):validate_remotion_timeline_payload(timeline)
        timeline['clips'][0]['overlay']['text']='短い文'
        timeline['clips'][0]['overlay']['style_preset']='arbitrary-css'
        with self.assertRaises(RemotionTimelineValidationError):validate_remotion_timeline_payload(timeline)

if __name__=='__main__':unittest.main()
