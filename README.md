# PDF Atölyesi

Kendi bilgisayarında çalışan, çevrimdışı PDF araç seti: Markdown / Office → PDF,
sayfa düzenleme, içerik ekleme, sıkıştırma, OCR, şifreleme. Dosyalar internete çıkmaz.
Ayrıntılı plan: [PLAN.md](PLAN.md).

## Gereksinimler

- Windows 10/11, Python 3.11+, [uv](https://docs.astral.sh/uv/), Node.js 20+ (yalnızca arayüzü derlemek için)
- Dış araçlar:

  ```
  winget install astral-sh.uv
  winget install TheDocumentFoundation.LibreOffice
  winget install UB-Mannheim.TesseractOCR
  ```

  - Tesseract Türkçe paketi: `tur.traineddata` dosyasını
    github.com/tesseract-ocr/tessdata_fast'tan indirip `C:\Program Files\Tesseract-OCR\tessdata\` içine kopyala.
  - Ghostscript winget'te yok: github.com/ArtifexSoftware/ghostpdl-downloads sürümlerinden
    `gs*w64.exe` dosyasını kısa bir klasöre indirip kur.
  - Edge Windows ile birlikte gelir.

## Çalıştırma

`baslat.bat` dosyasına çift tıkla. İlk açılışta bağımlılıkları kurar ve arayüzü derler,
sonra tarayıcıda `http://127.0.0.1:8765` açılır.

Elle:

```
uv sync
npm --prefix web install
npm --prefix web run build
uv run pdfatolye serve
```

Motor durumu: `uv run pdfatolye motorlar`

## Geliştirme

```
uv run pytest            # testler
uv run ruff check .      # kod denetimi
npm --prefix web run dev # arayüz geliştirme sunucusu (API'yi 8765'e yönlendirir)
```

## Ayarlar

`config.example.toml` dosyasını `config.toml` olarak kopyalayıp düzenle.
Varsayılan veri klasörü: `%LOCALAPPDATA%\PdfAtolye`.
