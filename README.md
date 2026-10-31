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
sonra tarayıcıda `http://127.0.0.1:8790` açılır.

Elle:

```
uv sync
npm --prefix web install
npm --prefix web run build
uv run python -m pdfatolye serve
```

Motor durumu: `uv run python -m pdfatolye motorlar`

Not: Windows'un Akıllı Uygulama Denetimi uv'nin ürettiği `pdfatolye.exe` başlatıcısını
engelleyebilir; bu yüzden komutlar `python -m pdfatolye` biçiminde.

## Web arayüzü

- **Ana sayfa**: dosyayı bırak; türüne göre doğru araç açılır (tek PDF → sayfa düzenleyici,
  birden çok PDF → birleştir, resimler → PDF, Markdown + resimleri → MD → PDF).
- **Sayfa düzenleyici**: sürükleyerek sırala (seçili sayfalar blok hâlinde taşınır), Ctrl/Shift
  ile çoklu seçim, `R` / `Shift+R` döndür, `Delete` sil, `Ctrl+Z` / `Ctrl+Y` geri/ileri,
  başka PDF'leri alana bırakarak sayfalarını ekle, çift tıkla büyüt. "Kaydet" yeni sürüm oluşturur,
  "Önceki sürüme dön" ile geri alınır.
- **Birleştir, Böl, Resim → PDF, PDF → Resim**: çok dosyalı çıktılar tek ZIP olarak indirilebilir.
- **Markdown → PDF**: yazdıkça canlı önizleme (baskıyla aynı tema), seçenekler, uyarılar.
- **İşler ve dosyalar**: son işler, tüm dosyalar; sabitlenmeyen dosyalar 24 saat sonra silinir.

Şifreli PDF'lerin şifresi yalnızca açık sekmenin belleğinde tutulur, hiçbir yere kaydedilmez.

## Komut satırı

Çıktı yolu (`-o`) verilmezse girdinin yanına yazılır, var olan dosyanın üstüne yazılmaz.
Sayfa aralıkları 1'den sayar: `1-3, 5, 8-`, `son`, `5-1` (ters sıra).

```
uv run python -m pdfatolye bilgi not.pdf
uv run python -m pdfatolye birlestir a.pdf b.pdf c.pdf -o hepsi.pdf --yer-imi-dosya
uv run python -m pdfatolye sec not.pdf "3,1,2"            # sırala / sayfa çıkar
uv run python -m pdfatolye sil not.pdf "2,5-7"
uv run python -m pdfatolye dondur not.pdf 90 --sayfalar "1-3"
uv run python -m pdfatolye ekle not.pdf ek.pdf --sonra 4 --sayfalar "1-2"
uv run python -m pdfatolye bos not.pdf --sonra 0
uv run python -m pdfatolye bol not.pdf --mod her | n --n 5 | aralik --aralik "1-3, 4-" | yer-imi
uv run python -m pdfatolye resimden foto1.jpg foto2.heic --boyut A4 --kenar 10
uv run python -m pdfatolye resme not.pdf --dpi 200 --bicim jpg
uv run python -m pdfatolye resimleri-cikar not.pdf
```

### Office / HTML / metin → PDF

```
uv run python -m pdfatolye cevir rapor.docx                 # rapor.pdf
uv run python -m pdfatolye cevir *.docx *.pptx -o pdfler    # her biri ayrı
uv run python -m pdfatolye cevir a.docx b.xlsx --birlestir  # tek PDF, dosya başına yer imi
uv run python -m pdfatolye cevir tez.docx --pdfa            # arşiv için PDF/A-2b
```

Word, Excel, PowerPoint, ODT/ODS/ODP, RTF, CSV LibreOffice ile; HTML ve TXT Edge ile çevrilir.
Bozuk bir dosya diğerlerini durdurmaz. Bilgisayarda olmayan fontlar (ör. Aptos) uyarılır.

### Markdown → PDF

```
uv run python -m pdfatolye md not.md                        # not.pdf (varsa üstüne yazar)
uv run python -m pdfatolye md not.md --tema rapor --icindekiler --kapak
uv run python -m pdfatolye md *.md -o pdfler                # her biri ayrı PDF
uv run python -m pdfatolye md not.md --kasa "C:\...\ObsidianKasam"   # ![[resim.png]] için
```

Desteklenenler: `$...$`, `$$...$$ (1)`, `\begin{align}`, `\ce{H2O}`; Obsidian callout'ları
(`> [!note]`, `[!warning]-` ...), `[[Not|takma ad]]`, `![[resim.png|300]]`, `==vurgu==`,
`%%yorum%%`, `#etiket`; kod renklendirme; tablo, dipnot, görev listesi; `\newpage`.
Hatalı formül baskıyı durdurmaz, satır numarasıyla uyarı verir. İnternete hiç bağlanmaz.

Ayarlar notun ön bilgisinde de verilebilir (komut satırı önceliklidir):

```yaml
---
title: Devre Analizi
author: Ad Soyad
date: 2026-10-31
pdf:
  tema: ders          # ders | rapor | sade
  kagit: A4           # A4 A5 A3 Letter Legal
  yatay: false
  kenar: 18           # mm
  icindekiler: true
  kapak: true
  sayfa_no: true
  yazi_boyutu: 11
  makrolar:
    \R: \mathbb{R}
---
```

Örnek: [ornekler/ders-notu.md](ornekler/ders-notu.md).

Şifreli PDF'ler için `--sifre` ekle. Her komutun ayrıntısı: `uv run python -m pdfatolye <komut> --help`.

## Geliştirme

```
uv run pytest            # testler
uv run ruff check .      # kod denetimi
npm --prefix web run dev # arayüz geliştirme sunucusu (API'yi 8790'e yönlendirir)
```

## Ayarlar

`config.example.toml` dosyasını `config.toml` olarak kopyalayıp düzenle.
Varsayılan veri klasörü: `%LOCALAPPDATA%\PdfAtolye`.
