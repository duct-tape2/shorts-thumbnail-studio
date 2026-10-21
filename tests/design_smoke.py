"""Generate real PhotoCraft outputs for all aspect ratios and two photo layouts."""
import json
import os
from pathlib import Path
import sys
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from studio.design import make_plan,PRESETS
from studio.design_render import render_design
from studio.paths import ROOT
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from studio.ui import Window,STYLE

out=ROOT.parent/'work/design-smoke';out.mkdir(parents=True,exist_ok=True)
reports=[]
for style,format in [('clean','shorts'),('bold','shorts'),('editorial','square'),('neon','landscape'),('warm','shorts'),('cinema','shorts')]:
    p=make_plan('혼자 떠나는 주말 여행','제목은 가운데 정렬','가볍게 챙겨 떠나세요','주말',preset=style,format=format)
    reports.append(render_design(p,out))
for layout in ['photo','split']:
    p=make_plan('새로운 하루를 시작해요','제목은 아래에','작은 변화부터 시작하세요',image=reports[0]['output'],preset='clean')
    p['layout']=layout;reports.append(render_design(p,out))
app=QApplication([]);app.setStyleSheet(STYLE)
w=Window(no_hotkey=True);w.output=out;w.show();w.modes.setCurrentWidget(w.designer)
d=w.designer;d.title.setText('혼자 떠나는 주말 여행');d.brief.setPlainText('어두운 배경, 노란 포인트. 제목은 아래 가운데 정렬.');d.subtitle.setText('가볍게 챙겨 떠나세요');d.emphasis.setText('주말');d.generate()
finished=False
def check():
    global finished
    if d.worker is None:
        assert d.report,d.status.text()
        app.processEvents();w.grab().save(str(out/'designer-ui.png'));finished=True;app.quit()
timer=QTimer();timer.timeout.connect(check);timer.start(100)
QTimer.singleShot(120000,app.quit);app.exec();w.tray.hide();assert finished
(out/'report.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf-8')
print('8 rendered designs + Qt designer workflow passed')
