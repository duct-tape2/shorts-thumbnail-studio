import json
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from studio.copywriting import plan_copy,complete_sentence,safe_filename
from studio.ocr import detect_frame
from studio.render import validate_plan
from studio.paths import ASSETS


class PipelineTests(unittest.TestCase):
    def test_fragment_repaired_without_ai(self):
        p=plan_copy('전기차 멀미,\n운전자는 덜할까?','몸속 감각이','눈 귓속 몸속 감각')
        self.assertTrue(p['copy_repaired']);self.assertNotEqual(p['caption'],'몸속 감각이')
        self.assertGreater(len(p['caption']),12);self.assertEqual(p['emphasis'],'운전자')
    def test_full_sentence_preserved(self):
        s='가슴이 아닌 턱이나 등, 어깨가 아픈 경우도 있습니다'
        self.assertEqual(plan_copy('가슴 통증 없는데 심장 질환 생기는 이유',s,'')['caption'],s)
    def test_unknown_topic_does_not_invent_facts(self):
        title='낯선 현상은 왜 생길까?'
        p=plan_copy(title,'이유가','')
        self.assertEqual(p['caption'],title);self.assertTrue(p['warnings'])
    def test_sanitized_title_filename(self):
        self.assertEqual(safe_filename('전기차 멀미,\n운전자는 덜할까?'),'전기차 멀미 운전자는 덜할까.png')
        self.assertNotIn('/',safe_filename('../../제목:*?'))
    def test_sentence_detector(self):
        for s in ['몸속 감각이','그래서','음식물 찌꺼기나 때가 남아있으면']:
            self.assertFalse(complete_sentence(s))
        self.assertTrue(complete_sentence('쿠션감이 좋은 실내화면 좋습니다'))
    def test_rules_have_safe_bounded_copy(self):
        rules=json.loads((ASSETS/'copy_rules.json').read_text(encoding='utf-8'))
        self.assertGreaterEqual(len(rules),50)
        self.assertEqual(len({r['id'] for r in rules}),len(rules))
        for r in rules:
            self.assertLessEqual(len(r['aux']),15,r['id'])
            self.assertTrue(complete_sentence(r['caption']),r['id'])
    def test_bad_crop_rejected(self):
        p=dict(title='테스트 제목',caption='테스트 내용을 확인해요',aux='내용 확인',source='출처',emphasis='테스트',crop=[-1,0,500,500],image_size=[500,500])
        with self.assertRaises(ValueError):validate_plan(p)
    def test_non_template_not_silently_assumed(self):
        frame,known=detect_frame(Image.new('RGB',(900,1200),'white'))
        self.assertFalse(known)

    def test_capture_negative_monitor_origin(self):
        from custom_capture.capture import DesktopSnapshot,save_region_from_snapshot
        from PySide6.QtCore import QRect
        original=Image.new('RGB',(800,400),'navy')
        original.paste('orange',(200,100,400,250))
        snapshot=DesktopSnapshot(original,-800,-100)
        with tempfile.TemporaryDirectory() as folder:
            path,crop=save_region_from_snapshot(snapshot,QRect(-600,0,200,150),Path(folder))
            self.assertEqual(crop.size,(200,150))
            self.assertEqual(crop.getpixel((0,0)),(255,165,0))
            self.assertEqual(crop.getpixel((199,149)),(255,165,0))
            with Image.open(path) as saved:
                self.assertEqual(saved.size,(200,150))


if __name__=='__main__':unittest.main()
