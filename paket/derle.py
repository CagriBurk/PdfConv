"""Masaüstü paketini üretir: `build/PdfAtolyesi-<sürüm>/` ve `build/PdfAtolyesi-<sürüm>.zip`.

    uv run python paket/derle.py                # motorlar bu bilgisayardaki kurulumdan
    uv run python paket/derle.py --motorsuz     # Tesseract/Ghostscript'siz (CI)

İçerik (kullanıcıda uv, Node, git gerekmez):
- python/        python.org'un İMZALI gömülü (embeddable) Python'u + Lib/site-packages
                 (kilit dosyasındaki çalışma bağımlılıkları + pdfatolye; arayüz paketin içinde)
- motorlar/      tesseract/ (yalnızca gereken DLL'ler + tur, eng, osd), ghostscript/
- simgeler/      uygulama simgesi
- Kur.cmd, Kaldir.cmd, pdfe-cevir.cmd, OKUBENI.txt, LISANSLAR.txt, LICENSE.txt (AGPL-3.0),
  pdfatolye-kurulum.json

Neden PyInstaller / Inno Setup değil: bkz. PLAN.md tuzak #52 (Akıllı Uygulama Denetimi).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tomllib
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "paket"))
from pe_bagimlilik import local_closure  # noqa: E402

PY_VERSION = "3.11.9"
PY_URL = f"https://www.python.org/ftp/python/{PY_VERSION}/python-{PY_VERSION}-embed-amd64.zip"
# Bütünlük: HTTPS + içindeki python.exe/pythonw.exe'nin PSF Authenticode imzası (check_signature).
TESSERACT = Path(r"C:\Program Files\Tesseract-OCR")
GS_GLOB = r"C:\Program Files\gs\gs*"
OCR_LANGS = ("tur", "eng", "osd")

KUR_CMD = """@echo off
chcp 65001 >nul
rem PDF Atolyesi kurulumu: imzali Python ile kurar (yonetici izni gerekmez).
"%~dp0python\\python.exe" -I -m pdfatolye.kurulum kur %*
"""
KALDIR_CMD = """@echo off
chcp 65001 >nul
"%~dp0python\\python.exe" -I -m pdfatolye.kurulum kaldir
"""
PDFE_CEVIR_CMD = """@echo off
chcp 65001 >nul
rem Sag tik > Gonder > "PDF'e cevir": dosyalari turune gore PDF'e cevirir.
"%~dp0python\\python.exe" -I -m pdfatolye gonder %*
if errorlevel 1 pause
"""
OKUBENI = """PDF Atölyesi {version} — kurulum
=================================

1. Bu klasördeki "Kur" (Kur.cmd) dosyasına çift tıkla.
   Windows "Bilinmeyen yayımcı" ya da "Windows bilgisayarınızı korudu" derse:
   "Daha fazla bilgi" → "Yine de çalıştır" (dosya imzalı değil, ama içinde çalışan Python
   python.org imzalıdır). Yönetici izni istemez.
