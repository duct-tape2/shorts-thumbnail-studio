import json
import uuid
from itertools import combinations
from pathlib import Path
from datetime import datetime,timezone,timedelta
from PIL import Image,ImageOps
from .paths import DATA,OUTPUT,ensure_dirs,setup_fonts
from .render import PhotoCraft,text_bounds
from .design import FORMATS,validate_design,contrast
from .copywriting import safe_filename

def render_design(plan,output_root=None,progress=lambda text:None):
    validate_design(plan);ensure_dirs();setup_fonts()
    job=DATA/'design-jobs'/uuid.uuid4().hex;job.mkdir(parents=True)
    pc=PhotoCraft(job)
    W,H=FORMATS[plan['format']];unit=W/1080;pad=round(W*.075)
    try:
        progress('디자인을 구성하고 있어요.')
        pc.rpc('doc.new',width=W,height=H,background=plan['background'],name=plan['title'])
        def shape(rect,color,name,rounded=False):
            return pc.run('shape.create',kind='roundedRect' if rounded else 'rect',rect=rect,fill=color,radii=24*unit,name=name)
        def add_photo(rect):
            x,y,w,h=map(round,rect)
            with Image.open(plan['image']) as original:
                picture=ImageOps.exif_transpose(original).convert('RGB')
                picture=ImageOps.fit(picture,(w,h),method=Image.Resampling.LANCZOS)
                picture.save(job/'photo.png')
            pc.rpc('doc.place',path=str(job/'photo.png'),center=[x+w/2,y+h/2],scale=100)
        layout=plan['layout'];bottom=plan['title_position']=='bottom'
        title_y=H*.12;title_maxh=H*.31;title_maxw=W-2*pad
        if layout=='photo' and plan.get('image'):
            add_photo([0,0,W,H])
            y=H*.53 if bottom else 0
            shape([0,y,W,H*.47],plan['background'],'Title backdrop')
            title_y=y+H*.065;title_maxh=H*.26
        elif layout=='split' and plan.get('image'):
            if H>=W:
                photo_y=H*.08 if bottom else H*.43
                add_photo([pad,photo_y,W-2*pad,H*.43])
                title_y=H*.58 if bottom else H*.1;title_maxh=H*.24
            else:
                add_photo([W*.56,H*.08,W*.38,H*.84])
                title_maxw=W*.43;title_y=H*.18;title_maxh=H*.42
        elif plan.get('image'):
            add_photo([pad,H*.10 if bottom else H*.49,W-2*pad,H*.35])
            title_y=H*.56 if bottom else H*.11;title_maxh=H*.26
        else:
            # Original vector composition: no company background, logo or PSD.
            shape([W*.68,H*.12 if bottom else H*.60,W*.32,H*.22],plan['accent'],'Accent block')
            pc.run('shape.create',kind='ellipse',rect=[W*.10,H*.10 if bottom else H*.57,W*.42,W*.42],fill=None,stroke={'color':plan['accent'],'width':8*unit},name='Outline circle')
            shape([pad,H*.80,W*.48,6*unit],plan['accent'],'Accent rule')
            title_y=H*.42 if bottom else H*.2;title_maxh=H*.32
        shape([(W-68*unit)/2 if plan['align']=='center' else pad,title_y-30*unit,68*unit,7*unit],plan['accent'],'Headline marker')
        def text_layer(text,size,color,name):
            pc.run('type.create',x=pad,y=title_y,text=text,name=name,font='Noto Sans CJK KR',fontStyle='Black',weight=900,size=size,color=color,tracking=-30,align=plan['align'])
            layers=pc.rpc('doc.inspect')['layers']
            return next(layer['id'] for layer in layers if layer['name']==name)
        def wrap(layer,text,size,maxw,maxh,maxlines):
            # Reflow by measured glyph bounds; break long unspaced Korean titles.
            for fontsize in range(round(size),round(size*.55)-1,-4):
                pc.run('type.setStyle',layer=layer,size=fontsize,leading=fontsize*1.16)
                words=text.replace('\n',' ').split();lines=[];line=''
                for word in words:
                    candidate=(line+' '+word).strip();pc.run('type.edit',layer=layer,text=candidate)
                    b=text_bounds(pc,layer)
                    if b[2]-b[0]<=maxw:line=candidate;continue
                    if line:lines.append(line);line=''
                    for char in word:
                        pc.run('type.edit',layer=layer,text=line+char);b=text_bounds(pc,layer)
                        if b[2]-b[0]>maxw and line:lines.append(line);line=char
                        else:line+=char
                if line:lines.append(line)
                if 2<=len(lines)<=3 and len(words)<=16:
                    candidates=[]
                    for breaks in combinations(range(1,len(words)),len(lines)-1):
                        ends=(0,)+breaks+(len(words),)
                        candidate=[' '.join(words[ends[i]:ends[i+1]]) for i in range(len(ends)-1)]
                        candidates.append(candidate)
                    for candidate in sorted(candidates,key=lambda c:max(map(len,c))-min(map(len,c)))[:8]:
                        pc.run('type.edit',layer=layer,text='\n'.join(candidate));cb=text_bounds(pc,layer)
                        if cb[2]-cb[0]<=maxw and cb[3]-cb[1]<=maxh:lines=candidate;break
                pc.run('type.edit',layer=layer,text='\n'.join(lines));b=text_bounds(pc,layer)
                if len(lines)<=maxlines and b[3]-b[1]<=maxh:return lines,b,fontsize
            raise ValueError('문구가 영역보다 깁니다. 제목이나 보조 문구를 줄여 주세요.')
        title=text_layer(plan['title'],112*unit,plan['foreground'],'Title')
        lines,b,size=wrap(title,plan['title'],112*unit,title_maxw,title_maxh,4)
        x=pad+(title_maxw-(b[2]-b[0]))/2 if plan['align']=='center' else pad
        pc.run('type.edit',layer=title,move=[x-b[0],title_y-b[1]])
        text='\n'.join(lines);em=plan.get('emphasis','')
        if em:
            direct=text.find(em)
            if direct>=0:pc.run('type.setStyle',layer=title,range=[direct,direct+len(em)],color=plan['accent'])
            else:plan=dict(plan,warnings=list(plan.get('warnings',[]))+['강조어가 줄 사이에 나뉘어 강조를 적용하지 않았습니다. 제목을 짧게 조정해 주세요.'])
        title_bounds=text_bounds(pc,title)
        if plan.get('subtitle'):
            sub=text_layer(plan['subtitle'],42*unit,plan['foreground'],'Subtitle')
            sublines,sb,_=wrap(sub,plan['subtitle'],42*unit,title_maxw,H*.11,3)
            sx=pad+(title_maxw-(sb[2]-sb[0]))/2 if plan['align']=='center' else pad
            pc.run('type.edit',layer=sub,move=[sx-sb[0],title_bounds[3]+28*unit-sb[1]])
        if plan.get('source'):
            source=text_layer(plan['source'],28*unit,plan['foreground'],'Credit')
            _,sb,_=wrap(source,plan['source'],28*unit,W-2*pad,H*.065,2)
            # A solid band keeps the optional credit readable over photographs.
            backdrop=shape([0,H*.91,W,H*.09],plan['background'],'Credit backdrop')
            pc.run('layer.moveTo',layer=source,target=next(l['id'] for l in pc.rpc('doc.inspect')['layers'] if l['name']=='Credit backdrop'),position='above')
            pc.run('type.edit',layer=source,move=[pad-sb[0],H*.94-sb[1]])
        for l in pc.rpc('doc.inspect')['layers']:
            if l['kind']=='Type':
                bounds=text_bounds(pc,l['id'])
                if bounds[0]<0 or bounds[1]<0 or bounds[2]>W or bounds[3]>H:raise ValueError('글자가 화면을 벗어났습니다. 문구를 줄여 주세요.')
        progress('PNG를 저장하고 있어요.')
        pc.rpc('doc.save',path=str(job/'render.png'))
        with Image.open(job/'render.png') as image:
            image.load()
            if image.size!=(W,H):raise RuntimeError('PNG 출력 크기 검사 실패')
        date=datetime.now(timezone(timedelta(hours=9))).strftime('%y%m%d')
        folder=Path(output_root or OUTPUT)/date;folder.mkdir(parents=True,exist_ok=True)
        target=folder/safe_filename(plan['title']);i=2
        while target.exists():target=folder/f'{Path(safe_filename(plan["title"])).stem} {i}.png';i+=1
        with target.open('xb') as f:f.write((job/'render.png').read_bytes())
        report=dict(plan,output=str(target),title_lines=lines,title_size=size,size=[W,H])
        (job/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        return report
    finally:
        pc.close()
        for name in ('photo.png','render.png'):(job/name).unlink(missing_ok=True)
