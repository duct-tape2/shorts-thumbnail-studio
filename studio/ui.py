import ctypes
import json
import os
import sys
import traceback
from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QThread, QTimer, QRect, QPoint, QUrl, QSize
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap, QDesktopServices, QAction, QIcon, QFontDatabase
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QLabel,
    QPushButton,QListWidget,QListWidgetItem,QTextEdit,QLineEdit,QFormLayout,QSplitter,
    QFileDialog,QMessageBox,QCheckBox,QSystemTrayIcon,QMenu,QFrame,QSizePolicy,
    QTabWidget,QStackedWidget,QProgressBar,QScrollArea)
from .paths import ROOT,DATA,OUTPUT,ensure_dirs
from .ocr import OCR,analyze
from .render import render


class Preview(QLabel):
    cropChanged=Signal(list)
    def __init__(self,editable=False):
        super().__init__();self.setMinimumSize(220,300);self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Expanding)
        self.setStyleSheet('background:#e7ecf2;color:#607084;padding:0;border:0;')
        self.image=None;self.crop=None;self.start=None;self.editable=editable;self.target=QRect()
        self.setText('완성되면 여기에 표시됩니다')
    def load(self,path,crop=None):
        self.image=QPixmap(str(path));self.crop=crop;self.setText('');self.update()
    def paintEvent(self,event):
        if self.image is None:return super().paintEvent(event)
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        size=self.image.size().scaled(self.size()-QSize(32,32),Qt.AspectRatioMode.KeepAspectRatio)
        self.target=QRect((self.width()-size.width())//2,(self.height()-size.height())//2,size.width(),size.height())
        p.drawPixmap(self.target,self.image)
        if self.crop:
            sx=self.target.width()/self.image.width();sy=self.target.height()/self.image.height()
            x0,y0,x1,y1=self.crop
            r=QRect(round(self.target.x()+x0*sx),round(self.target.y()+y0*sy),round((x1-x0)*sx),round((y1-y0)*sy))
            p.setPen(QPen(QColor('#f58220'),2));p.drawRect(r)
            p.fillRect(self.target.x(),self.target.y(),self.target.width(),max(0,r.y()-self.target.y()),QColor(0,0,0,70))
    def point(self,event):
        x=max(0,min(self.image.width(),(event.position().x()-self.target.x())/max(1,self.target.width())*self.image.width()))
        y=max(0,min(self.image.height(),(event.position().y()-self.target.y())/max(1,self.target.height())*self.image.height()))
        return round(x),round(y)
    def mousePressEvent(self,event):
        if self.editable and self.image is not None and event.button()==Qt.MouseButton.LeftButton:self.start=self.point(event)
    def mouseMoveEvent(self,event):
        if self.start:
            x,y=self.point(event);a,b=self.start;self.crop=[min(a,x),min(b,y),max(a,x),max(b,y)];self.update()
    def mouseReleaseEvent(self,event):
        if self.start:
            self.mouseMoveEvent(event);self.start=None
            if self.crop and self.crop[2]-self.crop[0]>20 and self.crop[3]-self.crop[1]>20:self.cropChanged.emit(self.crop)


class Worker(QThread):
    status=Signal(str);planned=Signal(dict);finishedJob=Signal(dict);failed=Signal(str)
    def __init__(self,path,output,plan=None):
        super().__init__();self.path=path;self.output=output;self.plan=plan
    def run(self):
        try:
            if self.plan is None:
                self.status.emit('한국어 OCR · 사진 영역 분석')
                self.plan=analyze(self.path,OCR())
            self.planned.emit(self.plan)
            result=render(self.plan,self.output,self.status.emit)
            self.finishedJob.emit(result)
        except Exception as e:
            self.failed.emit(str(e))
            DATA.mkdir(exist_ok=True,parents=True)
            with (DATA/'errors.log').open('a',encoding='utf-8') as f:f.write(traceback.format_exc()+'\n')


class Window(QMainWindow):
    hotkey=Signal()
    def __init__(self,no_hotkey=False):
        super().__init__();ensure_dirs()
        for font in (ROOT/'assets/fonts').glob('*'):QFontDatabase.addApplicationFont(str(font))
        self.setWindowTitle('쇼츠 썸네일 스튜디오');self.resize(1280,850)
        self.setMinimumSize(1000,700);self.setAcceptDrops(True)
        self.jobs=[];self.active=None;self.worker=None;self.snapshot=None;self.hook=None;self.capture_pending=False
        self.settings_path=DATA/'settings.json'
        try:self.settings=json.loads(self.settings_path.read_text(encoding='utf-8'))
        except (OSError,ValueError):self.settings={}
        self.output=Path(self.settings.get('output',str(OUTPUT)))
        self._build();self._tray();self.hotkey.connect(self.begin_capture)
        from custom_capture.overlay import SelectionOverlay
        self.overlay=SelectionOverlay();self.overlay.selection_made.connect(self.capture_done)
        self.overlay.cancelled.connect(self.capture_cancelled)
        if not no_hotkey:
            # Do not steal the shortcut from the user's already running original program.
            kernel=ctypes.windll.kernel32;kernel.OpenMutexW.restype=ctypes.c_void_p
            handle=kernel.OpenMutexW(0x00100000,False,'Local\\CustomCapture_SingleInstance')
            if handle:
                kernel.CloseHandle(ctypes.c_void_p(handle))
                self.capture_hint.setText('기존 캡처 앱이 실행 중입니다.\n새 캡처는 위 버튼을 이용하세요.')
            else:
                from custom_capture.keyboard_hook import WinShiftSKeyboardHook
                self.hook=WinShiftSKeyboardHook(self.hotkey.emit)
                try:self.hook.start()
                except Exception as e:self.status.setText('단축키 연결 실패 · 화면 캡처 버튼을 사용해 주세요: '+str(e))

    def _build(self):
        def label(text,name=None):
            w=QLabel(text)
            if name:w.setObjectName(name)
            return w
        def button(text,fn,name=None):
            w=QPushButton(text);w.clicked.connect(fn);w.setCursor(Qt.CursorShape.PointingHandCursor)
            if name:w.setObjectName(name)
            return w
        root=QWidget();self.setCentralWidget(root)
        outer=QHBoxLayout(root);outer.setContentsMargins(0,0,0,0);outer.setSpacing(0)
        rail=QFrame();rail.setObjectName('rail');rail.setFixedWidth(238);outer.addWidget(rail)
        side=QVBoxLayout(rail);side.setContentsMargins(20,28,20,20);side.setSpacing(12)
        side.addWidget(label('스마트라이프','brand'));side.addWidget(label('썸네일 스튜디오','railSubtitle'));side.addSpacing(18)
        side.addWidget(button('＋  캡처 파일 추가',self.pick,'importButton'))
        side.addWidget(button('화면 캡처',self.begin_capture,'captureButton'))
        self.capture_hint=label('단축키  Win + Shift + S','railHint');self.capture_hint.setWordWrap(True);side.addWidget(self.capture_hint)
        side.addSpacing(18)
        queue_head=QHBoxLayout();queue_head.addWidget(label('작업 목록','queueTitle'));queue_head.addStretch()
        self.queue_count=label('0개','railHint');queue_head.addWidget(self.queue_count);side.addLayout(queue_head)
        self.queue_empty=label('추가한 파일이\n여기에 모입니다.','railHint');side.addWidget(self.queue_empty)
        self.list=QListWidget();self.list.setObjectName('queue');self.list.setIconSize(QSize(32,52));self.list.setSpacing(5)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.currentRowChanged.connect(self.select);side.addWidget(self.list,1)
        self.settings_toggle=button('설정 펼치기',self.toggle_settings,'railSettings');side.addWidget(self.settings_toggle)
        self.settings_panel=QWidget();settings=QVBoxLayout(self.settings_panel);settings.setContentsMargins(0,4,0,0)
        self.auto_capture=QCheckBox('캡처 후 자동 제작');self.auto_capture.setChecked(True);settings.addWidget(self.auto_capture)
        self.startup=QCheckBox('로그인 시 자동 실행');self.startup.setChecked(self.startup_file().exists());self.startup.toggled.connect(self.toggle_startup);settings.addWidget(self.startup)
        settings.addWidget(button('저장 위치 변경',self.change_output,'railSettings'));side.addWidget(self.settings_panel);self.settings_panel.hide()
        side.addWidget(label('인터넷 연결 없이 사용','railHint'))
        workspace=QWidget();outer.addWidget(workspace,1);main=QVBoxLayout(workspace);main.setContentsMargins(28,24,28,16);main.setSpacing(20)
        header=QHBoxLayout();heading=QVBoxLayout();heading.setSpacing(5)
        heading.addWidget(label('썸네일 만들기','pageTitle'));heading.addWidget(label('파일을 넣고, 완성된 PNG를 확인하세요.','muted'))
        header.addLayout(heading);header.addStretch();header.addWidget(button('완성본 폴더 열기',self.open_output));main.addLayout(header)
        self.body=QStackedWidget();main.addWidget(self.body,1)
        empty=QFrame();empty.setObjectName('dropZone');ev=QVBoxLayout(empty);ev.setContentsMargins(48,40,48,40);ev.setSpacing(16);ev.addStretch()
        emblem=label('＋','dropMark');emblem.setAlignment(Qt.AlignmentFlag.AlignCenter);ev.addWidget(emblem)
        title=label('캡처를 여기에 놓아주세요','emptyTitle');title.setAlignment(Qt.AlignmentFlag.AlignCenter);ev.addWidget(title)
        desc=label('여러 장을 한 번에 넣어도 괜찮아요.\n사진과 문구를 정리해 PNG로 저장합니다.','emptyHint');desc.setAlignment(Qt.AlignmentFlag.AlignCenter);ev.addWidget(desc)
        add=button('캡처 파일 선택',self.pick,'importButton');add.setFixedWidth(190);ev.addWidget(add,0,Qt.AlignmentFlag.AlignHCenter)
        formats=label('PNG, JPG, WEBP, BMP','muted');formats.setAlignment(Qt.AlignmentFlag.AlignCenter);ev.addWidget(formats);ev.addStretch()
        self.body.addWidget(empty)
        editing=QWidget();edit_layout=QHBoxLayout(editing);edit_layout.setContentsMargins(0,0,0,0);edit_layout.setSpacing(20)
        viewer=QWidget();vl=QVBoxLayout(viewer);vl.setContentsMargins(0,0,0,0);vl.setSpacing(10)
        self.preview_title=label('미리보기','sectionTitle');vl.addWidget(self.preview_title)
        self.tabs=QTabWidget();self.tabs.setDocumentMode(True);vl.addWidget(self.tabs,1)
        self.result=Preview();self.original=Preview(True);self.original.cropChanged.connect(self.crop_changed)
        self.tabs.addTab(self.result,'완성본');self.tabs.addTab(self.original,'원본 / 사진 범위')
        self.preview_hint=label('완성본은 자동으로 저장됩니다.','muted');self.preview_hint.setWordWrap(True);vl.addWidget(self.preview_hint)
        self.tabs.currentChanged.connect(lambda i:self.preview_hint.setText('원본 위를 드래그해서 사용할 사진 범위를 바꾸세요.' if i else '완성본은 자동으로 저장됩니다.'))
        edit_layout.addWidget(viewer,1)
        editor=QFrame();editor.setObjectName('editor');editor.setFixedWidth(300);right=QVBoxLayout(editor);right.setContentsMargins(20,20,20,20);right.setSpacing(12)
        right.addWidget(label('문구 다듬기','sectionTitle'));right.addWidget(label('필요한 부분만 수정하세요.','muted'))
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.Shape.NoFrame);right.addWidget(scroll,1)
        self.form_widget=QWidget();form=QVBoxLayout(self.form_widget);form.setContentsMargins(0,2,6,4);form.setSpacing(8);self.fields={}
        for key,text in [('title','큰 제목'),('emphasis','주황색으로 강조할 말'),('aux','보조 문구'),('caption','상자 안 문구'),('source','출처')]:
            field_label=label(text,'fieldLabel');form.addWidget(field_label)
            w=QTextEdit() if key in ('title','caption') else QLineEdit();self.fields[key]=w
            w.setAccessibleName(text);field_label.setBuddy(w)
            if isinstance(w,QTextEdit):w.setFixedHeight(82 if key=='title' else 72);w.setAcceptRichText(False)
            else:w.setMinimumHeight(38)
            if key=='emphasis':w.setObjectName('emphasisField')
            form.addWidget(w);form.addSpacing(6)
        form.addStretch();scroll.setWidget(self.form_widget);self.form_widget.setEnabled(False)
        self.notes=label('파일 분석이 끝나면 문구를 수정할 수 있어요.','notice');self.notes.setWordWrap(True);right.addWidget(self.notes)
        self.regen=button('수정 내용으로 다시 만들기',self.regenerate,'regenerate');self.regen.setEnabled(False);right.addWidget(self.regen)
        edit_layout.addWidget(editor);self.body.addWidget(editing)
        footer=QVBoxLayout();footer.setSpacing(8)
        self.progress=QProgressBar();self.progress.setFixedHeight(3);self.progress.setTextVisible(False);self.progress.setRange(0,0);self.progress.hide();footer.addWidget(self.progress)
        self.status=label('준비됐어요. 캡처 파일을 추가해 주세요.','status');self.status.setWordWrap(True);footer.addWidget(self.status)
        self.path_label=label('저장 위치  '+str(self.output),'savePath');self.path_label.setToolTip(str(self.output));self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse);self.path_label.setWordWrap(True);footer.addWidget(self.path_label)
        main.addLayout(footer)
        from .designer import DesignPanel
        self.designer=DesignPanel(Preview,lambda:self.output)
        self.designer.captureRequested.connect(self.begin_capture);self.designer.outputRequested.connect(self.change_output)
        self.modes=QTabWidget();self.modes.setDocumentMode(True)
        self.takeCentralWidget()
        if (ROOT/'assets/template.psd').exists():self.modes.addTab(root,'캡처 자동 변환')
        else:root.hide();root.setParent(self)
        self.modes.addTab(self.designer,'디자인 설명으로 만들기')
        self.setCentralWidget(self.modes)

    def toggle_settings(self):
        visible=not self.settings_panel.isVisible();self.settings_panel.setVisible(visible)
        self.settings_toggle.setText('설정 접기' if visible else '설정 펼치기')

    def refresh_queue(self):
        self.queue_count.setText(str(len(self.jobs))+'개');self.queue_empty.setVisible(not self.jobs)
        for i,j in enumerate(self.jobs):
            title=(j.get('plan') or {}).get('title') or Path(j['path']).stem
            state='확인 권장' if j['state']=='완료' and (j.get('report') or {}).get('warnings') else j['state']
            self.list.item(i).setText(title.replace('\n',' ')+'\n'+state)
            self.list.item(i).setToolTip(title+'\n'+state)
        self.body.setCurrentIndex(1 if self.jobs else 0)

    def show_progress(self,message):
        friendly={'한국어 OCR · 사진 영역 분석':'사진과 문구를 읽고 있어요.',
                  'PhotoCraft 템플릿 배치':'썸네일에 사진과 문구를 배치하고 있어요.',
                  '문구·경계·출력 검사':'마지막으로 확인하고 PNG를 저장하고 있어요.'}
        self.status.setText(friendly.get(message,message))

    def _tray(self):
        p=QPixmap(64,64);p.fill(QColor('#f58220'));q=QPainter(p);q.setPen(QPen(QColor('#fff'),5));q.drawRoundedRect(10,16,44,32,7,7);q.end()
        self.setWindowIcon(QIcon(p));self.tray=QSystemTrayIcon(QIcon(p),self);self.tray.setToolTip('썸네일 스튜디오 · Win+Shift+S')
        menu=QMenu();menu.addAction('작업 창 열기',self.showNormal);menu.addAction('화면 캡처',self.begin_capture);menu.addAction('종료',self.quit_app)
        self.tray.setContextMenu(menu);self.tray.activated.connect(lambda r:self.showNormal() if r==QSystemTrayIcon.ActivationReason.DoubleClick else None);self.tray.show()

    def dragEnterEvent(self,e):
        if e.mimeData().hasUrls():e.acceptProposedAction()
    def dropEvent(self,e):
        if self.modes.currentWidget() is self.designer:self.designer.dropEvent(e)
        else:self.add([u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]);e.acceptProposedAction()
    def pick(self):
        files,_=QFileDialog.getOpenFileNames(self,'캡처 파일 선택','','이미지 (*.png *.jpg *.jpeg *.webp *.bmp)');self.add(files)
    def add(self,files):
        for f in files:
            path=Path(f)
            if path.is_file() and path.suffix.lower() in {'.png','.jpg','.jpeg','.webp','.bmp'}:
                self.jobs.append(dict(path=str(path),state='대기',plan=None,report=None))
                item=QListWidgetItem(QIcon(QPixmap(str(path)).scaled(32,52,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)),path.stem+'\n대기')
                item.setSizeHint(QSize(184,74));self.list.addItem(item)
        self.refresh_queue()
        if self.list.currentRow()<0 and self.jobs:self.list.setCurrentRow(0)
        self.next_job()
    def next_job(self):
        if self.worker is not None:return
        for i,j in enumerate(self.jobs):
            if j['state']=='대기':self.start_job(i);return
    def start_job(self,i,plan=None):
        self.active=i;self.jobs[i]['state']='처리 중';self.list.item(i).setText('처리 중 · '+Path(self.jobs[i]['path']).name)
        self.refresh_queue();self.progress.show()
        self.worker=Worker(self.jobs[i]['path'],self.output,plan);self.worker.status.connect(self.show_progress)
        self.worker.planned.connect(self.on_plan);self.worker.finishedJob.connect(self.on_done);self.worker.failed.connect(self.on_error)
        self.worker.finished.connect(self.worker_finished);self.regen.setEnabled(False);self.worker.start()
    def on_plan(self,plan):
        self.jobs[self.active]['plan']=plan
        self.refresh_queue()
        if self.list.currentRow()==self.active:self.select(self.active)
    def on_done(self,report):
        i=self.active;self.jobs[i].update(state='완료',plan=report,report=report)
        label='확인 권장' if report['warnings'] else '완료'
        self.list.item(i).setText(label+' · '+Path(report['output']).name)
        self.status.setText('저장 완료  '+Path(report['output']).name);self.refresh_queue()
        if self.list.currentRow()==i:self.select(i)
    def on_error(self,message):
        self.jobs[self.active]['state']='수정 필요';self.list.item(self.active).setText('수정 필요 · '+Path(self.jobs[self.active]['path']).name)
        self.jobs[self.active]['error']=message;self.status.setText('자동 출력 보류 · '+message)
        self.refresh_queue()
        if self.list.currentRow()==self.active:self.select(self.active)
    def worker_finished(self):
        self.worker.deleteLater();self.worker=None;self.active=None;self.progress.hide()
        i=self.list.currentRow();self.regen.setEnabled(i>=0 and bool(self.jobs[i].get('plan')));QTimer.singleShot(50,self.next_job)
    def select(self,i):
        if not 0<=i<len(self.jobs):return
        j=self.jobs[i];p=j.get('plan') or {};self.original.load(j['path'],p.get('crop'))
        self.form_widget.setEnabled(bool(p));self.regen.setEnabled(bool(p) and self.worker is None)
        self.preview_title.setText('미리보기');self.preview_title.setToolTip(Path(j['path']).name)
        for key,w in self.fields.items():
            if isinstance(w,QTextEdit):w.setPlainText(p.get(key,''))
            else:w.setText(p.get(key,''))
        self.result.image=None;self.result.setText('완성본을 만들고 있어요.\n원본 탭에서 사진을 먼저 확인할 수 있어요.');self.result.update()
        if j.get('report'):self.result.load(j['report']['output']);self.tabs.setCurrentIndex(0)
        else:self.tabs.setCurrentIndex(1)
        messages=list(p.get('warnings',[]))+list(p.get('notices',[]))
        if p.get('copy_repaired'):messages.append('끊기거나 짧은 자막을 주제별 문구로 보완했습니다.')
        if j.get('error'):messages.append(j['error'])
        self.notes.setText('\n'.join(messages) if messages else ('완성됐어요. 제목과 출처를 한 번 확인해 주세요.' if j.get('report') else '사진과 문구를 분석하고 있어요.'))
        self.notes.setProperty('attention',bool(p.get('warnings') or j.get('error')))
        self.notes.style().unpolish(self.notes);self.notes.style().polish(self.notes)
    def crop_changed(self,crop):
        i=self.list.currentRow()
        if i>=0 and self.jobs[i].get('plan'):self.jobs[i]['plan']['crop']=crop
    def regenerate(self):
        if self.worker:return
        i=self.list.currentRow()
        if i<0 or not self.jobs[i].get('plan'):return
        p=deepcopy(self.jobs[i]['plan'])
        for key,w in self.fields.items():p[key]=w.toPlainText().strip() if isinstance(w,QTextEdit) else w.text().strip()
        self.jobs[i].pop('error',None);self.start_job(i,p)
    def change_output(self):
        p=QFileDialog.getExistingDirectory(self,'완성본 저장 위치',str(self.output))
        if p:
            self.output=Path(p);self.settings['output']=p;self.settings_path.write_text(json.dumps(self.settings,ensure_ascii=False),encoding='utf-8');self.path_label.setText('저장 위치: '+p)
    def open_output(self):
        self.output.mkdir(parents=True,exist_ok=True);QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.output)))
    def begin_capture(self):
        if self.overlay.isVisible() or self.capture_pending:return
        self.capture_pending=True
        self.hide();QTimer.singleShot(200,self.take_snapshot)
    def take_snapshot(self):
        from custom_capture.capture import grab_desktop_snapshot
        self.snapshot=grab_desktop_snapshot()
        if self.snapshot is None:self.capture_pending=False;self.showNormal();self.status.setText('화면 캡처에 실패했습니다. 다시 시도해 주세요.');return
        self.overlay.begin(self.snapshot)
    def capture_done(self,rect):
        from custom_capture.capture import save_region_from_snapshot
        from custom_capture.clipboard import copy_image_to_clipboard
        try:
            path,image=save_region_from_snapshot(self.snapshot,rect,ROOT/'캡처')
            try:copy_image_to_clipboard(image)
            except Exception:pass
            self.showNormal()
            if self.modes.currentWidget() is self.designer:self.designer.set_photo(str(path))
            elif self.auto_capture.isChecked():self.add([str(path)])
            else:self.status.setText('캡처 저장 완료 · '+str(path))
        except Exception as e:self.showNormal();self.status.setText(str(e))
        finally:self.snapshot=None;self.capture_pending=False
    def capture_cancelled(self):self.snapshot=None;self.capture_pending=False;self.showNormal()
    def startup_file(self):return Path(os.environ['APPDATA'])/'Microsoft/Windows/Start Menu/Programs/Startup/SmartLifeThumbnail.vbs'
    def toggle_startup(self,on):
        p=self.startup_file()
        if on:
            exe=ROOT/'ThumbnailStudio.exe'
            if not exe.exists():self.startup.blockSignals(True);self.startup.setChecked(False);self.startup.blockSignals(False);return
            command='"'+str(exe)+'" --tray'
            p.write_text('Set sh = CreateObject("WScript.Shell")\nsh.Run "'+command.replace('"','""')+'", 0, False\n',encoding='utf-16')
        else:p.unlink(missing_ok=True)
    def closeEvent(self,e):
        if self.worker or self.designer.worker:
            self.hide();e.ignore();self.tray.showMessage('썸네일 스튜디오','작업은 계속됩니다. 트레이에서 창을 다시 열 수 있어요.');return
        self.hide();e.ignore()
    def quit_app(self):
        if self.worker or self.designer.worker:
            QMessageBox.information(self,'처리 중','현재 파일 처리가 끝난 뒤 종료해 주세요.');return
        if self.hook:self.hook.stop()
        self.tray.hide();QApplication.instance().quit()


