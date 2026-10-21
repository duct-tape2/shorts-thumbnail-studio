import json
import os
import queue
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from PIL import Image
from .paths import ROOT, ASSETS, DATA, OUTPUT, setup_fonts, ensure_dirs
from .copywriting import safe_filename


class PhotoCraft:
    def __init__(self, workspace):
        cli=ROOT/'vendor/photocraft/photocraft-cli.exe'
        self.workspace=Path(workspace)
        self.process=subprocess.Popen([str(cli),'serve','--automation-read-root',str(workspace),
                                       '--automation-write-root',str(workspace)],
                                      stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                      text=True,encoding='utf-8',errors='replace',
                                      creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        self.responses=queue.Queue();self.counter=0;self.errors=[]
        def reader():
            for line in self.process.stdout:
                try:self.responses.put(json.loads(line))
                except ValueError:pass
            self.responses.put({'ok':False,'error':'PhotoCraft가 종료되었습니다.'})
        def stderr():
            for line in self.process.stderr:self.errors.append(line[-1000:])
        threading.Thread(target=reader,daemon=True).start()
        threading.Thread(target=stderr,daemon=True).start()

    def rpc(self,method,**params):
        self.counter+=1
        self.process.stdin.write(json.dumps(dict(id=self.counter,method=method,params=params),ensure_ascii=False)+'\n')
        self.process.stdin.flush()
        try:r=self.responses.get(timeout=90)
        except queue.Empty:
            self.close()
            raise RuntimeError('PhotoCraft 처리 시간이 초과되었습니다.')
        if not r.get('ok'):raise RuntimeError(r.get('error','PhotoCraft 오류'))
        return r['result']

    def run(self,command,**params):return self.rpc('engine.execute',command=command,params=params)

    def close(self):
        if self.process.poll() is None:
            try:self.process.stdin.close();self.process.wait(timeout=3)
            except (OSError,subprocess.TimeoutExpired):self.process.kill();self.process.wait(timeout=3)


def flatten(layers):
    for l in layers:
        yield l
        yield from flatten(l.get('children',[]))


def text_bounds(pc,layer):return pc.run('type.info',layer=layer)['bounds']


def centered(pc,layer,x,y):
    b=text_bounds(pc,layer)
    pc.run('type.edit',layer=layer,move=[x-(b[0]+b[2])/2,y-(b[1]+b[3])/2])


def fit_lines(pc,layer,text,maxwidth,maxlines,size):
    """Keep the font size fixed. Reflow words using the actual renderer's glyph bounds."""
    words=text.replace('\n',' ').split()
    if not words:raise ValueError('빈 문구는 출력할 수 없습니다.')
    pc.run('type.setStyle',layer=layer,size=size,leading=size*1.13)
    def width(t):
        pc.run('type.edit',layer=layer,text=t)
        b=text_bounds(pc,layer);return b[2]-b[0]
    candidates=[]
    if width(' '.join(words))<=maxwidth:candidates.append([' '.join(words)])
    for i in range(1,len(words)):
        lines=[' '.join(words[:i]),' '.join(words[i:])]
        ws=[width(t) for t in lines]
        if max(ws)<=maxwidth:candidates.append(lines)
    if maxlines>=3 and not candidates:
        for i in range(1,len(words)-1):
            for j in range(i+1,len(words)):
                lines=[' '.join(words[:i]),' '.join(words[i:j]),' '.join(words[j:])]
                if max(width(t) for t in lines)<=maxwidth:candidates.append(lines)
    # Prefer the supplied two-line split if it already fits; otherwise balance widths.
    original=text.split('\n')
    if 1<len(original)<=maxlines and all(width(t)<=maxwidth for t in original):chosen=original
    elif candidates:
        minlines=min(len(c) for c in candidates)
        candidates=[c for c in candidates if len(c)==minlines]
        chosen=min(candidates,key=lambda c:sum((len(t)-sum(map(len,c))/len(c))**2 for t in c))
    else:
        raise ValueError('고정 글꼴 크기로 문구가 들어가지 않습니다. 문구를 간결하게 수정해 주세요.')
    if len(chosen)>maxlines:raise ValueError('문구 줄 수가 너무 많습니다.')
    pc.run('type.edit',layer=layer,text='\n'.join(chosen))
    return chosen


def validate_plan(plan):
    for key in ('title','caption','aux','source','emphasis'):
        if not str(plan.get(key,'')).strip():raise ValueError(f'{key}: 내용이 비어 있습니다. 편집 후 다시 만들어 주세요.')
    if plan['emphasis'] not in plan['title']:raise ValueError('강조어는 제목에 들어 있는 연속된 단어여야 합니다.')
    x0,y0,x1,y1=plan['crop'];w,h=plan['image_size']
    if not (0<=x0<x1<=w and 0<=y0<y1<=h and x1-x0>=100 and y1-y0>=100):
        raise ValueError('사진 범위를 다시 지정해 주세요.')


def render(plan, output_root=None, progress=lambda s:None):
    import shutil
    ensure_dirs();setup_fonts();validate_plan(plan)
    job=DATA/'jobs'/uuid.uuid4().hex
    job.mkdir(parents=True)
    # Scoped copies let PhotoCraft read only the job's assets, with no user-folder authority.
    shutil.copy2(ASSETS/'template.psd',job/'template.psd')
    image=Image.open(plan['input']).convert('RGB')
    crop=plan['crop'];photo=image.crop(crop)
    photo.save(job/'photo.png')
    pc=PhotoCraft(job)
    try:
        progress('PhotoCraft 템플릿 배치')
        pc.rpc('doc.open',path=str(job/'template.psd'))
        layers=list(flatten(pc.rpc('doc.inspect')['layers']))
        def named(name):return next(l['id'] for l in layers if l['name']==name)
        title=next(l['id'] for l in layers if l['kind']=='Type')
        aux=named('과도한 응원 주의');caption=named('실제로 스포츠 경기 관람과');source=named('출처 - 코메디닷컴')
        frame=named('Layer 2');pill=named('Rectangle 1')
        for layer,txt in ((title,plan['title']),(aux,plan['aux']),(caption,plan['caption']),(source,'출처 - '+plan['source'])):
            pc.run('type.edit',layer=layer,text=txt)
        for layer,size in ((title,95),(aux,82)):
            pc.run('type.setStyle',layer=layer,font='Noto Sans CJK KR',fontStyle='Black',weight=900,size=size,
                   tracking=-50,color='#ffffff',align='center')
        pc.run('type.setStyle',layer=caption,font='SUIT',fontStyle='SemiBold',weight=600,size=60,
               tracking=-50,color='#000000',align='center')
        pc.run('type.setStyle',layer=source,font='SUIT',fontStyle='ExtraLight',weight=200,size=45,
               tracking=-50,color='#ffffff',align='center')
        lines=fit_lines(pc,title,plan['title'],970,3,95)
        centered(pc,title,540,225 if len(lines)<3 else 185)
        actual='\n'.join(lines);em=plan['emphasis']
        if em not in actual:
            # A line break may split a phrase: highlight the contiguous character span including newline.
            a=actual.replace('\n',' ');idx=a.find(em)
        else:idx=actual.find(em)
        if idx<0:raise ValueError('줄바꿈 후 강조어 위치를 찾지 못했습니다.')
        pc.run('type.setStyle',layer=title,range=[idx,idx+len(em)],color='#f58220')
        if text_bounds(pc,aux)[2]-text_bounds(pc,aux)[0]>950:raise ValueError('보조 문구가 깁니다. 13자 안팎으로 줄여 주세요.')
        centered(pc,aux,540,1247)
        caps=fit_lines(pc,caption,plan['caption'],875,2,60)
        if len(caps)==2:
            pc.run('shape.edit',layer=pill,kind='roundedRect',rect=[61,1323,958,149],radii=60)
            centered(pc,caption,540,1397.5)
        else:centered(pc,caption,540,1382.5)
        centered(pc,source,540,1639)
        # A small overscan eliminates a fractional one-pixel gap at any edge.
        scale=max(1084/photo.width,1224/photo.height)*100
        placed=pc.rpc('doc.place',path=str(job/'photo.png'),scale=scale,center=[540,970])
        pc.run('layer.moveTo',layer=placed['layer'],target=frame,position='below')
        progress('문구·경계·출력 검사')
        for layer,region in ((title,[30,38,1050,350]),(aux,[35,1180,1045,1310]),(caption,[80,1320,1000,1475]),(source,[50,1595,1030,1690])):
            b=text_bounds(pc,layer)
            if b[0]<region[0] or b[1]<region[1] or b[2]>region[2] or b[3]>region[3]:
                raise ValueError('텍스트가 템플릿 안전 영역을 벗어났습니다. 문구를 확인해 주세요.')
        staged=job/'render.png';pc.rpc('doc.save',path=str(staged))
        with Image.open(staged) as result:
            result.load()
            if result.size!=(1080,1920):raise RuntimeError('출력 규격 검사 실패')
        day=datetime.now(timezone(timedelta(hours=9))).strftime('%y%m%d')
        dest=Path(output_root or OUTPUT)/day;dest.mkdir(parents=True,exist_ok=True)
        target=dest/safe_filename(plan['title'])
        # Never overwrite a user file. Revisions are explicit and retain the title.
        base=target.stem;i=2
        while target.exists():target=dest/f'{base} {i}.png';i+=1
        with open(target,'xb') as f:f.write(staged.read_bytes())
        audit=dict(plan,output=str(target),title_lines=lines,caption_lines=caps,
                   sizes=dict(title=95,aux=82,caption=60,source=45),photocraft='0.11.1')
        (job/'report.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
        return audit
    finally:
        pc.close()
        # Only this job's exact scratch PSD and photograph are temporary.
        for name in ('template.psd','photo.png','render.png'):
            (job/name).unlink(missing_ok=True)
