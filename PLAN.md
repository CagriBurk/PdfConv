# PDF Atölyesi — Proje Planı

> Kendi bilgisayarında çalışan, kayıt / reklam / bekleme / dosya yükleme sınırı olmayan PDF araç seti.
> Dosyalar hiçbir zaman internete çıkmaz.
> Tarih: 2026-10-31 · Durum: Faz 0, 1 ve 2 tamamlandı

---

## 1. Hedefler ve sınırlar

### 1.1 Hedefler
1. **Markdown → PDF**: LaTeX formüller, Obsidian sözdizimi, kod renklendirme; ders notu kalitesinde çıktı.
2. **Office / diğer → PDF**: docx, doc, odt, rtf, xlsx, pptx, html, txt, resimler.
3. **PDF düzenleme**: birleştir, böl, sırala, sil, döndür, başka PDF'ten sayfa ekle, boş sayfa ekle.
4. **İçerik ekleme**: yazı, resim, imza, vurgu, şekil, filigran, sayfa numarası, gerçek karartma (redaction).
5. **Sıkıştırma ve resim**: PDF küçültme, resim → PDF, PDF → resim.
6. **OCR ve güvenlik**: taranmış PDF'i aranabilir yapma (Türkçe + İngilizce), şifre koyma/kaldırma, meta veri temizleme, bozuk PDF onarma.
7. **Tek tıkla açılış**: `baslat.bat` → tarayıcıda `http://127.0.0.1:8765` açılır.

### 1.2 Tasarım ilkeleri
- **Çevrimdışı**: tüm kütüphaneler, fontlar, KaTeX dahil her şey yerelde. İnternet gerekmez.
- **Orijinale dokunma**: her işlem yeni bir *sürüm* üretir; geri al her zaman mümkündür.
- **Çekirdek arayüzden bağımsız**: tüm PDF işleri saf Python fonksiyonları; web arayüzü ve komut satırı (CLI) aynı çekirdeği çağırır. Böylece her şey test edilebilir.
- **Türkçe her yerde doğru**: ğ ü ş ı İ ö ç hem arayüzde, hem eklenen yazılarda, hem dosya adlarında, hem OCR'da.
- **Dürüst hata mesajları**: "Bir hata oluştu" yerine "Bu PDF şifreli, şifreyi gir" gibi ne yapılacağını söyleyen Türkçe mesajlar.