STYLE='''
QMainWindow {background:#f0f3f7;}
QWidget {color:#172b43;font-family:"SUIT";font-size:14px;}
QLabel {background:transparent;}
QPushButton {background:#fff;border:1px solid #cbd4df;border-radius:7px;padding:10px 14px;font-weight:600;min-height:20px;}
QPushButton:hover {background:#f2f5f9;border-color:#8295ab;}
QPushButton:pressed {background:#dce4ed;}
QPushButton:focus,QLineEdit:focus,QTextEdit:focus {border:2px solid #42698e;}
QPushButton:disabled {background:#edf0f4;color:#8995a4;border-color:#e0e5eb;}
QPushButton#importButton {background:#f58220;color:#142b46;border:1px solid #f58220;font-weight:700;}
QPushButton#importButton:hover {background:#ff963d;border-color:#ff963d;}
QPushButton#regenerate {background:#193c61;color:#fff;border:1px solid #193c61;font-size:13px;}
QPushButton#regenerate:hover {background:#28537c;}
QPushButton#regenerate:disabled {background:#e6ebf0;color:#8491a0;border-color:#e6ebf0;}
QFrame#rail {background:#142b46;}
QFrame#rail QLabel {color:#dae5f0;}
QFrame#rail QLabel#brand {font-size:23px;font-weight:700;color:#fff;}
QFrame#rail QLabel#railSubtitle {font-size:15px;color:#bacbde;}
QFrame#rail QLabel#railHint {font-size:12px;color:#b4c5d9;}
QFrame#rail QLabel#queueTitle {font-weight:600;}
QPushButton#captureButton {background:#25415f;color:#fff;border:1px solid #49617b;}
QPushButton#captureButton:hover {background:#355676;}
QPushButton#railSettings {background:transparent;color:#d7e4f2;border:1px solid #49617b;font-size:12px;}
QPushButton#railSettings:hover {background:#25415f;}
QListWidget#queue {background:transparent;border:0;color:#dde8f3;outline:0;}
QListWidget#queue::item {border:1px solid transparent;border-radius:7px;padding:8px;font-size:12px;}
QListWidget#queue::item:selected {background:#2d4b6b;border-color:#67809b;color:#fff;}
QListWidget#queue::item:hover {background:#243f5d;}
QListWidget#queue:focus {border:1px solid #8299b3;border-radius:7px;}
QFrame#rail QCheckBox {color:#e0e9f4;font-size:12px;padding:4px 0;}
QLabel#pageTitle {font-size:24px;font-weight:700;}
QLabel#sectionTitle {font-size:17px;font-weight:700;}
QLabel#muted,QLabel#savePath {color:#607084;font-size:12px;}
QLabel#savePath {font-size:11px;}
QLabel#status {font-size:13px;color:#294561;}
QFrame#dropZone {background:#fff;border:1px dashed #9eafc2;border-radius:12px;}
QLabel#dropMark {font-size:54px;font-weight:400;color:#f58220;}
QLabel#emptyTitle {font-size:25px;font-weight:700;}
QLabel#emptyHint {font-size:15px;color:#607084;}
QFrame#editor {background:#fff;border:1px solid #dce3eb;border-radius:10px;}
QScrollArea,QScrollArea>QWidget>QWidget {background:transparent;border:0;}
QLabel#fieldLabel {font-size:12px;font-weight:600;color:#485c73;}
QLineEdit,QTextEdit {background:#f8fafc;border:1px solid #cbd4df;border-radius:6px;padding:8px;selection-background-color:#c9dff4;selection-color:#142b46;}
QLineEdit#emphasisField {color:#a54b09;}
QLineEdit:disabled,QTextEdit:disabled {color:#92a0af;background:#f2f4f7;}
QLabel#notice {font-size:12px;color:#466079;background:#eef3f8;border-radius:6px;padding:10px;}
QLabel#notice[attention="true"] {color:#79511a;background:#fff2dc;}
QTabWidget::pane {background:#e7ecf2;border:1px solid #d5dee8;top:0;}
QTabBar::tab {background:transparent;color:#607084;padding:11px 16px;border-bottom:3px solid transparent;font-weight:600;}
QTabBar::tab:selected {color:#173c62;border-bottom:3px solid #173c62;}
QTabBar::tab:hover {background:#e4eaf2;}
QTabBar::tab:focus {outline:1px solid #42698e;}
QProgressBar {background:#e0e7ef;border:0;}
QProgressBar::chunk {background:#f58220;}
QScrollBar:vertical {background:transparent;width:7px;margin:0;}
QScrollBar::handle:vertical {background:#adbbc9;border-radius:3px;min-height:24px;}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {height:0;}
QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical {background:transparent;}
QToolTip {background:#142b46;color:#fff;border:0;padding:6px;}
'''
