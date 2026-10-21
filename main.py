import argparse
import json
import os
import sys
from pathlib import Path


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('files',nargs='*')
    parser.add_argument('--no-hotkey',action='store_true')
    parser.add_argument('--tray',action='store_true')
    parser.add_argument('--process',action='store_true',help='Process inputs without a window')
    parser.add_argument('--plan',help='Render an existing JSON plan')
    parser.add_argument('--output')
    parser.add_argument('--report')
    parser.add_argument('--self-check',action='store_true')
    parser.add_argument('--design',help='Render a design JSON without company assets')
    args=parser.parse_args()
    from studio.paths import ensure_dirs,setup_fonts,ROOT
    ensure_dirs();setup_fonts()
    if args.self_check:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import QTimer
        from studio.ui import Window,STYLE
        app=QApplication([])
        app.setStyleSheet(STYLE)
        probe=Window(no_hotkey=True);probe.show()
        QTimer.singleShot(100,app.quit)
        app.exec()
        screenshot=probe.grab()
        if screenshot.isNull():raise RuntimeError('작업 창 렌더링 검사 실패')
        if args.report:screenshot.save(str(Path(args.report).with_suffix('.png')))
        probe.tray.hide();probe.close()
        from studio.ocr import OCR
        from studio.render import PhotoCraft
        from studio.paths import DATA
        OCR();pc=PhotoCraft(ROOT)
        try:
            if (ROOT/'assets/template.psd').exists():pc.rpc('doc.open',path=str(ROOT/'assets/template.psd'))
            else:
                pc.rpc('doc.new',width=1080,height=1920,background='#142B46')
                pc.run('type.create',x=80,y=80,text='시작 검사',font='Noto Sans CJK KR',fontStyle='Black',weight=900,size=80,color='#ffffff')
                pc.run('type.create',x=80,y=220,text='글꼴 확인',font='SUIT',fontStyle='SemiBold',weight=600,size=45,color='#ffffff')
            missing=pc.run('type.resolveMissingFonts')
            if missing.get('missing'):raise RuntimeError('필수 폰트 누락: '+str(missing))
            result=dict(ok=True,photocraft=True,ocr=True,fonts=True,qt_widgets=True)
        finally:pc.close()
        if args.report:Path(args.report).write_text(json.dumps(result),encoding='utf-8')
        return 0
    if args.design:
        from studio.design_render import render_design
        result=render_design(json.loads(Path(args.design).read_text(encoding='utf-8')),args.output)
        if args.report:Path(args.report).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        return 0
    if args.process or args.plan:
        from studio.ocr import OCR,analyze
        from studio.render import render
        results=[]
        if args.plan:
            plans=[json.loads(Path(args.plan).read_text(encoding='utf-8'))]
        else:
            ocr=OCR();plans=[analyze(f,ocr) for f in args.files]
        for p in plans:results.append(render(p,args.output))
        if args.report:Path(args.report).write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
        return 0
    from custom_capture.dpi import enable_dpi_awareness
    enable_dpi_awareness()
    import ctypes
    kernel=ctypes.windll.kernel32
    kernel.CreateMutexW.argtypes=[ctypes.c_void_p,ctypes.c_bool,ctypes.c_wchar_p]
    kernel.CreateMutexW.restype=ctypes.c_void_p
    mutex=kernel.CreateMutexW(None,False,'Local\\SmartLifeThumbnailStudio')
    if kernel.GetLastError()==183:
        ctypes.windll.user32.MessageBoxW(None,'이미 실행 중입니다. 작업 표시줄의 트레이 아이콘에서 창을 열어 주세요.','썸네일 스튜디오',64)
        return 0
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QTimer
    from studio.ui import Window,STYLE
    app=QApplication([sys.argv[0]]);app.setApplicationName('ThumbnailStudio');app.setQuitOnLastWindowClosed(False);app.setStyleSheet(STYLE)
    window=Window(args.no_hotkey)
    if not args.tray:window.show()
    if args.files:QTimer.singleShot(100,lambda:window.add(args.files))
    return app.exec()


if __name__=='__main__':
    try:sys.exit(main())
    except Exception:
        import traceback
        error=traceback.format_exc()
        from studio.paths import DATA
        DATA.mkdir(parents=True,exist_ok=True);(DATA/'startup-error.log').write_text(error,encoding='utf-8')
        if sys.stderr:print(error,file=sys.stderr)
        diagnostic=any(arg in {'--self-check','--process','--plan','--design'} or arg.startswith(('--plan=','--design=')) for arg in sys.argv[1:])
        if getattr(sys,'frozen',False) and not diagnostic:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,'실행에 실패했습니다. data/startup-error.log를 확인해 주세요.\n'+error[-1000:],'썸네일 스튜디오',16)
        sys.exit(1)
