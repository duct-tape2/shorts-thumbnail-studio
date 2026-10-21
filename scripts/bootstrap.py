"""Developer-only dependency download. Portable releases do not call this."""
from pathlib import Path
import hashlib
import shutil
import tempfile
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[1]
FILES={
 'det.onnx':('https://raw.githubusercontent.com/403323726/PP-OCRv5/master/det/ch_PP-OCRv5_det_mobile.onnx','4d97c44a20d30a81aad087d6a396b08f786c4635742afc391f6621f5c6ae78ae'),
 'korean-rec.onnx':('https://raw.githubusercontent.com/403323726/PP-OCRv5/master/rec/korean_PP-OCRv5_rec_mobile.onnx','cd6e2ea50f6943ca7271eb8c56a877a5a90720b7047fe9c41a2e541a25773c9b'),
}
def download(url,target,expected):
    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()==expected:return
    target.parent.mkdir(parents=True,exist_ok=True)
    temp=target.with_suffix(target.suffix+'.download')
    urllib.request.urlretrieve(url,temp)
    if hashlib.sha256(temp.read_bytes()).hexdigest()!=expected:temp.unlink();raise RuntimeError('Checksum mismatch: '+target.name)
    temp.replace(target)

for name,(url,digest) in FILES.items():download(url,ROOT/'assets/models'/name,digest)
import rapidocr
model=next((Path(rapidocr.__file__).parent/'models').glob('*cls*.onnx'))
if hashlib.sha256(model.read_bytes()).hexdigest()!='e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c':raise RuntimeError('Unexpected RapidOCR classifier version')
shutil.copy2(model,ROOT/'assets/models/cls.onnx')
with tempfile.TemporaryDirectory() as temporary:
    archive=Path(temporary)/'photocraft.zip'
    download('https://github.com/storytold/photocraft/releases/download/v0.11.1/photocraft-0.11.1-windows-x64-portable.zip',archive,'00570cb1a2da18a5677b28296f6cefae46dfad3011f51b8369146dcc73a2777a')
    extracted=Path(temporary)/'extracted';extracted.mkdir()
    with zipfile.ZipFile(archive) as z:
        for member in z.infolist():
            target=(extracted/member.filename).resolve()
            if not target.is_relative_to(extracted.resolve()):raise RuntimeError('Unsafe archive entry')
        z.extractall(extracted)
    cli=next(extracted.rglob('photocraft-cli.exe'))
    shutil.copytree(cli.parent,ROOT/'vendor/photocraft',dirs_exist_ok=True)
if not (ROOT/'assets/fonts/NotoSansCJKkr-Black.otf').exists():raise RuntimeError('Use the full Source.zip release: bundled open fonts are required.')
print('Developer dependencies ready. Run python main.py.')
