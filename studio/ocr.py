import json
from dataclasses import dataclass, asdict
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageOps, ImageFilter
from .paths import ASSETS


@dataclass
class TextBox:
    text: str
    score: float
    box: list

    @property
    def x(self): return self.box[0]
    @property
    def y(self): return self.box[1]
    @property
    def w(self): return self.box[2] - self.box[0]
    @property
    def h(self): return self.box[3] - self.box[1]


class OCR:
    def __init__(self):
        from rapidocr import RapidOCR, OCRVersion, ModelType
        from kiwipiepy import Kiwi
        self.kiwi=Kiwi(num_workers=1)
        for term in ('전기차','내장지방','심장질환','ADHD','소독제','실내화','쿠션감','보이스피싱','스미싱','스마트폰','운전자','코메디닷컴'):
            self.kiwi.add_user_word(term,'NNP',10)
        # All models are local. Classification is disabled: screenshots are upright.
        self.engine = RapidOCR(params={
            'Global.use_cls': False,
            'Global.text_score': 0.45,
            'Cls.model_path': str(ASSETS / 'models/cls.onnx'),
            'Det.model_path': str(ASSETS / 'models/det.onnx'),
            'Det.ocr_version': OCRVersion.PPOCRV5,
            'Det.model_type': ModelType.MOBILE,
            'Rec.model_path': str(ASSETS / 'models/korean-rec.onnx'),
            'Rec.lang_type': 'korean',
            'Rec.ocr_version': OCRVersion.PPOCRV5,
            'Rec.model_type': ModelType.MOBILE,
            'EngineConfig.onnxruntime.intra_op_num_threads': 2,
            'EngineConfig.onnxruntime.inter_op_num_threads': 1,
        })

    def read(self, image):
        a = np.array(image.convert('RGB'))
        result = self.engine(cv2.cvtColor(a, cv2.COLOR_RGB2BGR), use_cls=False)
        boxes = []
        if result.boxes is None:
            return boxes
        for points, text, confidence in zip(result.boxes, result.txts, result.scores):
            if float(confidence) < .40:
                continue
            pts = np.array(points)
            x0,y0 = pts.min(axis=0)
            x1,y1 = pts.max(axis=0)
            boxes.append(TextBox(text.strip(), float(confidence), [float(x0),float(y0),float(x1),float(y1)]))
        return sorted(boxes, key=lambda b:(b.y,b.x))

    def space(self,text):
        spaced=self.kiwi.space(text)
        # Spacing may change, content must never change at this stage.
        if ''.join(spaced.split())!=''.join(text.split()):return text
        for old,new in (('심장질환','심장 질환'),('가슴통증','가슴 통증')):
            spaced=spaced.replace(old,new)
        if text.endswith('없는데') and spaced.endswith('없는 데'):
            spaced=spaced[:-4]+'없는데'
        return spaced

    def reread(self,image,box):
        c=ImageOps.autocontrast(image.crop(box)).filter(ImageFilter.UnsharpMask())
        result=self.engine(cv2.cvtColor(np.array(c),cv2.COLOR_RGB2BGR),use_det=False,use_cls=False)
        return result.txts[0] if result.txts else ''


def open_image(path):
    image = Image.open(path)
    if image.width * image.height > 70_000_000:
        raise ValueError('이미지가 너무 큽니다. 7천만 픽셀 이하 캡처를 사용해 주세요.')
    return ImageOps.exif_transpose(image).convert('RGB')


def detect_frame(image):
    """Locate the connected orange vertical card; margins scale with its measured size."""
    a = np.array(image)
    hsv = cv2.cvtColor(a, cv2.COLOR_RGB2HSV)
    mask = cv2.inRange(hsv, np.array([5,55,100]), np.array([30,255,255]))
    n, labels, stats, centers = cv2.connectedComponentsWithStats(mask, 8)
    W,H = image.size
    candidates = []
    for x,y,w,h,area in stats[1:]:
        if h > H*.45 and w > W*.30 and 1.15 < h/max(w,1) < 2.6 and area > w*h*.015:
            candidates.append((int(area), [int(x),int(y),int(x+w),int(y+h)]))
    if not candidates:
        return [0,0,W,H], False
    frame = max(candidates)[1]
    return frame, True