2. Kurulum bitince uygulama açılır; sonra masaüstündeki "PDF Atölyesi" simgesini kullan.
3. Bu klasörü (ve indirdiğin zip'i) silebilirsin.

Kaldırmak: Ayarlar → Uygulamalar → "PDF Atölyesi" → Kaldır (belgelerin silinsin mi diye sorar).
Güncellemek: yeni sürümün paketinde yine "Kur"a çift tıkla; belgelerin ve ayarların korunur.

Word / Excel / PowerPoint → PDF için LibreOffice gerekir; uygulamanın Ayarlar sayfasındaki
"LibreOffice'i kur" düğmesi kurar (ya da: winget install TheDocumentFoundation.LibreOffice).
Dosyaların bilgisayarından çıkmaz; uygulama internete bağlanmaz (yalnızca sen "Güncellemeleri
denetle" dersen GitHub'a sorar).
"""
LISANSLAR = """PDF Atölyesi paketindeki bileşenler ve lisansları
=================================================

- PDF Atölyesi: GNU AGPL v3 (LICENSE.txt), kaynak kod: https://github.com/CagriBurk/PdfConv
- Python {py} (python.org, imzalı gömülü dağıtım): PSF License
- PyMuPDF / MuPDF: GNU AGPL v3 (ticari lisans ayrıca Artifex'ten)
- pikepdf / qpdf: MPL 2.0 / Apache 2.0
- OCRmyPDF: MPL 2.0
- Tesseract OCR (UB Mannheim derlemesi) ve tessdata_fast dil dosyaları: Apache 2.0
- Ghostscript (Artifex): GNU AGPL v3
- Playwright (Microsoft): Apache 2.0 — tarayıcı indirilmez, kurulu Edge kullanılır
- Noto Sans / Serif / Sans Mono (Google, Noto Project): SIL Open Font License 1.1
- KaTeX: MIT; pdf.js: Apache 2.0; React: MIT; Konva: MIT; dnd-kit: MIT
- Diğer Python kütüphaneleri: python/Lib/site-packages altında her birinin *.dist-info/
  klasöründeki LICENSE dosyaları

PDF Atölyesi ve AGPL bileşenleri (PyMuPDF, Ghostscript) nedeniyle bu paketi başkasına
verirken kaynak kod erişilebilir olmalıdır: https://github.com/CagriBurk/PdfConv
"""


def log(msg: str) -> None:
    print(msg, flush=True)


class StepFailed(Exception):
    pass


def run(args: list, **kw) -> None:
    """Komutu çalıştırır; başarısızsa çıktısının sonunu hatayla birlikte verir (CI günlüğü
    kimliksiz okunamıyor: hata `::error::` annotation'ı olarak da yazılır)."""
    log("  $ " + " ".join(map(str, args)))
    r = subprocess.run([str(a) for a in args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", **kw)
    out = (r.stdout or "") + (r.stderr or "")
    if r.returncode != 0:
        tail = "\n".join(out.strip().splitlines()[-25:])
        raise StepFailed(f"Komut başarısız (çıkış {r.returncode}): {Path(str(args[0])).name} "
                         f"{' '.join(map(str, args[1:4]))}...\n{tail}")
    if out.strip():
        log("\n".join("    " + ln for ln in out.strip().splitlines()[-5:]))


def ci_error(message: str) -> None:
    """GitHub Actions'ta hatayı annotation olarak yaz (API'den kimliksiz okunur)."""
    import os

    if os.environ.get("GITHUB_ACTIONS"):
        esc = message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print(f"::error title=Paket derlenemedi::{esc}", flush=True)


def project_version() -> str:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"]


def fetch_python(cache: Path) -> Path:
    zip_path = cache / Path(PY_URL).name
    if not zip_path.is_file():
        log(f"İndiriliyor: {PY_URL}")
        cache.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(PY_URL, timeout=120) as resp:
            zip_path.write_bytes(resp.read())
    log(f"  sha256 {hashlib.sha256(zip_path.read_bytes()).hexdigest()}")
    return zip_path


def check_signature(exe: Path) -> None:
    """python.exe python.org (PSF) imzalı mı? Akıllı Uygulama Denetimi buna güvenir."""
    import os

    # pwsh (PowerShell 7) içinden çağrılınca devralınan PSModulePath, Windows PowerShell 5.1'in
    # güvenlik modülünü yükletmiyor (CI): temizlenir.
    env = {k: v for k, v in os.environ.items() if k.upper() != "PSMODULEPATH"}
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         f"$s = Get-AuthenticodeSignature '{exe}'; "
         "\"$($s.Status)|$($s.SignerCertificate.Subject)\""],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    out = r.stdout.strip()
    status, _, subject = out.partition("|")
    if status != "Valid" or "Python Software Foundation" not in subject:
        raise SystemExit(f"{exe.name} imzası geçersiz: {out} {r.stderr.strip()[-500:]}")
    log(f"  imza: {status} ({subject.split(',')[0]})")


def build_python(dest: Path, cache: Path) -> Path:
    py = dest / "python"
    with zipfile.ZipFile(fetch_python(cache)) as zf:
        zf.extractall(py)
    check_signature(py / "python.exe")
    check_signature(py / "pythonw.exe")
    # ._pth: site-packages yolu + `import site` (.pth dosyaları işlensin). -I ile çalıştırılır:
    # kullanıcının PYTHONPATH'i ve kullanıcı site klasörü karışmaz.
    pth = next(py.glob("python*._pth"))
    pth.write_text("python311.zip\n.\nLib\\site-packages\nimport site\n", encoding="utf-8")
    return py / "Lib" / "site-packages"


def _requirement_names(req: Path) -> set[str]:
    import re

    from packaging.markers import Marker

    names = set()
    for line in req.read_text(encoding="utf-8").splitlines():
        spec, _, marker = line.strip().partition(";")
        m = re.match(r"^([A-Za-z0-9_.-]+)==", spec.strip())
        # İşaretçiler bu yorumlayıcıya göre (Windows, CPython 3.11) değerlendirilir.
        if m and (not marker.strip() or Marker(marker.strip()).evaluate()):
            names.add(re.sub(r"[-_.]+", "-", m.group(1)).lower())
    return names


def copy_from_venv(site: Path, req: Path) -> None:
    """Ağ yavaşken: kilit dosyasıyla eşitlenmiş yerel .venv'den yalnızca çalışma paketlerini
    (kilitteki sürümler) RECORD dosyalarına göre kopyalar. Geliştirme araçları ve düzenlenebilir
    pdfatolye kurulumu alınmaz."""
    import re
    from importlib.metadata import distributions

    venv_site = ROOT / ".venv" / "Lib" / "site-packages"
    wanted = _requirement_names(req)
    found = set()
    for dist in distributions(path=[str(venv_site)]):
        name = re.sub(r"[-_.]+", "-", dist.metadata["Name"]).lower()
        if name not in wanted:
            continue
        found.add(name)
        for f in dist.files or []:
            src = Path(dist.locate_file(f)).resolve()
            if not src.is_file() or not src.is_relative_to(venv_site.resolve()):
                continue  # Scripts\*.exe gibi site-packages dışındakiler
            dest = site / src.relative_to(venv_site.resolve())
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
    missing = wanted - found
    if missing:
        raise SystemExit(f".venv'de olmayan çalışma paketleri: {sorted(missing)} (uv sync)")
    log(f"  .venv'den {len(found)} paket kopyalandı")


def install_packages(site: Path, work: Path, *, from_venv: bool = False) -> None:
    site.mkdir(parents=True, exist_ok=True)
    req = work / "gereksinimler.txt"
    run(["uv", "export", "--frozen", "--no-dev", "--no-hashes", "--no-emit-project",
         "--format", "requirements-txt", "-o", req], cwd=ROOT)
    target = ["--target", site, "--python-version", "3.11",
              "--python-platform", "x86_64-pc-windows-msvc", "--only-binary", ":all:"]
    if from_venv:
        copy_from_venv(site, req)
    else:
        run(["uv", "pip", "install", "--quiet", *target, "-r", req], cwd=ROOT)
    wheel_dir = work / "teker"
    run(["uv", "build", "--wheel", "--out-dir", wheel_dir], cwd=ROOT)
    wheel = next(wheel_dir.glob("pdfatolye-*.whl"))
    run(["uv", "pip", "install", "--quiet", "--no-deps", *target, wheel], cwd=ROOT)
    # Derlenmiş arayüz paketin içine: kullanıcıda Node gerekmez (paths.web_dist).
    dist = ROOT / "web" / "dist"
    if not (dist / "index.html").is_file():
        raise SystemExit("Arayüz derlenmemiş: npm --prefix web run build")
    shutil.copytree(dist, site / "pdfatolye" / "web")
    # Paket içinde çalıştırılabilir başlatıcılar gereksiz (SAC engeller, kullanılmaz).
    shutil.rmtree(site / "bin", ignore_errors=True)
    for cache_dir in site.rglob("__pycache__"):
        shutil.rmtree(cache_dir, ignore_errors=True)


def copy_tesseract(dest: Path) -> None:
    exe = TESSERACT / "tesseract.exe"
    if not exe.is_file():
        raise SystemExit(f"Tesseract yok: {exe} (ya da --motorsuz)")
    out = dest / "tesseract"
    (out / "tessdata").mkdir(parents=True)
    shutil.copyfile(exe, out / exe.name)
    for dll in local_closure(exe):
        shutil.copyfile(dll, out / dll.name)
    for lang in OCR_LANGS:
        src = TESSERACT / "tessdata" / f"{lang}.traineddata"
        if not src.is_file():
            raise SystemExit(f"Dil dosyası yok: {src}")
        shutil.copyfile(src, out / "tessdata" / src.name)
    for sub in ("configs", "tessconfigs"):
        if (TESSERACT / "tessdata" / sub).is_dir():
            shutil.copytree(TESSERACT / "tessdata" / sub, out / "tessdata" / sub)


def copy_ghostscript(dest: Path) -> None:
    import glob

    found = sorted(glob.glob(GS_GLOB), reverse=True)
    if not found:
        raise SystemExit("Ghostscript yok (ya da --motorsuz)")
    gs = Path(found[0])
    out = dest / "ghostscript"
    (out / "bin").mkdir(parents=True)
    for name in ("gswin64c.exe", "gsdll64.dll"):
        shutil.copyfile(gs / "bin" / name, out / "bin" / name)
    for sub in ("lib", "Resource", "iccprofiles"):
        if (gs / sub).is_dir():
            shutil.copytree(gs / sub, out / sub)
    lic = gs / "doc" / "COPYING"
    if lic.is_file():
        shutil.copyfile(lic, out / "COPYING")


def make_icon(dest: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    dest.mkdir(parents=True, exist_ok=True)
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((8, 8, size - 8, size - 8), radius=48, fill=(194, 65, 12, 255))
    d.rounded_rectangle((8, 8, size - 8, 120), radius=48, fill=(234, 88, 12, 255))
    d.rectangle((8, 80, size - 8, 120), fill=(234, 88, 12, 255))
    font = ImageFont.truetype(str(ROOT / "src/pdfatolye/assets/fonts/NotoSans-Bold.ttf"), 92)
    d.text((size / 2, size / 2 + 6), "PDF", font=font, fill="white", anchor="mm")
    img.save(dest / "pdfatolye.ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])


def smoke_test(pkg: Path) -> None:
    """Paketin kendi Python'uyla: bütün bağımlılıklar yükleniyor mu, motorlar bulunuyor mu?"""
    py = pkg / "python" / "python.exe"
    code = ("import pymupdf, pikepdf, PIL, ocrmypdf, playwright, fastapi, uvicorn, pdfatolye;"
            "from pdfatolye import paths, engines, settings;"
            "assert paths.install_root() is not None, 'kurulum kökü bulunamadı';"
            "assert (paths.web_dist() / 'index.html').is_file(), 'arayüz yok';"
            "assert (paths.fonts_dir() / 'NotoSans-Regular.ttf').is_file();"
            "print('sürüm', pdfatolye.__version__, 'arayüz', paths.web_dist());"
            "[print(' ', e.name, e.ok, e.path) for e in engines.detect_all(settings.Settings())]")
    run([py, "-I", "-c", code])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--motorsuz", action="store_true", help="Tesseract/Ghostscript ekleme")
    ap.add_argument("--zip", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--yerel-ortam", action="store_true",
                    help="Bağımlılıkları ağdan değil kilitle eşit .venv'den al (yavaş ağ)")
    args = ap.parse_args()

    version = project_version()
    build = ROOT / "build"
    name = f"PdfAtolyesi-{version}"
    out = build / name
    pkg = out  # Kur.cmd paketin kökünde: python\ ve motorlar\ yanında
    shutil.rmtree(out, ignore_errors=True)
    work = build / "is"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    log(f"PDF Atölyesi {version} paketi → {out}")

    log("1/5 Python (python.org, imzalı)")
    site = build_python(pkg, build / "onbellek")
    log("2/5 Python paketleri ve arayüz")
    install_packages(site, work, from_venv=args.yerel_ortam)
    log("3/5 Motorlar")
    engines_dir = pkg / "motorlar"
    engines_dir.mkdir()
    if not args.motorsuz:
        copy_tesseract(engines_dir)
        copy_ghostscript(engines_dir)
    log("4/5 Başlatıcılar ve belgeler")
    make_icon(pkg / "simgeler")
    for fname, text in (("Kur.cmd", KUR_CMD), ("Kaldir.cmd", KALDIR_CMD),
                        ("pdfe-cevir.cmd", PDFE_CEVIR_CMD)):
        (pkg / fname).write_bytes(text.replace("\n", "\r\n").encode("ascii"))
    (pkg / "OKUBENI.txt").write_text(OKUBENI.format(version=version), encoding="utf-8-sig")
    (pkg / "LISANSLAR.txt").write_text(LISANSLAR.format(py=PY_VERSION), encoding="utf-8-sig")
    (pkg / "LICENSE.txt").write_bytes(
        (ROOT / "LICENSE").read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    (pkg / "pdfatolye-kurulum.json").write_text(json.dumps(
        {"version": version, "python": PY_VERSION, "engines": not args.motorsuz}), "utf-8")
    log("5/5 Deneme")
    smoke_test(pkg)
    size = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    log(f"Paket: {size / 1024 / 1024:.0f} MB")
    if args.zip:
        archive = build / f"{name}.zip"
        archive.unlink(missing_ok=True)
        shutil.make_archive(str(archive.with_suffix("")), "zip", build, name)
        log(f"Zip: {archive} ({archive.stat().st_size / 1024 / 1024:.0f} MB)")
    shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    import traceback

    # CI'da konsol cp1252: "→", "ö" yazdırmak UnicodeEncodeError verir (hata yakalayıcısı da).
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    try:
        main()
    except SystemExit as e:
        if e.code not in (0, None):
            ci_error(str(e.code))
        raise
    except Exception as e:
        detail = str(e) if isinstance(e, StepFailed) else traceback.format_exc()[-3000:]
        log(detail)
        ci_error(detail)
        sys.exit(1)
