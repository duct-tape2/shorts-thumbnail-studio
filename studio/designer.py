"""General thumbnail designer UI; no company assets or external service required."""
from pathlib import Path
from PySide6.QtCore import Signal,QThread,Qt,QUrl
from PySide6.QtGui import QPixmap,QDesktopServices
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QTextEdit,QLineEdit,
    QPushButton,QComboBox,QFileDialog,QFrame,QScrollArea,QProgressBar)
from .design import make_plan,PRESETS
from .design_render import render_design
from .paths import OUTPUT

class DesignWorker(QThread):
    done=Signal(dict);failed=Signal(str);status=Signal(str)
    def __init__(self,plan,output):super().__init__();self.plan=plan;self.output=output
    def run(self):
        try:self.done.emit(render_design(self.plan,self.output,self.status.emit))
        except Exception as e:self.failed.emit(str(e))

class DesignPanel(QWidget):
    captureRequested=Signal()
    outputRequested=Signal()
    def __init__(self,preview_class,output):
        super().__init__();self.output=output;self.worker=None;self.photo='';self.report=None;self.setAcceptDrops(True)
        root=QHBoxLayout(self);root.setContentsMargins(28,24,28,24);root.setSpacing(24)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.Shape.NoFrame);scroll.setFixedWidth(382)
        controls=QWidget();form=QVBoxLayout(controls);form.setContentsMargins(0,0,14,0);form.setSpacing(9)
        title=QLabel('설명으로 만드는 썸네일');title.setObjectName('pageTitle');form.addWidget(title)
        hint=QLabel('스타일과 문구를 정하고 미리보기를 확인하세요.');hint.setObjectName('muted');form.addWidget(hint);form.addSpacing(12)
        def field(label,widget):form.addWidget(QLabel(label));form.addWidget(widget);return widget
        self.title=field('큰 제목',QLineEdit());self.title.setPlaceholderText('예: 혼자 떠나는 주말 여행')
        self.brief=field('원하는 디자인',QTextEdit());self.brief.setFixedHeight(106)
        self.brief.setPlaceholderText('예: 어두운 배경, 노란 포인트, 강렬한 느낌. 제목은 가운데 정렬로 아래에.')
        self.subtitle=field('보조 문구 (선택)',QLineEdit());self.subtitle.setPlaceholderText('예: 가볍게 챙겨 떠나세요')
        self.emphasis=field('강조할 말 (선택)',QLineEdit());self.emphasis.setPlaceholderText('제목에 있는 말 한 곳')
        self.source=field('출처 / 채널명 (선택)',QLineEdit())
        self.style=QComboBox();self.style.addItem('설명에서 선택','auto')
        for key,preset in PRESETS.items():self.style.addItem(preset['name'],key)
        field('스타일',self.style)
        self.format=QComboBox()
        for text,key in [('쇼츠  1080 × 1920','shorts'),('정사각형  1080 × 1080','square'),('가로  1280 × 720','landscape')]:self.format.addItem(text,key)
        field('출력 크기',self.format)
        photo_row=QHBoxLayout();self.photo_button=QPushButton('사진 추가');self.photo_button.clicked.connect(self.pick_photo);photo_row.addWidget(self.photo_button)
        remove=QPushButton('사진 빼기');remove.clicked.connect(self.clear_photo);photo_row.addWidget(remove);form.addLayout(photo_row)
        capture=QPushButton('화면에서 사진 캡처');capture.clicked.connect(self.captureRequested.emit);form.addWidget(capture)
        self.photo_label=QLabel('사진은 이 창에 끌어다 놓아도 됩니다.');self.photo_label.setObjectName('muted');self.photo_label.setWordWrap(True);form.addWidget(self.photo_label)
        note=QLabel('오프라인 기본 모드는 준비된 스타일을 조합합니다.\n새로운 사진이나 일러스트를 생성하지는 않습니다.');note.setObjectName('notice');note.setWordWrap(True);form.addWidget(note)
        form.addStretch()
        scroll.setWidget(controls)
        left=QVBoxLayout();left.addWidget(scroll,1)
        self.create=QPushButton('썸네일 만들기');self.create.setObjectName('importButton');self.create.clicked.connect(self.generate);left.addWidget(self.create)
        root.addLayout(left)
        right=QVBoxLayout();right.setSpacing(12);root.addLayout(right,1)
        heading=QHBoxLayout();l=QLabel('미리보기');l.setObjectName('sectionTitle');heading.addWidget(l);heading.addStretch()
        self.open_button=QPushButton('저장 폴더 열기');self.open_button.clicked.connect(self.open_output);heading.addWidget(self.open_button)
        change=QPushButton('저장 위치');change.clicked.connect(self.outputRequested.emit);heading.addWidget(change);right.addLayout(heading)
        self.preview=preview_class();self.preview.setText('제목과 원하는 디자인을 입력해 주세요.');right.addWidget(self.preview,1)
        self.progress=QProgressBar();self.progress.setRange(0,0);self.progress.setFixedHeight(3);self.progress.setTextVisible(False);self.progress.hide();right.addWidget(self.progress)
        self.status=QLabel('완성 PNG는 날짜별 폴더에 자동 저장됩니다.');self.status.setWordWrap(True);right.addWidget(self.status)
        self.description=QLabel('');self.description.setWordWrap(True);self.description.setObjectName('muted');right.addWidget(self.description)
    def pick_photo(self):
        path,_=QFileDialog.getOpenFileName(self,'사진 선택','','이미지 (*.png *.jpg *.jpeg *.webp *.bmp)')
        if path:self.set_photo(path)
    def set_photo(self,path):self.photo=path;self.photo_label.setText(Path(path).name);self.photo_label.setToolTip(path)
    def clear_photo(self):self.photo='';self.photo_label.setText('사진 없이 텍스트 중심으로 만듭니다.')
    def dragEnterEvent(self,event):
        if event.mimeData().hasUrls():event.acceptProposedAction()
    def dropEvent(self,event):
        for url in event.mimeData().urls():
            path=Path(url.toLocalFile())
            if path.is_file() and path.suffix.lower() in {'.png','.jpg','.jpeg','.webp','.bmp'}:self.set_photo(str(path));break
        event.acceptProposedAction()
    def generate(self):
        if self.worker:return
        try:
            plan=make_plan(self.title.text(),self.brief.toPlainText(),self.subtitle.text(),self.emphasis.text(),self.source.text(),self.photo,self.style.currentData(),self.format.currentData())
        except ValueError as e:self.status.setText(str(e));return
        self.description.setText(plan['summary']);self.create.setEnabled(False);self.progress.show()
        self.worker=DesignWorker(plan,self.output());self.worker.status.connect(self.status.setText);self.worker.done.connect(self.finished);self.worker.failed.connect(lambda error:self.status.setText('만들지 못했어요. '+error));self.worker.finished.connect(self.cleanup);self.worker.start()
    def finished(self,report):
        self.report=report;self.preview.load(report['output']);self.status.setText('저장 완료  '+Path(report['output']).name)
        self.description.setText(report['summary']+'\n'+'\n'.join(report.get('warnings',[])))
    def cleanup(self):self.worker.deleteLater();self.worker=None;self.create.setEnabled(True);self.progress.hide()
    def open_output(self):
        folder=Path(self.report['output']).parent if self.report else Path(self.output());folder.mkdir(parents=True,exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