def group_lines(boxes):
    groups=[]
    for b in sorted(boxes,key=lambda b:b.y+b.h/2):
        match=next((g for g in groups if abs((g[0].y+g[0].h/2)-(b.y+b.h/2))<max(g[0].h,b.h)*.53),None)
        if match is None: groups.append([b])
        else: match.append(b)
    lines=[]
    for group in groups:
        group.sort(key=lambda b:b.x)
        text=' '.join(b.text for b in group)
        lines.append(TextBox(text,min(b.score for b in group),[min(b.x for b in group),min(b.y for b in group),max(b.box[2] for b in group),max(b.box[3] for b in group)]))
    return sorted(lines,key=lambda b:b.y)


def analyze(path, ocr):
    import re
    from .copywriting import plan_copy, clean
    image=open_image(path)
    frame,known=detect_frame(image)
    fx,fy,fr,fb=frame; fw,fh=fr-fx,fb-fy
    if known:
        inner=[round(fx+fw*.084)+2,round(fy+fh*.045),round(fr-fw*.084)-2,round(fb-fh*.045)]
    else: inner=frame
    x0,y0,x1,y1=inner; iw,ih=x1-x0,y1-y0
    boxes=ocr.read(image.crop(inner))
    for b in boxes:
        b.box=[b.box[0]+x0,b.box[1]+y0,b.box[2]+x0,b.box[3]+y0]
    title_boxes=[b for b in boxes if b.y < y0+ih*.24 and b.h > ih*.024 and b.x < x0+iw*.72 and not re.search('출처|라이프|스마트',b.text)]
    titles=group_lines(title_boxes)
    # Short brand logo fragments at far right cannot become title lines.
    titles=[b for b in titles if b.w>iw*.23]
    corrections=[]
    for b in titles:
        if '딜할까' in b.text:
            alternative=ocr.reread(image,b.box)
            if '덜할까' in alternative:
                corrections.append('제목의 비슷한 글자를 재인식해 보완했습니다.')
                b.text=b.text.replace('딜할까','덜할까')
        b.text=ocr.space(b.text)
    title='\n'.join(clean(b.text) for b in titles[:3])
    source_boxes=[b for b in boxes if '출처' in b.text and b.y<y0+ih*.18]
    source=clean(re.sub(r'^.*?출처\s*[-–:·]?\s*','',source_boxes[0].text)) if source_boxes else ''
    publishers=['코메디닷컴','메디컬투데이','스포츠경향','전자신문','하이닥','헬스조선','동아일보','중앙일보','조선일보','서울신문','경향신문','한겨레','연합뉴스','매일경제','한국경제','뉴시스','뉴스1','세계일보','머니투데이','국민일보']
    if source=='스프츠경향':
        source='스포츠경향';corrections.append('출처의 유사 글자를 매체명 사전과 대조했습니다.')
    if not source:
        for b in boxes:
            if b.y<y0+ih*.12 and b.x>x0+iw*.45 and b.h<ih*.04:
                source=next((p for p in publishers if p in b.text.replace(' ','')),'')
                if source:break
    subtitles=[b for b in boxes if y0+ih*.58 < b.y < y0+ih*.88 and b.x < x0+iw*.16 and b.w>iw*.12 and b.h>ih*.012 and not re.search('본.?영상|생성된|가상인물|포함되어|Shorts|Miraeasset',b.text,re.I)]
    sub_lines=group_lines(subtitles)
    subtitle=ocr.space(clean(sub_lines[-1].text)) if sub_lines else ''
    top=max((b.box[3] for b in titles),default=y0)+max(8,ih*.008)
    bottom=min((b.y for b in sub_lines),default=y1)-max(12,ih*.025)
    # Crop only the main photograph; internal explanatory callout labels stay.
    crop=[int(x0),int(top),int(x1),int(bottom)]
    warnings=[]
    if not known: warnings.append('원본 테두리를 찾지 못했습니다. 사진 범위를 확인해 주세요.')
    if not source: warnings.append('출처를 읽지 못했습니다. 출처 입력이 필요합니다.')
    if not title: warnings.append('제목 인식 실패: 제목을 입력해 주세요.')
    if titles and min(b.score for b in titles)<.82: warnings.append('제목의 OCR 신뢰도가 낮습니다. 오탈자를 확인해 주세요.')
    if bottom-top<ih*.30: warnings.append('사진 영역이 너무 좁습니다. 범위를 직접 지정해 주세요.')
    copy=plan_copy(title,subtitle,' '.join(b.text for b in boxes))
    warnings.extend(copy.pop('warnings'))
    return dict(input=str(Path(path).resolve()),title=title,subtitle_original=subtitle,source=source,
                crop=crop,image_size=list(image.size),frame=frame,known_frame=known,
                ocr=[asdict(b) for b in boxes],warnings=warnings,notices=corrections,**copy)
