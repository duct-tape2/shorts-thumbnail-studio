"""Offline design planning. A finite grammar, not a general language model."""
import re

PRESETS = {
    'clean': dict(name='깔끔한 정보형',background='#F3F5F8',foreground='#142B46',accent='#F58220',layout='split'),
    'bold': dict(name='강렬한 타이틀',background='#142B46',foreground='#FFFFFF',accent='#FFD447',layout='poster'),
    'editorial': dict(name='차분한 매거진',background='#EAE7E0',foreground='#282B2D',accent='#387B77',layout='split'),
    'neon': dict(name='선명한 테크',background='#15162B',foreground='#FFFFFF',accent='#67E8F9',layout='poster'),
    'warm': dict(name='따뜻한 일상',background='#FFF1E5',foreground='#53342C',accent='#D85D38',layout='split'),
    'cinema': dict(name='사진 중심',background='#17212A',foreground='#FFFFFF',accent='#FFD447',layout='photo'),
}
FORMATS={'shorts':(1080,1920),'square':(1080,1080),'landscape':(1280,720)}
COLORS={'주황':'#F58220','노랑':'#FFD447','노란':'#FFD447','빨강':'#E44848','빨간':'#E44848',
        '파랑':'#3183E7','파란':'#3183E7','초록':'#29A574','녹색':'#29A574','보라':'#9764D8',
        '분홍':'#F08CAC','민트':'#63D7BF','하늘':'#67C9E8','흰색':'#FFFFFF','하얀':'#FFFFFF',
        '검정':'#14171C','검은':'#14171C','남색':'#142B46','베이지':'#EAE7E0'}

def contrast(hexcolor):
    rgb=[int(hexcolor[i:i+2],16)/255 for i in (1,3,5)]
    lum=sum(v*w for v,w in zip([v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in rgb],[.2126,.7152,.0722]))
    return '#142B46' if lum>.42 else '#FFFFFF'

def make_plan(title,brief='',subtitle='',emphasis='',source='',image='',preset='auto',format='shorts'):
    title=title.strip();brief=brief.strip()
    if not title:raise ValueError('썸네일에 넣을 큰 제목을 입력해 주세요.')
    if len(title)>100:raise ValueError('제목은 100자 이내로 입력해 주세요.')
    if len(subtitle)>100:raise ValueError('보조 문구는 100자 이내로 입력해 주세요.')
    if len(brief)>2000:raise ValueError('디자인 설명은 2,000자 이내로 입력해 주세요.')
    if format not in FORMATS:raise ValueError('지원하지 않는 크기입니다.')
    choices=[('cinema',r'영화|시네마|사진.?중심|사진.?가득'),('neon',r'네온|테크|사이버|게임'),
             ('editorial',r'매거진|잡지|차분|미니멀'),('warm',r'따뜻|감성|브이로그|일상'),('bold',r'강렬|임팩트|굵게|강하게')]
    chosen=preset if preset!='auto' else next((key for key,pattern in choices if re.search(pattern,brief)),'clean')
    if chosen not in PRESETS:raise ValueError('지원하지 않는 스타일입니다.')
    plan=dict(PRESETS[chosen],version=1,mode='design',preset=chosen,format=format,title=title,
              subtitle=subtitle.strip(),source=source.strip(),image=image,brief=brief,emphasis=emphasis.strip(),align='left',title_position='top')
    recognized=[]
    for word,color in COLORS.items():
        if re.search(re.escape(word)+r'(?:색)?\s*(?:으로\s*)?(?:배경|바탕)',brief):
            plan['background']=color;recognized.append('배경색')
        if re.search(re.escape(word)+r'(?:색)?\s*(?:으로\s*)?(?:포인트|강조)',brief):
            plan['accent']=color;recognized.append('강조색')
    for key,pattern in [('background',r'(?:배경|바탕)\s*(?:색)?\s*[:=]?\s*(#[0-9a-fA-F]{6})'),('accent',r'(?:포인트|강조)\s*(?:색)?\s*[:=]?\s*(#[0-9a-fA-F]{6})')]:
        match=re.search(pattern,brief)
        if match:plan[key]=match.group(1).upper();recognized.append(key)
    if re.search(r'어두운|다크|검정\s*배경',brief):plan['background']='#142B46';recognized.append('어두운 배경')
    if re.search(r'밝은|화이트',brief):plan['background']='#F3F5F8';recognized.append('밝은 배경')
    if re.search(r'가운데\s*(?:정렬|제목)|중앙\s*정렬|제목.*가운데',brief):plan['align']='center';recognized.append('가운데 정렬')
    if re.search(r'제목.*(?:아래|하단)|(?:아래|하단).*제목',brief):plan['title_position']='bottom';recognized.append('제목 아래')
    if re.search(r'사진.?가득|꽉.?찬.?사진|전체.?사진',brief):plan['layout']='photo';recognized.append('사진 전체')
    if re.search(r'텍스트.?중심|글자.?중심|글씨.?중심',brief):plan['layout']='poster';recognized.append('텍스트 중심')
    plan['foreground']=contrast(plan['background'])
    warnings=[]
    if emphasis and emphasis not in title:raise ValueError('강조할 말은 제목에 포함된 문구여야 합니다.')
    if not image and plan['layout']=='photo':plan['layout']='poster';warnings.append('사진이 없어 텍스트 중심으로 만들었어요.')
    if brief:warnings.append('오프라인 모드는 스타일·색상·제목 위치·정렬 키워드를 해석합니다. 자유로운 이미지 생성은 하지 않습니다.')
    plan['warnings']=warnings
    plan['summary']=f"{PRESETS[chosen]['name']} / {plan['background']} / {'가운데' if plan['align']=='center' else '왼쪽'} 정렬 / 제목 {'아래' if plan['title_position']=='bottom' else '위'}"
    return plan

def validate_design(plan):
    for key in ('background','foreground','accent'):
        if not re.fullmatch(r'#[0-9a-fA-F]{6}',str(plan.get(key,''))):raise ValueError('잘못된 색상: '+key)
    if plan.get('format') not in FORMATS:raise ValueError('잘못된 출력 크기')
    if plan.get('layout') not in {'split','photo','poster'}:raise ValueError('잘못된 사진 배치')
    if plan.get('align') not in {'left','center'}:raise ValueError('잘못된 정렬')
    if plan.get('title_position') not in {'top','bottom'}:raise ValueError('잘못된 제목 위치')
    if not 1<=len(plan.get('title','').strip())<=100:raise ValueError('제목 길이를 확인해 주세요.')
    if len(plan.get('subtitle',''))>100 or len(plan.get('source',''))>80:raise ValueError('문구가 너무 깁니다.')
    if plan.get('emphasis') and plan['emphasis'] not in plan['title']:raise ValueError('강조어가 제목에 없습니다.')