### 1.3 Kapsam dışı (v1)
- PDF içindeki **mevcut yazıyı yerinde düzenleme** (Acrobat seviyesi iş; v1'de "beyazla kapat + üstüne yaz" yöntemi olacak ve öyle etiketlenecek).
- PDF → Word (sonraki sürüm adayı, `pdf2docx` ile).
- Sertifikalı dijital imza (e-imza). v1'deki imza, imza *görüntüsü* eklemedir.
- Bulut, kullanıcı hesapları, çoklu kullanıcı.

---

## 2. Makinedeki mevcut durum (kontrol edildi)

| Araç | Durum | Not |
|---|---|---|
| Python | ✅ 3.11.9 | Backend için yeterli |
| Node.js | ✅ v24.16.0 | Yalnızca arayüzü derlemek için |
| Git | ✅ | Sürüm kontrolü |
| Microsoft Edge / Chrome | ✅ | Markdown → PDF baskısı için başsız (headless) kullanılacak, ayrıca tarayıcı indirilmeyecek |
| MS Word | ❌ | Bu yüzden Office dönüşümü LibreOffice ile |
| LibreOffice | ❌ → kurulacak | Office → PDF |
| Tesseract OCR | ❌ → kurulacak | Türkçe dil paketiyle |
| Ghostscript | ❌ → kurulacak | OCRmyPDF'in ihtiyacı + "güçlü sıkıştırma" |
| Pandoc | ❌ | Gerekmiyor |

Faz 0'da kurulanlar: uv 0.13.6, LibreOffice 26.8.2.2, Tesseract 5.4.0 (winget).
```
winget install astral-sh.uv
winget install TheDocumentFoundation.LibreOffice
winget install UB-Mannheim.TesseractOCR
```
Elle kurulanlar:
- **Türkçe OCR paketi**: sessiz kurulum yalnızca `eng` + `osd` getirir. `tur.traineddata` (tessdata_fast, 4,5 MB) github.com/tesseract-ocr/tessdata_fast adresinden indirilip `C:\Program Files\Tesseract-OCR\tessdata\` içine kopyalandı.
- **Ghostscript 10.08.0**: winget'te yok. Resmi `gs10080w64.exe` (github.com/ArtifexSoftware/ghostpdl-downloads, Artifex imzalı) `/S` ile sessiz kuruldu. Yükleyici uzun bir klasör yolundan çalıştırılınca hiçbir şey kurmadan çıkıyor; kısa bir yoldan çalıştırılmalı.

---

## 3. Teknoloji seçimleri

| Katman | Seçim | Neden | Elenen alternatifler |
|---|---|---|---|
| Python ortamı | **uv** + `pyproject.toml` | Hızlı, kilit dosyalı, tekrarlanabilir kurulum | pip+venv (kilit yok), conda (ağır) |
| Web sunucu | **FastAPI** + Uvicorn | Async yükleme, otomatik şema doğrulama (Pydantic), kolay test | Flask (şema doğrulama elle), Django (fazla büyük) |
| PDF çekirdeği | **PyMuPDF** (fitz) | Sayfa işlemleri, çizim, yazı/resim ekleme, açıklama, karartma, render, resim yeniden sıkıştırma — hepsi tek kütüphanede ve çok hızlı | pypdf (render yok, çizim zayıf), reportlab (sadece üretim) |
| Düşük seviye PDF | **pikepdf** (qpdf) | AES-256 şifreleme, onarım, meta veri, doğrusallaştırma | — |
| Markdown ayrıştırma | **markdown-it-py** + mdit-py-plugins | Eklenti mimarisi; `dollarmath` formülleri Markdown'dan korur; Obsidian eklentilerini yazmak kolay | Python-Markdown (formül korumada sorunlu), Pandoc (Obsidian sözdizimini bilmez) |
| Formül | **KaTeX** (yerel kopya) | Hızlı, çevrimdışı, `align`, `cases`, `matrix` vb. destekler | MathJax (yavaş baskı), LaTeX/MiKTeX (GB'larca kurulum) |
| Kod renklendirme | **Pygments** | Sunucuda renklendirir, JS gerekmez | highlight.js |
| HTML → PDF | **Playwright** + kurulu **Edge** (`channel="msedge"`) | Gerçek tarayıcı motoru: modern CSS, KaTeX JS çalışır, üst/alt bilgi + sayfa no | WeasyPrint (Windows'ta GTK derdi, JS yok), wkhtmltopdf (terk edilmiş) |
| Office → PDF | **LibreOffice** başsız mod | Ücretsiz, çevrimdışı, docx/xlsx/pptx/odt/rtf | docx2pdf (MS Word ister), bulut API (amaca aykırı) |
| OCR | **OCRmyPDF** + Tesseract (`tur+eng`) | Metin katmanını doğru hizalar, eğiklik düzeltir, döndürür, zaten metinli sayfaları atlar | Sadece PyMuPDF OCR (eğiklik düzeltme yok) |
| Resim | Pillow + **pillow-heif** | iPhone HEIC fotoğrafları dahil, EXIF yönlendirme | — |
| CLI | **Typer** | Aynı çekirdeği komut satırından kullanmak için | argparse |
| Arayüz | **React + TypeScript + Vite** | Sayfa düzenleyici ve içerik editörü karmaşık durum tutar; TS hataları erken yakalar. Derlenip FastAPI'den statik dosya olarak sunulur | Saf JS (editör büyüdükçe dağılır) |
| PDF görüntüleme (tarayıcı) | **pdf.js** (`pdfjs-dist` ≥ 4.2.67) | Küçük resimler ve editör tuvali tarayıcıda çizilir, sunucuya gidip gelme olmaz | Sunucuda PNG üretmek (yavaş, ağır) |
| Sürükle-bırak sıralama | **dnd-kit** | Grid sıralama, çoklu seçim, klavye erişimi | SortableJS |
| Editör tuvali | **Konva** (react-konva) | Yazı/resim/şekil nesnelerini taşı, boyutlandır, döndür | Fabric.js |
| İmza çizimi | **signature_pad** | Yumuşak çizgi, şeffaf PNG | — |
| Kod kalitesi | ruff, pytest, (mypy); eslint, vitest, Playwright E2E | — | — |

**Fontlar** (`assets/fonts/`, OFL lisanslı, Türkçe karakter tam): Noto Sans, Noto Serif, JetBrains Mono. PDF'e eklenen her yazı bu fontlar gömülerek yazılır (PDF'in yerleşik Helvetica'sında ğ, ş, ı, İ **yoktur** — en sık yapılan hata).

**Lisans notu**: PyMuPDF ve Ghostscript AGPL lisanslıdır. Kişisel kullanımda hiçbir sorun yok. Proje ileride herkese açık bir *hizmet* olarak yayınlanırsa kaynak kodunun da AGPL ile açılması gerekir.

---

## 4. Mimari

```
┌──────────────── Tarayıcı (localhost) ─────────────────┐
│ React arayüz: Araçlar · Sayfa Düzenleyici · Editör ·  │
│ MD→PDF · İşler · Ayarlar      (pdf.js ile görüntüleme)│
└───────────────▲───────────────────────┬───────────────┘
                │ REST + SSE (ilerleme)  │ yükleme / indirme
┌───────────────┴───────────────────────▼───────────────┐
│ FastAPI (127.0.0.1:8765)                               │
│  api/  → doğrulama (Pydantic), güvenlik (token, Host)  │
│  jobs/ → iş kuyruğu, ilerleme, iptal, zaman aşımı      │
│  storage → dosya deposu, sürümler, otomatik temizlik   │
└───────────────┬────────────────────────────────────────┘
                │ saf fonksiyon çağrısı
┌───────────────▼────────────────────────────────────────┐
│ core/     PyMuPDF + pikepdf  (sayfa, içerik, sıkıştırma, │
│           güvenlik, inceleme, geometri)                │
│ convert/  markdown (markdown-it → HTML → Edge → PDF)   │
│           office (LibreOffice alt süreç), html, resim  │
│ engines   dış araçları bulur, sürümlerini raporlar     │
└───────────────┬────────────────────────────────────────┘
                │ alt süreç (shell=False, zaman aşımlı)
     LibreOffice · Tesseract/OCRmyPDF · Ghostscript · Edge
                ▲
           cli.py (Typer) aynı core/convert'i doğrudan çağırır
```

### 4.1 Klasör yapısı
```
pdf-atolye/
├─ pyproject.toml · uv.lock · config.example.toml · baslat.bat · README.md
├─ src/pdfatolye/
│  ├─ core/
│  │  ├─ pdfio.py        # açma (şifre/bozuk dosya), güvenli yazma, dosya adı yardımcıları
│  │  ├─ pages.py        # manifest uygulama: birleştir/böl/sırala/sil/döndür/ekle/boş sayfa
│  │  ├─ ranges.py       # "1-3,5,8-" ayrıştırıcı (tek yerde, testli)
│  │  ├─ geometry.py     # ekran ↔ PDF koordinat dönüşümü (rotation, CropBox)
│  │  ├─ content.py      # yazı, resim, imza, şekil, vurgu, filigran, sayfa no, karartma
│  │  ├─ images.py       # resim → PDF, PDF → resim
│  │  ├─ compress.py
│  │  ├─ ocr.py
│  │  ├─ security.py     # şifrele, şifre kaldır, meta temizle, onar
│  │  └─ info.py         # sayfa sayısı, boyutlar, şifreli mi, metin var mı, fontlar
│  ├─ convert/
│  │  ├─ markdown/  parser.py · obsidian.py · render.py · themes/{ders,rapor,sade}.css
│  │  ├─ office.py
│  │  └─ html.py
│  ├─ engines.py · settings.py · storage.py · errors.py
│  ├─ jobs/  queue.py · models.py
│  ├─ api/   app.py · security.py · routes_files.py · routes_jobs.py · routes_md.py · schemas.py
│  └─ cli.py
├─ web/      (React + TS + Vite) src/{pages,components,editor,organizer,api}
├─ assets/   fonts/ · katex/ · pdfjs/
└─ tests/    fixtures/make_fixtures.py · test_core_*.py · test_convert_*.py · test_api_*.py · e2e/
```

### 4.2 Veri ve dosya modeli
- Veri klasörü: `%LOCALAPPDATA%\PdfAtolye\` → `files/`, `jobs/`, `logs/`, `lo-profiles/`.
- Her yüklenen dosya: `file_id` (uuid) + **sürüm listesi** `v1, v2, ...`. Sürümler değişmez (immutable); geri al = önceki sürüme dön.
- `meta.json`: orijinal ad, boyut, sayfa sayısı, şifreli mi, oluşturulma zamanı, sabitlendi mi.
- **Otomatik temizlik**: varsayılan 24 saatten eski, sabitlenmemiş dosyalar açılışta ve saatte bir silinir.
- Yükleme diske akışla (stream) yazılır; büyük dosyalar belleği doldurmaz. Varsayılan üst sınır 1 GB (ayarlanabilir).

### 4.3 Anahtar tasarım: **Sayfa Manifestosu**
Birleştirme, sıralama, silme, döndürme, başka dosyadan sayfa ekleme aslında tek bir işlemdir: *"Şu dosyaların şu sayfalarını, şu sırayla, şu açıyla diz."*

```json
{
  "op": "compose",
  "pages": [
    {"file": "a1b2", "page": 0, "rotate": 0},
    {"file": "a1b2", "page": 2, "rotate": 90},
    {"file": "c3d4", "page": 0, "rotate": 0},
    {"blank": true, "size": "A4"}
  ],
  "keep_bookmarks": true,
  "bookmark_per_file": false
}
```
- Sayfa düzenleyici arayüzü sadece bu listeyi tutar → "Kaydet" ile tek istek.
- Birleştir = her dosyanın tüm sayfaları arka arkaya. Sil = listeden çıkar. Böl = birden fazla manifest.
- Yer imleri (TOC) sayfa kaymalarına göre yeniden hesaplanır; silinen sayfayı gösteren yer imi kaldırılır.

### 4.4 İçerik editörü işlem şeması
Editörde yapılan her şey tarayıcıda nesne olarak durur, "Uygula" denince sunucuya işlem listesi gider:
```json
{"op": "apply", "file": "a1b2", "ops": [
  {"type": "text", "page": 0, "rect": [72,100,300,130], "text": "Onaylandı – Çağrı",
   "font": "NotoSans", "size": 12, "color": "#1a1a1a", "align": "left"},
  {"type": "image", "page": 0, "rect": [400,700,520,760], "asset": "sig01", "keep_aspect": true},
  {"type": "highlight", "page": 1, "quads": [[...]], "color": "#ffe066"},
  {"type": "rect", "page": 1, "rect": [...], "stroke": "#d00", "fill": null, "width": 1.5},
  {"type": "redact", "page": 2, "rect": [...]},
  {"type": "watermark", "pages": "all", "text": "TASLAK", "opacity": 0.15, "angle": 45},
  {"type": "page_numbers", "format": "Sayfa {n} / {N}", "position": "bottom-center",
   "start": 1, "skip_first": true}
]}
```
- Koordinatlar her zaman **PDF noktası** (1/72 inç) cinsinden; dönüşüm tek bir modülde (`geometry.py`) — döndürülmüş sayfalar ve kaydırılmış CropBox burada çözülür.
- Pydantic "discriminated union" ile her işlem tipi ayrı doğrulanır.

### 4.5 API taslağı
| Metot | Yol | Amaç |
|---|---|---|
| POST | `/api/files` | Yükle (çoklu). Döner: `file_id`, sayfa sayısı, şifreli mi |
| GET | `/api/files/{id}` | Meta + sürümler |
| GET | `/api/files/{id}/raw?v=` | PDF içeriği (pdf.js için) |
| GET | `/api/files/{id}/download?v=` | İndir (Türkçe dosya adı RFC 5987 ile) |
| POST | `/api/files/{id}/unlock` | Şifreyle aç |
| POST | `/api/files/{id}/undo` | Önceki sürüm |
| POST | `/api/jobs` | `{type, inputs, options}` → `job_id` |
| GET | `/api/jobs/{id}` | Durum, ilerleme, uyarılar, çıktı dosyaları |
| GET | `/api/jobs/{id}/events` | SSE ile canlı ilerleme |
| POST | `/api/jobs/{id}/cancel` | İptal |
| POST | `/api/md/preview` | Markdown → HTML (canlı önizleme) |
| GET | `/api/engines` | LibreOffice/Tesseract/Ghostscript/Edge var mı, sürümleri |
| GET | `/api/download-zip?files=` | Çoklu çıktıyı ZIP olarak indir |

İş tipleri: `compose`, `split`, `apply`, `md_to_pdf`, `office_to_pdf`, `html_to_pdf`, `images_to_pdf`, `pdf_to_images`, `compress`, `ocr`, `encrypt`, `decrypt`, `clean_metadata`, `repair`.

### 4.6 İş kuyruğu
- Redis/Celery yok (gereksiz). Uygulama içi kuyruk + iş başına alt süreç.
- Eşzamanlılık sınırları: LibreOffice **1**, OCR **1** (zaten çok çekirdek kullanır), diğerleri **4**.
- Her işin zaman aşımı var (Office 120 sn/dosya, OCR 30 sn/sayfa); aşılınca süreç ağacı öldürülür (`psutil`).
- İş geçmişi diskte JSON → sunucu yeniden başlasa da "son çıktılar" listesi kalır.

---

## 5. Özellik detayları

### 5.1 Markdown → PDF
**Akış**: `.md` → markdown-it (+eklentiler) → HTML + tema CSS → Edge'de aç → KaTeX çizilsin + fontlar yüklensin diye bekle → `page.pdf()`.

**Desteklenecek sözdizimi**
- Standart: başlık, liste, tablo, alıntı, görev listesi `- [ ]`, dipnot, yatay çizgi, resim, bağlantı.
- **Formül**: `$...$`, `$$...$$`, `\begin{align}...\end{align}` (KaTeX). Formüller Markdown işlenmeden önce korunur → `_` ve `*` formülü bozmaz. `100$ ile 200$` gibi para ifadeleri formül sanılmaz (açılıştan sonra / kapanıştan önce boşluk kuralı).
- Formül hatası olursa baskı **durmaz**: hatalı formül kırmızı gösterilir ve iş sonucunda "3 formül çizilemedi: satır 42, 88, 120" uyarısı çıkar.
- Kullanıcı tanımlı KaTeX makroları (`\R`, `\dd` vb.) ayarlardan veya front matter'dan.
- **Obsidian**:
  - Callout: `> [!note]`, `[!tip]`, `[!warning]`, `[!important]`, `[!example]`, `[!question]`, `[!quote]`… ve katlanabilir `[!note]-` (baskıda açık).
  - `[[Not]]`, `[[Not|takma ad]]` → düz metin (veya PDF içi bağlantı, aynı belgedeyse).
  - `![[resim.png]]`, `![[resim.png|300]]` → genişlikli resim. Obsidian gibi **kasanın (vault) her yerinde dosya adıyla** aranır.
  - `![[Başka not]]` → notu gömme (derinlik sınırı 3, döngü kontrolü) — v1.1.
  - `==vurgu==`, `%%yorum%%` (baskıda gizli), `#etiket` (stilli), YAML front matter → başlık sayfası (title, author, date).
- **Kod**: Pygments renklendirme, satır kaydırma (taşma yok), isteğe bağlı satır numarası.
- **Sayfa sonu**: `<!-- pagebreak -->` veya `\newpage`.

**Seçenekler**: A4/Letter, dikey/yatay, kenar boşlukları, font boyutu, tema (`ders` – formül yoğun, `rapor`, `sade`), içindekiler tablosu, başlık sayfası, üst/alt bilgi + "Sayfa n / N", başlıkların sayfa sonunda yalnız kalmaması, tablo/resim/formülün sayfa ortasından bölünmemesi (`break-inside: avoid`).

**Resim kaynağı sorunu** (web'den yüklenen tek `.md` dosyasının resimleri nerede?): üç yol desteklenir
1. `.md` + resimleri birlikte sürükle-bırak,
2. Klasörü/ZIP'i bırak,
3. Ayarlarda **Obsidian kasa yolu** tanımla → sunucu yerelde olduğu için resimleri doğrudan oradan okur (yalnızca bu kök klasörün altı; dışarısı yasak).

**Arayüz**: solda ayarlar, sağda **canlı önizleme** (baskıyla aynı CSS, `@media print`), "PDF oluştur" butonu. Toplu mod: bir klasördeki tüm notlar → ayrı PDF'ler veya tek birleşik PDF.

### 5.2 Office ve diğer formatlar → PDF
- Komut (shell yok, argüman listesi):
  `soffice --headless --norestore --nolockcheck -env:UserInstallation=file:///<izole-profil> --convert-to pdf --outdir <çıktı> <girdi>`
- **İzole profil**: her çalışan için ayrı LibreOffice profili → açık bir LibreOffice penceresi veya takılmış eski süreç dönüşümü kilitlemez.
- Zaman aşımı + süreç ağacını öldürme; başarısız dosya toplu işte diğerlerini durdurmaz.
- **Font kontrolü**: dönüşüm sonrası PDF'teki fontlar okunur, belgede istenen fontlarla karşılaştırılır → "Calibri bulunamadı, yerine Carlito kullanıldı" uyarısı.
- İsteğe bağlı PDF/A çıktısı (arşiv için).
- Bilinen sınırlar (arayüzde yazılacak): Excel'de baskı alanı/ölçek dosyadaki sayfa ayarına göre çıkar; PowerPoint animasyonları statik olur; çok karmaşık Word yerleşimlerinde küçük kaymalar olabilir.
- HTML → PDF: Edge motoruyla. TXT → PDF: Markdown hattından düz metin olarak.

### 5.3 Sayfa düzenleme (Sayfa Düzenleyici ekranı)
- Küçük resim ızgarası (pdf.js, görünür olanlar tembel çizilir → 500 sayfalık PDF'te de akıcı).
- Sürükleyerek sırala; **çoklu seçim** (Ctrl/Shift tık, Ctrl+A); seçilenleri döndür / sil / ayrı PDF olarak çıkar.
- Başka PDF'leri pencereye bırak → sayfaları ızgaraya karışık olarak eklenir (dosyalar renkli çerçeveyle ayırt edilir).
- Boş sayfa ekle (A4/Letter/önceki sayfa boyutu).
- Kısayollar: `Del` sil, `R` / `Shift+R` döndür, `Ctrl+Z` / `Ctrl+Y` geri/ileri, oklarla gezinme.
- Sayfaya çift tık → büyük önizleme.
- **Böl** modları: her sayfa ayrı, her N sayfada bir, aralıklarla (`1-3, 4-10, 11-`), üst seviye yer imlerine göre. Çoklu çıktı → ZIP.
- Aralık sözdizimi arayüzde 1'den başlar, çekirdekte 0'dan — dönüşüm tek bir fonksiyonda (`ranges.py`), kenar durumları testli.

### 5.4 İçerik ekleme (Editör ekranı)
- Araç çubuğu: Seç · Yazı · Resim · İmza · Vurgu · Dikdörtgen/Elips/Çizgi/Ok · Karartma · Beyazla kapat.
- Nesneler taşınır, boyutlandırılır, döndürülür, silinir; sağ panelde özellikler (font, boyut, renk, opaklık).
- **İmza**: tuvale çiz / resim yükle (arka plan otomatik şeffaflaştırılır) → "imzalarım" listesinde saklanır, sonraki belgelerde tek tıkla kullanılır.
- **Filigran**: yazı veya resim, açı, opaklık, içeriğin önünde/arkasında, sayfa aralığı.
- **Sayfa numarası**: format (`{n}`, `{N}`, `Sayfa {n} / {N}`), 6 konum, başlangıç numarası, ilk sayfayı atla, aralık.
- **Karartma (redaction)**: altındaki yazı ve resim gerçekten **silinir** (`apply_redactions`). Arayüzde "siyah kutu çizmek ≠ karartma" uyarısı; sadece gerçek karartma aracı gizlilik için önerilir.
- **"Beyazla kapat + yaz"**: mevcut yazıyı düzeltmek için geçici çözüm, açıkça etiketli.
- Tüm eklenen yazılar gömülü Noto fontlarıyla → Türkçe karakter sorunu yok.

### 5.5 Sıkıştırma
| Seviye | Yöntem | Beklenen |
|---|---|---|
| Kayıpsız | Kullanılmayan nesneleri at, akışları yeniden sıkıştır, nesne akışları | %5–30, kalite kaybı sıfır |
| Dengeli | + 150 DPI üstü resimleri 150 DPI'a indir, JPEG kalite 75 | Taramalarda %50–80 |
| Güçlü | + 100 DPI, kalite 60 (veya Ghostscript `/ebook`) | En küçük boyut |
- Önce/sonra boyut gösterilir. **Sonuç orijinalden büyükse orijinal korunur** ve bu söylenir.
- Toplu sıkıştırma desteklenir.

### 5.6 Resim ↔ PDF
- **Resim → PDF**: JPG, PNG, WEBP, TIFF (çok sayfalı), HEIC. Sürükleyerek sırala. Sayfa boyutu: resme uy / A4 (kenar boşluklu). Yön otomatik. EXIF döndürmesi uygulanır (telefon fotoğrafı yan çıkmaz). Seçenek: "taranmış belge gibi" (gri ton + kontrast).
- **PDF → Resim**: PNG/JPG, 72–300 DPI, sayfa aralığı; çoklu sayfa → ZIP. Ayrıca "PDF'teki gömülü resimleri olduğu gibi çıkar".

### 5.7 OCR
- `ocrmypdf -l tur+eng --rotate-pages --deskew --skip-text` (zaten metni olan sayfaları atlar; isteğe bağlı `--redo-ocr` / `--force-ocr`).
- İlerleme sayfa sayfa SSE ile gösterilir; iptal edilebilir.
- Sonuç kontrolü: OCR'dan sonra metin çıkarılır, "x sayfada metin bulundu" özeti.
- Sayfa düzenleyici yüklemede "Bu PDF'te metin yok, OCR yapılsın mı?" önerisi (`inspect.py`).

### 5.8 Güvenlik ve bakım
- **Şifrele**: AES-256; açılış şifresi + isteğe bağlı sahip şifresi; izinler (yazdırma, kopyalama, düzenleme).
- **Şifre kaldır**: açılış şifresi biliniyorsa. Sadece kısıtlamalı (açılış şifresiz) PDF'lerde kısıtları kaldırma — *kendi dosyaların için*. Şifre kırma yok.
- **Meta veri temizle**: yazar, oluşturan program, XMP, gizli ekler.
- **Onar**: bozuk PDF'i pikepdf ile yeniden yaz; açılamayan dosyada otomatik önerilir.

---

## 6. Arayüz ekranları
1. **Ana sayfa**: araç kartları + ortada büyük "dosyayı buraya bırak" alanı. Bırakılan dosya türüne göre öneri (PDF → Düzenle/Sıkıştır/OCR…, DOCX → PDF'e çevir, MD → MD→PDF, resimler → PDF yap).
2. **Sayfa Düzenleyici** (5.3).
3. **Editör** (5.4).
4. **MD → PDF** (5.1).
5. **Tek adımlı araçlar** (sıkıştır, OCR, şifrele, böl, resim↔PDF): seçenek formu + "Başlat" + ilerleme + indir.
6. **İşler**: son çıktılar, ilerleme, hata ayrıntısı, "tekrar indir", "sabitle", "klasörde göster".
7. **Ayarlar**: port, veri klasörü, saklama süresi, Obsidian kasa yolu, varsayılan tema/kağıt, **motor durumu** (LibreOffice ✅ 24.x, Tesseract ✅ tur+eng, Ghostscript ✅, Edge ✅) ve eksikse kurulum komutu.
- Açık/koyu tema, Türkçe arayüz (metinler tek dosyada, ileride İngilizce eklenebilir).

---

## 7. Güvenlik (yerel sunucu olsa bile)
Tarayıcıda açık başka bir web sitesi, `localhost`'taki sunucuna istek atmayı deneyebilir. Önlemler:
- Yalnızca `127.0.0.1`'e bağlan (varsayılan).
- **Host başlığı kontrolü** (yalnızca `127.0.0.1` / `localhost`) → DNS rebinding saldırısını keser.
- **Origin kontrolü** + açılışta üretilen rastgele **oturum belirteci** (SameSite=Strict çerez) → başka site API'yi çağıramaz.
- **Telefon / LAN modu** (`baslat.bat --lan`): `0.0.0.0`'a bağlanır, ekranda belirteçli adresin **QR kodu** gösterilir; belirteçsiz istek reddedilir.
- Dosya adları temizlenir; ZIP açarken "zip slip" (../ ile dışarı yazma) engellenir; kullanıcıdan gelen yol yalnızca izin verilen köklerin (kasa yolu) altında okunur.
- Alt süreçler `shell=False` + argüman listesiyle; zaman aşımlı.
- pdf.js `isEvalSupported: false` ve ≥ 4.2.67 (bilinen açık CVE-2024-4367 kapalı). PDF içi JavaScript hiçbir yerde çalıştırılmaz.
- Yükleme boyutu ve sayfa sayısı üst sınırları (ayarlanabilir).

---

## 8. Bilinen tuzaklar ve çözümleri

| # | Tuzak | Çözüm |
|---|---|---|
| 1 | Eklenen yazıda ğ/ş/ı/İ kutucuk çıkar | Her zaman gömülü Noto TTF; testte Türkçe metin çıkarılıp doğrulanır |
| 2 | Döndürülmüş sayfada yazı yanlış yere/yan konur | `geometry.py`: rotation + CropBox dönüşümü; 0/90/180/270 ve kaydırılmış CropBox fixture'larıyla test |
| 3 | Birleştirmede yer imleri kaybolur | TOC sayfa kaymasıyla yeniden kurulur |
| 4 | Şifreli PDF yüklenince çöker | `inspect` önce kontrol eder, arayüz şifre sorar |
| 5 | Bozuk PDF açılmaz | pikepdf ile onarım denemesi, sonra kullanıcıya bilgi |
| 6 | LibreOffice takılır / açık pencere kilitler | İzole profil, tek çalışan, zaman aşımı + süreç ağacı öldürme |
| 7 | Markdown formülü bozar (`a_1*b_2`) | `dollarmath` ile formül önce korunur; test seti |
| 8 | KaTeX çizilmeden PDF basılır | `document.fonts.ready` + KaTeX bitti işareti beklenir |
| 9 | Sıkıştırma dosyayı büyütür | Büyüdüyse orijinal korunur |
| 10 | Türkçe dosya adı indirmede bozulur | `Content-Disposition: filename*=UTF-8''...` |
| 11 | Windows dosya kilidi (silinemeyen dosya) | PyMuPDF belgeleri `with` ile kapatılır; temizlik hataları loglanır, tekrar denenir |
| 12 | 1 tabanlı / 0 tabanlı sayfa karışıklığı | Tek dönüşüm noktası (`ranges.py`) |
| 13 | OCR zaten metinli sayfayı bozar | `--skip-text` varsayılan |
| 14 | Telefon fotoğrafı yan çıkar | EXIF yönlendirmesi uygulanır |
| 15 | Büyük PDF tarayıcıyı dondurur | Küçük resimler tembel çizilir, sanal liste |
| 16 | Siyah kutu "karartma" sanılır | Gerçek `apply_redactions` + arayüz uyarısı |
| 17 | **Uzun yolda LibreOffice çöker** (Faz 0'da yaşandı: 281 karakterlik profil yolunda `0xC0000409`) | Profiller ve iş klasörleri her zaman kısa veri klasöründe (`%LOCALAPPDATA%\PdfAtolye\...`); girdi dosyası dönüşümden önce oraya kopyalanır |
| 18 | PyMuPDF 2.0'da `import fitz` kullanımdan kalktı | Her yerde `import pymupdf` |
| 19 | **CRLF satır sonlu .md'de `\newpage` tanınmıyordu** (Faz 2 testinde yakalandı) | Ayrıştırmadan önce satır sonları `\n`'e çevrilir; testler iki biçimle de çalışır |
| 20 | KaTeX `align` ortamını numaralar, Obsidian (MathJax) numaralamaz | Baskıda `align` → `align*` (equation, gather vb. de); elle numara için `$$ ... $$ (1)` |
| 21 | İçindekilerde sayfa numarası Chromium'da CSS ile yapılamıyor | İki geçiş: ilk baskının yer imlerinden başlık sayfaları okunur, `000` yer tutucuları doldurulup yeniden basılır (aynı genişlik → yerleşim değişmez) |

**Faz 2 notları**: Not gömme (`![[Başka not]]`) henüz yok, uyarı verir. Sayfa numarası kapak sayfasında da görünür (Chromium sınırı).

---

## 9. Test stratejisi
- **Fixture üreticisi** (`tests/fixtures/make_fixtures.py`): kodla üretilen PDF'ler — farklı sayfa boyutları, 90/180/270 döndürülmüş, kaydırılmış CropBox, şifreli, yer imli, formlu, "taranmış" (Türkçe metnin resmi), 300 sayfalık büyük dosya; örnek `.docx` (tablo, resim, Türkçe), örnek `.md` (formül, callout, kod, Obsidian resim).
- **Çekirdek birim testleri**: her sayfaya "Sayfa 3" yazılı fixture → sıralama/silme sonrası metin çıkarılarak doğru sıra kontrolü; döndürme değerleri; yer imi hedefleri; Türkçe karakterli eklenen yazının geri okunması; fontların gömülü olduğu; şifrelemenin AES-256 olduğu.
- **Dönüşüm testleri**: MD → HTML anlık görüntü (snapshot) testleri; MD → PDF'te formül hatası olmadığı; PDF'in sayfa render'ı referans görüntüyle toleranslı karşılaştırma (görsel regresyon). Office → PDF'te Türkçe metnin çıkarılabildiği. Motor yoksa test atlanır (skip), başarısız sayılmaz.
- **API testleri**: FastAPI TestClient; güvenlik testleri (yanlış Host, belirteçsiz istek, zip slip, kök dışı yol → reddedilmeli).
- **Arayüz**: vitest (manifest/geçmiş mantığı), Playwright E2E: yükle → sürükle sırala → kaydet → indir → sayfa sırası doğru.
- **Komut**: `uv run pytest` tek komutla hepsi; isteğe bağlı GitHub Actions (windows-latest).

---

## 10. Yol haritası (fazlar)

Boyut: **K** küçük · **O** orta · **B** büyük. Her faz sonunda çalışan, kullanılabilir bir şey olur.

### Faz 0 — Kurulum ve iskelet (K)
- Git deposu, `uv` projesi, ruff/pytest, Vite + React + TS iskeleti.
- LibreOffice, Tesseract (tur+eng), Ghostscript kurulumu.
- `engines.py` + `/api/engines` + Ayarlar sayfasında motor durumu.
- `baslat.bat`: sunucuyu başlatır, tarayıcıyı açar.
- **Bitti sayılır**: `baslat.bat` → tarayıcıda boş arayüz ve 4 motorun hepsi ✅ görünür; `uv run pytest` yeşil.

### Faz 1 — PDF çekirdeği + CLI (O)
- `ranges.py`, `inspect.py`, `pages.py` (manifest), böl, resim ↔ PDF, fixture üreticisi, testler.
- CLI: `pdfatolye birlestir a.pdf b.pdf -o c.pdf`, `bol`, `dondur`, `sil`, `resimden`, `resme`.
- **Bitti sayılır**: tüm sayfa işlemleri CLI'dan çalışır; döndürülmüş/şifreli/yer imli fixture testleri geçer.

### Faz 2 — Markdown → PDF (O)
- Parser + Obsidian eklentileri + KaTeX + Pygments + 3 tema + Edge ile baskı; uyarı raporu.
- CLI: `pdfatolye md not.md --tema ders --icindekiler`.
- **Bitti sayılır**: gerçek bir ders notun (formül + callout + resim + kod) hatasız ve düzgün sayfalanmış PDF olur; formül hata raporu çalışır.

### Faz 3 — Web arayüzü: depo, işler, Sayfa Düzenleyici, MD ekranı (B)
- Yükleme, sürümler/geri al, iş kuyruğu + SSE, güvenlik katmanı (Host/Origin/belirteç).
- Ana sayfa, Sayfa Düzenleyici (ızgara, sürükle, çoklu seçim, başka PDF ekle, kısayollar), Böl ekranı, MD → PDF ekranı (canlı önizleme), İşler ekranı.
- **Bitti sayılır**: 3 PDF'i bırakıp sayfalarını karıştırıp döndürüp silip tek PDF indirebilirsin; geri al çalışır; MD canlı önizlemesi baskıyla aynı görünür.

### Faz 4 — Office ve diğer dönüşümler (O)
- `office.py` (izole profil, zaman aşımı, font uyarısı), HTML/TXT, toplu dönüşüm + ZIP.
- **Bitti sayılır**: 10 karışık dosyalık (docx/xlsx/pptx/odt) toplu dönüşüm, biri bozuk olsa bile diğerleri biter; font uyarıları görünür.

### Faz 5 — İçerik Editörü (B)
- `geometry.py`, `content.py`; Konva editör; yazı/resim/imza/vurgu/şekil/karartma/beyazla kapat; filigran ve sayfa numarası ekranları; imzalarım.
- **Bitti sayılır**: 90° döndürülmüş bir sayfaya Türkçe yazı ve imza doğru yerde ve doğru yönde eklenir; karartılan yazı metin çıkarmada artık görünmez.

### Faz 6 — Sıkıştırma, OCR, güvenlik (O)
- 3 seviyeli sıkıştırma, OCRmyPDF entegrasyonu + ilerleme/iptal, şifrele/kaldır, meta temizle, onar; yüklemede "metin yok → OCR?" önerisi.
- **Bitti sayılır**: taranmış Türkçe bir belge aranabilir olur (Ctrl+F ile "ğ/ş" içeren kelime bulunur); 50 MB'lık taranmış PDF "dengeli" ile belirgin küçülür.

### Faz 7 — Sağlamlaştırma ve kolaylıklar (O)
- E2E testler, hata mesajı kataloğu, log dosyası + arayüzde hata kimliği, otomatik temizlik, LAN/telefon modu + QR.
- Windows kolaylıkları: masaüstü kısayolu, **Sağ tık → Gönder → "PDF'e çevir"** (CLI çağırır), isteğe bağlı sistem tepsisi simgesi.
- İsteğe bağlı: PyInstaller ile tek klasörlük paket.
- **Bitti sayılır**: temiz bir Windows kullanıcı hesabında README'deki adımlarla 10 dakikada kurulur ve çalışır.

### Sonraki sürüm adayları
PDF → Word (`pdf2docx`), form doldurma, iki PDF'i karşılaştırma, not gömme (`![[Not]]`), Pandoc/LaTeX alternatif MD motoru, PDF/A doğrulama, İngilizce arayüz.

---

## 11. Riskler

| Risk | Olasılık | Etki | Önlem |
|---|---|---|---|
| LibreOffice karmaşık Word dosyasında yerleşimi bozar | Orta | Orta | Font uyarısı, bilinen sınırlar notu; ileride gerekirse Word'lü bir bilgisayarda COM motoru eklenebilir (mimari motor değiştirmeye hazır) |
| Editör koordinat hataları | Orta | Yüksek | Tek geometri modülü + döndürülmüş fixture testleri, Faz 5'in ilk işi |
| KaTeX'in desteklemediği LaTeX komutu | Düşük | Düşük | Hata raporu + makro desteği |
| Edge güncellemesi Playwright'ı bozar | Düşük | Orta | Playwright güncel tutulur; yedek olarak Chrome kanalı |
| Proje kapsamı büyür, bitmez | Orta | Yüksek | Faz sırası katı; her faz kendi başına kullanılabilir; "sonraki sürüm" listesi |

---

## 12. Çalışma düzeni
- Her faz ayrı bir git dalında, sonunda `main`'e birleştirilir; her faz için kısa bir "ne yapıldı" notu.
- Önce çekirdek + test, sonra API, en son arayüz.
- `config.toml` ile tüm ayarlar (port 8765, veri klasörü, saklama 24 saat, maks. yükleme 1 GB, motor yolları, kasa yolu).
