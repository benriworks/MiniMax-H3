import copy
import json
from pathlib import Path
import unittest
import tempfile
from PIL import Image
from unittest.mock import patch
from tools.studio.shorts_creator import validate_story,prepare,record

class SourceCaptureShortsTests(unittest.TestCase):
    def story(self):
        root=Path(__file__).resolve().parents[1]
        return json.loads((root/'productions/SHORT_20261022_dots_04_editorial/creator-story.json').read_text(encoding='utf-8'))

    def test_official_capture_requires_citation_and_closed_url(self):
        source=self.story();validate_story(source)
        for url in ['https://example.com/fake','http://learn.chatgpt.com/docs/dots/tasks-and-memory',
                    'https://learn.chatgpt.com.example.com/docs/dots/tasks-and-memory',
                    'https://user@learn.chatgpt.com/docs/dots/tasks-and-memory',
                    'https://learn.chatgpt.com/docs/dots/tasks-and-memory?private=1']:
            story=copy.deepcopy(source);story['scenes'][1]['capture']['source_url']=url
            with self.assertRaisesRegex(ValueError,'source URL'):validate_story(story)
        story=copy.deepcopy(source);del story['scenes'][1]['capture']['proof']
        with self.assertRaisesRegex(ValueError,'cited source'):validate_story(story)

    def test_editorial_layout_is_closed_and_narration_still_matches_captions(self):
        source=self.story();source['scenes'][0]['editorial_layout']='arbitrary_html'
        with self.assertRaisesRegex(ValueError,'editorial layout'):validate_story(source)
        source=self.story();source['scenes'][3]['captions']=['原稿と違う字幕']
        with self.assertRaisesRegex(ValueError,'match'):validate_story(source)

    def test_source_paths_cannot_read_outside_production_captures(self):
        story=self.story();story['scenes'][1]['capture']['proof']='../../private.json'
        with self.assertRaisesRegex(ValueError,'paths must stay'):validate_story(story)

    def test_editorial_sidebar_rejects_overflow_before_paid_preparation(self):
        story=self.story();shot=story['scenes'][0]
        shot.update(editorial_layout='channels',stat='dot',items=[{'label':'連絡先','detail':'とても長い条件の説明'}])
        with self.assertRaisesRegex(ValueError,'side-panel'):validate_story(story)
        shot['items']=[{'label':'ChatGPT','detail':'進行状況'}]
        validate_story(story)
        shot['action']='確認してから\n次へ進みます'
        with self.assertRaisesRegex(ValueError,'action'):validate_story(story)

    def test_presenter_does_not_cover_sources_or_load_arbitrary_paths(self):
        story=self.story()
        presenter={'path':'outputs/characters/dots-guide-20261022/guide.png',
                   'proof':'outputs/characters/dots-guide-20261022/guide.json','role':'hook'}
        story['scenes'][0]['presenter']=presenter.copy();validate_story(story)
        story['scenes'][1]['presenter']=presenter.copy()
        with self.assertRaisesRegex(ValueError,'opening or closing'):validate_story(story)
        del story['scenes'][1]['presenter']
        story['scenes'][0]['presenter']['path']='../../secret.png'
        with self.assertRaisesRegex(ValueError,'character assets'):validate_story(story)

    def test_unreviewed_presenter_stops_before_voice_generation(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as temp,patch('tools.studio.shorts_creator.ROOT',Path(temp)),patch('tools.studio.narration.generate_local_narration') as generate:
            root=Path(temp);story=self.story()
            asset=root/'outputs/characters/guide/guide.png';asset.parent.mkdir(parents=True)
            Image.new('RGBA',(768,1024)).save(asset)
            proof_path=asset.with_suffix('.json')
            proof_path.write_text(json.dumps({'artifact':record(asset),'review_status':'pending','source_type':'generated_humanoid','transparent':True,'width':768,'height':1024}),encoding='utf-8')
            story['scenes'][0]['presenter']={'path':asset.relative_to(root).as_posix(),'proof':proof_path.relative_to(root).as_posix(),'role':'hook'}
            path=root/'productions/story.json';path.parent.mkdir();path.write_text(json.dumps(story),encoding='utf-8')
            module=root/'tools/studio/shorts_creator.py';module.parent.mkdir(parents=True);module.write_text('fixture')
            (module.parent/'narration.py').write_text('fixture')
            with patch('tools.studio.shorts_creator.__file__',str(module)),self.assertRaisesRegex(ValueError,'Unverified human'):prepare(path)
            generate.assert_not_called()

    def test_unverified_capture_and_invalid_crop_stop_before_any_voice_generation(self):
        for field,value,expected in [('review_status','unknown','Unverified'),('clip',{'x':0,'y':0,'width':415,'height':172},'outside')]:
            with tempfile.TemporaryDirectory() as temp,patch('tools.studio.shorts_creator.ROOT',Path(temp)),patch('tools.studio.narration.generate_local_narration') as generate:
                root=Path(temp);story=self.story();capture=story['scenes'][1]['capture']
                source=root/capture['path'];source.parent.mkdir(parents=True)
                # Synthetic PNGs keep this guard test independent of private/local captures.
                Image.new('RGB',(20,20),'white').save(source)
                context=root/'outputs/context.png';Image.new('RGB',(100,100),'white').save(context)
                proof={'artifact':record(source),'context':record(context),
                       'title':capture['title'],'source_url':capture['source_url'],
                       'review_status':'capture_review_passed',
                       'context_clip':{'x':0,'y':0,'width':100,'height':100},
                       'clip':{'x':10,'y':10,'width':20,'height':20}}
                proof[field]=value
                (root/capture['proof']).write_text(json.dumps(proof),encoding='utf-8')
                path=root/'productions/story.json';path.parent.mkdir();path.write_text(json.dumps(story),encoding='utf-8')
                module=root/'tools/studio/shorts_creator.py';module.parent.mkdir(parents=True);module.write_text('fixture')
                (module.parent/'narration.py').write_text('fixture')
                with patch('tools.studio.shorts_creator.__file__',str(module)),self.assertRaisesRegex(ValueError,expected):prepare(path)
                generate.assert_not_called()

if __name__=='__main__':unittest.main()
