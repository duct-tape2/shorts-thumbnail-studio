import unittest
from studio.design import make_plan,validate_design

class DesignTests(unittest.TestCase):
    def test_korean_brief(self):
        p=make_plan('주말 여행','어두운 배경, 노란 포인트. 제목은 아래 가운데 정렬.')
        self.assertEqual(p['background'],'#142B46');self.assertEqual(p['accent'],'#FFD447')
        self.assertEqual(p['align'],'center');self.assertEqual(p['title_position'],'bottom')
    def test_no_fabricated_photograph(self):
        p=make_plan('제목','사진 가득 시네마 느낌')
        self.assertEqual(p['layout'],'poster');self.assertTrue(p['warnings'])
    def test_literal_colors_and_override(self):
        p=make_plan('제목','배경 #ABCDEF 포인트 #123456',preset='warm')
        self.assertEqual(p['background'],'#ABCDEF');self.assertEqual(p['accent'],'#123456');self.assertEqual(p['preset'],'warm')
    def test_validate_untrusted_ai_or_file_plan(self):
        p=make_plan('제목');p['background']='url(file://private)'
        with self.assertRaises(ValueError):validate_design(p)
    def test_bad_emphasis_is_actionable(self):
        with self.assertRaises(ValueError):make_plan('제목',emphasis='없는 말')
    def test_unknown_prompt_is_not_claimed_understood(self):
        p=make_plan('제목','우주에서 춤추는 동물 사진을 그려줘')
        self.assertTrue(p['warnings']);self.assertFalse(p['image'])

if __name__=='__main__':unittest.main()
