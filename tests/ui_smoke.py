"""Exercise real Qt drop, queue, editor and preview code without controlling the user's desktop."""
import json
import os
from pathlib import Path
import sys
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QMimeData,QUrl,Qt,QPoint,QPointF,QTimer
from PySide6.QtGui import QDragEnterEvent,QDropEvent
from PySide6.QtWidgets import QApplication
from studio.ui import Window,STYLE

root=Path(__file__).resolve().parents[2]/'work'
app=QApplication([]);app.setStyleSheet(STYLE)
w=Window(no_hotkey=True);w.output=root/'ui-test-output';w.show()
app.processEvents();w.grab().save(str(root/'studio-ui-empty.png'))
files=sys.argv[1:]
mime=QMimeData();mime.setUrls([QUrl.fromLocalFile(f) for f in files])
enter=QDragEnterEvent(QPoint(50,100),Qt.DropAction.CopyAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
QApplication.sendEvent(w,enter)
assert enter.isAccepted()
drop=QDropEvent(QPointF(50,100),Qt.DropAction.CopyAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
QApplication.sendEvent(w,drop)
assert drop.isAccepted()
completed=False
def check():
    global completed
    if w.worker is None and len(w.jobs)==len(files) and not any(j['state']=='대기' for j in w.jobs):
        completed=True
        w.list.setCurrentRow(len(w.jobs)-1)
        app.processEvents()
        w.grab().save(str(root/'studio-ui.png'))
        w.resize(1024,720);app.processEvents();w.grab().save(str(root/'studio-ui-compact.png'))
        assert w.body.width()>650
        assert w.fields['caption'].toPlainText()==w.jobs[-1]['report']['caption']
        w.tabs.setCurrentIndex(1);app.processEvents();w.grab().save(str(root/'studio-ui-original.png'))
        (root/'studio-ui-test.json').write_text(json.dumps([dict(state=j['state'],output=(j.get('report') or {}).get('output'),error=j.get('error')) for j in w.jobs],ensure_ascii=False),encoding='utf-8')
        app.quit()
timer=QTimer();timer.timeout.connect(check);timer.start(150)
QTimer.singleShot(90000,app.quit)
app.exec()
assert completed,'Qt queue timed out'
assert all(j['state']=='완료' for j in w.jobs),w.jobs
w.tray.hide()
