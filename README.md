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

## Komut satırı

Çıktı yolu (`-o`) verilmezse girdinin yanına yazılır, var olan dosyanın üstüne yazılmaz.
Sayfa aralıkları 1'den sayar: `1-3, 5, 8-`, `son`, `5-1` (ters sıra).

```
uv run pdfatolye bilgi not.pdf
uv run pdfatolye birlestir a.pdf b.pdf c.pdf -o hepsi.pdf --yer-imi-dosya
uv run pdfatolye sec not.pdf "3,1,2"            # sırala / sayfa çıkar
uv run pdfatolye sil not.pdf "2,5-7"
uv run pdfatolye dondur not.pdf 90 --sayfalar "1-3"
uv run pdfatolye ekle not.pdf ek.pdf --sonra 4 --sayfalar "1-2"
uv run pdfatolye bos not.pdf --sonra 0
uv run pdfatolye bol not.pdf --mod her | n --n 5 | aralik --aralik "1-3, 4-" | yer-imi
uv run pdfatolye resimden foto1.jpg foto2.heic --boyut A4 --kenar 10
uv run pdfatolye resme not.pdf --dpi 200 --bicim jpg
uv run pdfatolye resimleri-cikar not.pdf
```

Şifreli PDF'ler için `--sifre` ekle. Her komutun ayrıntısı: `uv run pdfatolye <komut> --help`.

## Geliştirme

```
uv run pytest            # testler
uv run ruff check .      # kod denetimi
npm --prefix web run dev # arayüz geliştirme sunucusu (API'yi 8765'e yönlendirir)
```

## Ayarlar

`config.example.toml` dosyasını `config.toml` olarak kopyalayıp düzenle.
Varsayılan veri klasörü: `%LOCALAPPDATA%\PdfAtolye`.
