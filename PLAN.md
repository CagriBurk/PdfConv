# PDF Atölyesi — Proje Planı

> Kendi bilgisayarında çalışan, kayıt / reklam / bekleme / dosya yükleme sınırı olmayan PDF araç seti.
> Dosyalar hiçbir zaman internete çıkmaz.
> Tarih: 2026-11-07 · Durum: Faz 0–7 tamamlandı (v1). Ürünleşme: Faz A, B, C ve D yapıldı, sıradaki Faz E (§10.1); kararlar §10.2

---

## 1. Hedefler ve sınırlar

### 1.1 Hedefler
1. **Markdown → PDF**: LaTeX formüller, Obsidian sözdizimi, kod renklendirme; ders notu kalitesinde çıktı.
2. **Office / diğer → PDF**: docx, doc, odt, rtf, xlsx, pptx, html, txt, resimler.
3. **PDF düzenleme**: birleştir, böl, sırala, sil, döndür, başka PDF'ten sayfa ekle, boş sayfa ekle.
4. **İçerik ekleme**: yazı, resim, imza, vurgu, şekil, filigran, sayfa numarası, gerçek karartma (redaction).
5. **Sıkıştırma ve resim**: PDF küçültme, resim → PDF, PDF → resim.
6. **OCR ve güvenlik**: taranmış PDF'i aranabilir yapma (Türkçe + İngilizce), şifre koyma/kaldırma, meta veri temizleme, bozuk PDF onarma.
7. **Tek tıkla açılış**: `baslat.bat` → tarayıcıda `http://127.0.0.1:8790` açılır.

### 1.2 Tasarım ilkeleri
- **Çevrimdışı**: tüm kütüphaneler, fontlar, KaTeX dahil her şey yerelde. İnternet gerekmez.
- **Orijinale dokunma**: her işlem yeni bir *sürüm* üretir; geri al her zaman mümkündür.
- **Çekirdek arayüzden bağımsız**: tüm PDF işleri saf Python fonksiyonları; web arayüzü ve komut satırı (CLI) aynı çekirdeği çağırır. Böylece her şey test edilebilir.
- **Türkçe her yerde doğru**: ğ ü ş ı İ ö ç hem arayüzde, hem eklenen yazılarda, hem dosya adlarında, hem OCR'da.
- **Dürüst hata mesajları**: "Bir hata oluştu" yerine "Bu PDF şifreli, şifreyi gir" gibi ne yapılacağını söyleyen Türkçe mesajlar.

### 1.3 Kapsam dışı (v1)
- PDF içindeki **mevcut yazıyı yerinde düzenleme** (Acrobat seviyesi iş; v1'de "beyazla kapat + üstüne yaz" yöntemi olacak ve öyle etiketlenecek).
- ~~PDF → Word~~: eklendi (`pdf2docx`), PDF → Excel ile birlikte (Faz F).
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

**Lisans notu**: PyMuPDF ve Ghostscript AGPL ya da ticari lisanslıdır. Kişisel kullanımda sorun yok. Uygulamayı başkalarına *vermek* (arkadaşlara kurulum dosyası dahil) ya da herkese açık *hizmet* olarak sunmak AGPL yükümlülüğü doğurur: kaynak kodu AGPL ile erişilebilir olmalı. Kapalı kaynak satış için Artifex'ten ticari lisans gerekir.

---

## 4. Mimari

```
┌──────────────── Tarayıcı (localhost) ─────────────────┐
│ React arayüz: Araçlar · Sayfa Düzenleyici · Editör ·  │
│ MD→PDF · İşler · Ayarlar      (pdf.js ile görüntüleme)│
└───────────────▲───────────────────────┬───────────────┘
                │ REST + SSE (ilerleme)  │ yükleme / indirme
┌───────────────┴───────────────────────▼───────────────┐
│ FastAPI (127.0.0.1:8790)                               │
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
- Yükleme diske akışla (stream) yazılır; büyük dosyalar belleği doldurmaz. Varsayılan üst sınır dosya başına 8 GB (ayarlanabilir; ilk sürümde 1 GB'tı, şehir planlama paftaları için yükseltildi).

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
- **Güvenlik başlıkları**: uygulama CSP ile yalnızca kendi betiklerini çalıştırır; `nosniff`, `no-referrer`. Yüklenen HTML/SVG kum havuzunda sunulur, uygulamanın kökeninde betik çalıştıramaz.
- **Telefon / LAN modu** (`baslat.bat --lan`): `0.0.0.0`'a bağlanır, ekranda belirteçli adresin **QR kodu** gösterilir; belirteçsiz istek reddedilir. QR tek kullanımlık, her cihazın kendi oturumu var, oturumlar kesilebilir. Bağlantı HTTP'dir (yerel ağda şifresiz); bu arayüzde söylenir. Telefon modu dışında loopback dışı `host` reddedilir.
- **Güvenilmeyen belge baskısı** (`convert/browser.py`): tarayıcı ölü bir vekil sunucuyla başlar, her istek süzülür; belge dışarı veri gönderemez, disk dosyası gömemez.
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

| 22 | **Port 8765'i başka bir yerel proje kullanıyordu** ve "zaten çalışıyor" kontrolü onu bizim sunucumuz sandı | Varsayılan port 8790; `/api/health` artık `"app": "pdfatolye"` döndürür, kontrol buna bakar |
| 23 | **Windows Akıllı Uygulama Denetimi uv'nin ürettiği `pdfatolye.exe`'yi engelliyor** | `baslat.bat` ve belgeler `uv run python -m pdfatolye` kullanır (imzalı python.exe) |
| 24 | Kum havuzlu (sandbox) önizleme iframe'i localhost'tan KaTeX yükleyemiyor | iframe aynı kökende, ama içerik güvenlik politikası (nonce) ile: yalnızca KaTeX betikleri çalışır, notun içindeki betikler/ağ istekleri engellenir |
| 25 | Arayüzden gelen CRLF metin Windows'ta `write_text` ile `\r\r\n` oluyor, uyarı satır numaraları ikiye katlanıyordu | Yazarken `newline=""` + satır sonu normalleştirme; arayüz de metni yüklerken `\n`'e çevirir |

| 26 | **LibreOffice 26.8 bir kez kullanılmış profille (kopyasıyla bile) ikinci çağrıda takılıyor**; öldürülen soffice.com'un açtığı soffice.bin arkada kalıyordu | Her çağrıda taze profil (~4 sn); toplu dönüşüm tek çağrıda, çıkmayan dosya tek başına yeniden denenir; profil yolunu taşıyan tüm soffice süreçleri her çağrıdan sonra öldürülür. Planlanan "kalıcı profil" yaklaşımı bu yüzden bırakıldı |

| 27 | **PyMuPDF 2.0'da `page.transformation_matrix` döndürülmüş + CropBox'ı kaydırılmış sayfada ofseti kaybediyor** | Hiçbir yerde kullanılmaz; görünüm ↔ sayfa dönüşümü yalnızca `rotation_matrix` / `derotation_matrix` ile (`geometry.py`) |
| 28 | `morph` matrisi PDF'in y'si yukarı uzayında uygulanıyor: `Matrix(30)` ekranda saat yönünün **tersine** döndürür | `geometry.morph_matrix(açı)` işareti çevirir; döndürülmüş yazı/şekil testleri yönü denetler |
| 29 | Çoğu Windows fontunda boşluk ve NBSP aynı glifi paylaşır; tam font gömülünce metin çıkarmada boşluklar U+00A0 okunur (Ctrl+F bulamaz) | Font fontTools ile kullanılan karakterlere indirgenip gömülür (`core/fonts.py`): hem boşluk doğru okunur hem dosya ~1 MB yerine birkaç KB büyür |
| 30 | `insert_textbox` yazı sığmazsa **hiçbir şey yazmaz** (negatif değer döner) | Kutu eksik yükseklik kadar uzatılıp yeniden denenir; yine sığmazsa uyarı |

| 31 | OCRmyPDF API'si ana süreçte çalışırsa iptal edilemez; kendi günlüğünü de yapılandırmadan hiçbir şey yazmaz | `core/_ocr_run.py` ayrı süreçte çalışır (iptal/zaman aşımı = süreç ağacını öldür); ilerleme bir OCRmyPDF eklentisiyle (`_ocr_plugin.py`) stderr'e `PA_OCR {json}` satırları olarak gelir; `configure_logging` ile "sayfada zaten metin var" satırları sayılır |
| 32 | `"İzin".lower()` Python'da `"i̇zin"` olur (noktalı i + birleşik nokta) | Türkçe metin karşılaştırmasında `lower()`a güvenme; testler küçük harfli kelime arar |

| 33 | Bash heredoc içinde `'` geçen Türkçe metin (ör. `İğdır'da`) araç kabuğunda tırnak hatası verdi | Uzun düzenleme betikleri dosyaya yazılıp öyle çalıştırılır |
| 34 | `_setup_logging` ilk uygulamanın günlük dosyasını tutuyordu; aynı süreçte farklı veri klasörüyle yeni uygulama (testler) eski dosyaya yazıyordu | Var olan dosya işleyicisi hedef yol farklıysa değiştirilir |
| 35 | **`apply_redactions` açıklamalara ve form alanlarına dokunmaz**: karartılan yerde not ve form değeri dosyada okunabilir kalıyordu | Önce kutuya değen açıklama ve form alanları silinir; sayfanın `Thumb`/`PieceInfo` verisi de kaldırılır (`content.py`) |
| 36 | **PyMuPDF ve pikepdf `save` varsayılanı şifreyi kaldırır**: şifreli PDF düzenlenince sessizce şifresizleşiyordu | İşlem sonrası `security.keep_encryption`: aynı şifre ve izinler AES-256 ile geri uygulanır; birden çok kaynakta uyarı |
| 37 | **Açılış şifresi = sahip şifresi ise izin kısıtları uygulanmaz** (dosyayı açan tam yetkili sayılır) | Kısıt varken sahip şifresi rastgele üretilir; ikisi aynı verilirse reddedilir |
| 38 | **`page.route` WebSocket'i yakalamaz**: belge içeriği dışarı sızabiliyordu. `page.route_web_socket` ise eşzamanlı API'de sayfa açılışını kilitliyor (süreç takılı kalıyor) | Tarayıcı `--proxy-server` ile ölü vekile yönlendirilir, `<-loopback>` ile loopback muafiyeti kalkar |
| 39 | **Sandbox iframe + `allow-same-origin` üstünden uygulama CSP'si srcdoc'a miras kalır** | Uygulama politikası KaTeX başlatıcısına özetiyle (`sha256-...`) izin verir; çerçevenin kendi nonce politikası da geçerlidir, ikisi birlikte uygulanır |
| 40 | Python'da `secrets.compare_digest` ASCII dışı `str`'de hata verir: `?t=ğ` isteği 500 dönüyordu | Belirteçler bayta çevrilip karşılaştırılır (`tokens_match`) |

| 41 | `safe_filename(max_len=80)` uzantıyı da kesiyordu: uzun adlı PDF `kind=other` oluyor, "PDF değil" hatası veriyordu; çıktı adındaki `_duzenlenmis` eki de kesiliyordu | Kök ve uzantı ayrı (`safe_name_with_ext`); çıktı adındaki kaynak kökü 56 karakter (`workers.STEM_MAX`) |
| 42 | `Path("Sürüm 1.2 son").suffix` → `".2 son"`: yeniden adlandırma ve çıktı adı noktadan sonrasını atıyordu | Uzantı yalnızca kısa, harf/rakam son parça (`split_ext`); atılan yalnızca dosyanın kendi ya da bilinen bir türün uzantısı |
| 43 | Sürüm numarası yeniden kullanılıyor (Kaydet → v2, geri al → v1, Kaydet → yeni v2): `fileId@sürüm` anahtarlı küçük resim önbelleği eski v2'yi gösteriyordu | Anahtar sürümün oluşturulma zamanını da taşır (`PdfRef.updated`); `forgetPdf` küçük resimleri de bırakır |
| 44 | Hash değişimi `beforeunload`'u tetiklemez: uygulama içi gezinmede kaydedilmemiş iş sessizce kayboluyordu | Yönlendirici seviyesinde koruma (`useLeaveGuard`): bağlantı, `navigate` ve geri/ileri düğmesi sorar; vazgeçilirse adres `pushState` ile geri yazılır |
| 45 | Tek bir bozuk `meta.json` `KeyError` ile `/api/files`'ı (500) ve saatlik temizliği durduruyordu | `get` her bozukluğu `CorruptMetaError`'a çevirir, günlüğe bir kez yazar; liste ve temizlik atlar; bilinmeyen alanlar yok sayılır, `schema` alanı |
| 46 | Sınırlı türlerin semaforu havuz iş parçacığında bekleniyordu: sırada 4 OCR işi varken birleştirme bile bekliyordu | Sınırlı her türün kendi tek iş parçacıklı sırası (`JobManager._limited`) |
| 47 | İptal yalnızca bir sonraki `report`'ta etkiliydi; LibreOffice/Ghostscript/tarayıcı baskısı fiilen iptal edilemiyordu, kapanışta alt süreçler öksüz kalıyordu | İş başına iptal bayrağı (`proc.cancel_scope`); `proc.run`/`spawn` süreç ağacını öldürür; tarayıcı işaretle (`--pa-isaret`) başlatılır, `Watchdog` öldürür; kapanışta `proc.kill_all` |
| 48 | Güvenilmeyen HTML `load`'dan sonra sonsuz döngüye girince `page.evaluate`/`page.pdf` zaman aşımsız bekliyordu | `OfflineBrowser.guard`: baskının üst süresi dolunca tarayıcı öldürülür, anlaşılır hata |
| 49 | Uygulamanın CSP'si Playwright'ın `wait_for_function("...")` dize değerlendirmesini engeller | E2E testlerde `expect(locator)` kullanılır |
| 50 | **Bu makinedeki araç kabuğunda heredoc `\\` → `\` çeviriyor** (tuzak #33'ün asıl nedeni): betik ya da JSON içindeki `"\\n"` dosyaya gerçek satır sonu olarak yazıldı | Ters eğik çizgi içeren betik/düzenleme dosyaları Write aracıyla yazılır |
| 51 | Çok parçalı yükleme uca ulaşmadan geçici klasöre tamamen yazılıyor; dosya başına sınır geç kalıyor, disk dolunca anlaşılmaz hata | `api/limits.py` ara katmanı: `Content-Length` sınırı (`max_request_mb`) ve disk alanı gövde okunmadan denetlenir (413/507); chunked gövde sayılır; yazarken ENOSPC → `DiskFullError` |
| 52 | **Akıllı Uygulama Denetimi (SAC) indirilmiş imzasız .exe'yi engeller** (ölçüldü: aynı imzasız .exe MOTW'siz çalıştı, `Zone.Identifier` ZoneId=3 ile "Uygulama Denetimi ilkesi bu dosyayı engelledi", CodeIntegrity 3077). PyInstaller çıktısı ve Inno Setup kurulum dosyası imzasız olur; arkadaşın indirdiği hâliyle açılmaz | Paket hiç kendi .exe'sini içermez: python.org'un imzalı gömülü Python'u + `.py` + `.cmd` + `.lnk`. MOTW'li `.cmd` ve `-File` ile çağrılan `.ps1` çalıştı; MOTW'li imzasız PyPI `.pyd` (Pillow) yüklendi. Kurulum `shutil` ile kopyalar: `Zone.Identifier` akışı kopyaya geçmez |
| 53 | uv'nin sanal ortamındaki `python.exe` bir yönlendirici: asıl süreç sistem Python'u (`C:\Program Files\Python311`) | Paket kendi gömülü Python'unu taşır; kullanıcıda Python gerekmez |
| 54 | Edge `--app` penceresine `Process.CloseMainWindow()` yanlış pencereye gidiyor (pencere kapanmıyor sanıldı) | Doğru pencereye `WM_CLOSE` gidince bütün profil süreçleri 1 sn'de kapanıyor ve başlatılan `msedge` süreci çıkıyor: uygulama o sürecin çıkışını bekler |
| 55 | ctypes'ta `argtypes` verilmeyen Win32 çağrısı 64-bit tutamakta `OverflowError` verir (`SetInformationJobObject`) | İş nesnesi çağrılarının imzaları açıkça verilir |
| 56 | CI'da paket betiği ilk `print`'te ("→", "ö") cp1252 yüzünden çöktü; hata yakalayıcısı da aynı yüzden çöktüğü için CI'da yalnızca "exit code 1" görünüyordu (günlükler kimliksiz okunamıyor) | Betik stdout/stderr'i UTF-8'e çevirir; hata `::error::` annotation'ı olarak yazılır, kimliksiz `check-runs/{id}/annotations` API'sinden okunur |
| 57 | `pwsh` (PowerShell 7) içinden çağrılan `powershell.exe` (5.1) devraldığı `PSModulePath` ile `Get-AuthenticodeSignature`'ı yükleyemiyor, boş dönüyor | Alt süreçte `PSModulePath` silinir (paket betiği ve kurulumun kısayol adımı) |
| 58 | Testte `settings.default_data_dir`'i yamamak yetmez: `Settings.data_dir` alanının `default_factory`'si özgün fonksiyonu tutar; kaldırma testi gerçek veri klasörünü silebilirdi (otomatik denetim durdurdu) | `uninstall(data_dir=...)` açık parametre; testler ayrıca `LOCALAPPDATA`'yı geçici klasöre çevirir ve silinecek yolun geçici klasörde olduğunu doğrular |
| 59 | **Markdown önizlemesi her güncellemede başa atlıyordu**: `srcdoc` değişince çerçeve yeniden yüklenir (ölçüldü: 5657 px → 0) | Belgenin "kabuğu" (CSS, makrolar, yön; nonce'lar hariç) aynıysa yalnızca gövde yerinde değişir, formüller çerçevenin kendi `__paRender`'ıyla çizilir; kabuk değişince yeniden yüklenir ve kaydırma oranı KaTeX bitince geri verilir (`mdpreview.ts`, `PreviewFrame`) |
| 60 | Önizleme yanıtları sırasız gelebilir: yavaş eski yanıt yenisinin üstüne yazıyordu | Her istek sıra numarası taşır, yalnızca en sonuncunun yanıtı gösterilir (testte eski yanıt `page.route` ile bekletilip sonra verilir) |
| 61 | Yerinde güncelleme `innerHTML` kullanır: notun betikleri çalışır mı? | `<script>` `innerHTML` ile hiç çalışmaz; `onerror=` gibi satır içi işleyiciler çerçevenin CSP'si (`'unsafe-inline'` yok) yüzünden engellenir; testli |
| 62 | Port değişince arayüz yeni sunucuyu (başka köken) okuyamaz: CORS yok, `Cross-Origin-Resource-Policy: same-origin` `no-cors` yoklamasını da engeller; **uygulamanın kendi CSP'si (`connect-src 'self'`) yoklamayı hiç göndermiyordu** (kurulu paket denemesinde bulundu: sunucu 0,5 sn'de yeni portta açıldı, pencere eski adreste kaldı) | `/api/health` köken dışına `cross-origin` CORP ile açılır (içerik yine okunamaz); `connect-src` yalnızca `http://127.0.0.1:*` kadar genişler (testli); aynı portta yeni sunucu `instance` kimliğinden anlaşılır; uçtan uca test gerçek `desktop.run` + düğmeyle |
| 63 | dnd-kit'in klavye sensörü Boşluk/Enter'ı "sürüklemeyi başlat" sayar; çoklu seçimle çakışır, ızgara klavyeyle seçilemiyordu | Klavye sensörü kaldırıldı; ızgara `listbox` (tek sekme durağı), Boşluk seçer, `Alt+ok` taşır; dnd-kit'in `role="button"`/`aria-roledescription`'ı ezilir |
| 64 | `Alt+←` tarayıcıda "geri"dir; sayfa taşırken uygulama geri gidebilirdi | `keydown`'da `preventDefault` (testte adres değişmiyor) |
| 65 | `<dialog>` React tarafından kaldırılınca (× düğmesi) odak `body`'ye düşüyordu | `Modal` açıldığında odaktaki öğeyi hatırlar, kapanınca geri verir |
| 66 | Sayfa düzenleyicide `Ctrl+R` döndürme kısayoluna takılıyor, sayfayı yenilemiyordu | `R` yalnızca değiştiricisizken döndürür |
| 68 | **Sayfa düzenleyiciye sınırdan büyük dosya bırakınca hiçbir şey olmuyordu** (arkadaş denemesi, 2 GB): sunucu reddediyordu ama boş düzenleyici ekranı yükleme hatasını göstermiyordu | `useUpload({ toastErrors: true })`: hatayı kendisi göstermeyen ekranlarda (düzenleyici, içerik ekle) bildirim; e2e testli |
| 69 | **pdf.js büyük dosyanın tamamını arka planda tarayıcıya çekiyordu** (2 GB'lık dosyada 15 sn'de 578 MB, sürüyordu; 8 GB'ta tarayıcı belleği biterdi) | `disableAutoFetch` + `disableStream`: yalnızca çizilen sayfaların baytları aralık isteğiyle (Starlette `FileResponse` `Range` destekler); ekran durunca indirme durur |
| 70 | pdf.js açılışta son sayfayı doğrulamak için bütün sayfa nesnelerini okur; bu nesneler resimlerin arasına dağılmıştır. 1 MB'lık `rangeChunkSize` ile her küçük nesne 1 MB indirme demekti (400 sayfalık dosyanın %72'si çekildi) | Parça boyutu varsayılanda (64 KB); büyük resim bitişik parçalar birleştirilerek yine tek istekte gelir |
| 71 | Playwright `requestfinished` akışla gelen ya da yarıda kesilen isteği saymaz: "dosyanın tamamı çekiliyor mu" testi eski kodda da geçiyordu | Baytlar CDP `Network.dataReceived` ile sayılır (eski arayüzde 107 MB'lık dosya için 132 MB ölçüldü, test kırmızı) |
| 72 | **"Güçlü" sıkıştırma dakikalarca ilerlemesiz sürüyordu** (248 MB pafta: PyMuPDF 27 sn + Ghostscript 130 sn, Ghostscript yalnızca %4 daha küçük) | PyMuPDF sonucu orijinalin %40'ının altındaysa Ghostscript atlanır (158 → 28 sn); çalışırsa `proc.run_lines` ile "Page N" satırları sayfa sayfa ilerleme olur; iş panelinde geçen süre |
| 73 | Metin ağırlıklı PDF'te sıkıştırma ~%10–20 kazandırıyordu: yazı tipleri tam gömülü kalıyordu | Her seviyede `subset_fonts` (kayıpsız; metin birebir aynı, testli): örnek 1,20 → 0,46 MB. Az kazançta nedeni söylenir ("dosyanın %0'ı resim...") |
| 74 | Linux'ta `Path("..\a.pdf").name` ters eğik çizgiyi adın parçası sayar: yüklenen ad `_.._kötü.md` oluyordu | `pdfio.base_name` (`PureWindowsPath`): iki ayırıcı her platformda |
| 75 | Gerçek Ctrl+R bazı başsız tarayıcı sürümlerinde sayfayı yeniliyor: klavye e2e testi CI'da aralıklı düşüyordu | Kısayol testi olayı `dispatch_event` ile gönderir |
| 76 | GitHub `::error` komutu satır başında olmalı (pytest ilerleme satırı satır sonsuz biter), özellikte `:` kaçırılmalı; adım başına en fazla 10 açıklama gösterilir | `conftest.py`: komuttan önce satır sonu, `%3A`; ilk 8 hata ayrıntılı, sonda "N test düştü" özeti |
| 77 | PyMuPDF `Table.extract()` harf kutularını kesin (glyph) ölçüyle alır: nokta/virgül satır çizgisinde kaldığı için ayrı satır sayılır, kelime arası boşluk kaybolur ("1.250,50" → "125050\n. ,", tarayıcı çıktısında da) | `to_excel._cell_text`: hücre sınırı tablodan, metin `get_text("words")` kelimelerinden (merkezi hücrede olanlar) |
| 78 | PyMuPDF 2'de `find_tables` varsayılan olarak her sayfada onnx sayfa düzeni modelini çalıştırır (~0,7 sn/sayfa; 100 sayfalık döküm 90 sn) | `use_layout=False` (~0,05 sn/sayfa; 7,5 sn) + çizgisizde hizaya göre arama; tek hücreli çerçeve elenir (≥ 2 × 2) |
| 79 | pdf2docx içe aktarılırken kök günlükleyiciye `basicConfig` uygular ve her sayfada köke yazar ("Ignore Line ... due to overlap"); `Converter.convert` ilerleme vermez, iptal edilemez, sayfa hatasını yutar | `to_word._import_pdf2docx`: kök eski hâline, pdf2docx kayıtları süzülür; dört aşama sayfa sayfa yürütülür (ilerleme + iptal), atlanan sayfa uyarı olur. İç yapıya bağlı: `pdf2docx<0.6` |
| 80 | openpyxl "=" ile başlayan yazıyı formül yapar: PDF'teki metin Excel'de formül olarak çalışırdı (`=HYPERLINK(...)`) | Hücre `data_type = "s"`; test xlsx içinde `<f>` olmadığını denetler |
| 81 | Esc'te `<dialog>` hemen kapanır, `close` olayı sonraki görevde gelir: Modal kaldırılırken odağı açan öğeye *yeniden* veriyordu; arada oklarla geçilen sayfadan odak geri çekiliyor, klavye e2e testi CI'da (iki işletim sisteminde) düşüyordu, yerelde 20× yavaşlatmada bile geçiyordu | Modal odağı yalnızca kaybolduysa (gövdede ya da kaldırılan pencerede) geri verir; test kapatma + başka öğeye odağı aynı görevde yapar (eski kodda kırmızı). CI açıklamasına düşen testin teardown çıktısı (tarayıcı sürümü, konsol) da yazılır |
| 67 | Python `Path.write_text` Windows'ta `\n`'i `\r\n` yazar: betikle düzenlenen kaynaklar CRLF'e döndü (git uyarısı) | Düzenleme betikleri `newline="\n"` ile yazar |

**Faz D3 notları (Linux)**: Masaüstü paketi yalnızca Windows; Linux'ta kaynak koddan çalışır ve CI'da `linux` işi (ubuntu-latest; LibreOffice, Tesseract + Türkçe, Ghostscript apt ile; tarayıcı Google Chrome) bütün testleri koşar. Tarayıcı Linux'ta PATH'te aranır (Edge, Chrome, Chromium); kurulum ipuçları platforma göre (apt); Windows'a özgü düğmeler (Klasör seç, Klasörde göster, LibreOffice'i kur) yalnızca Windows'ta. Testler platformdan bağımsız: Arial yoksa fixture'lar Noto kullanır, Windows'a özgü testler atlanır. İlk Linux koşusunda düşen 10+ testin hepsi test varsayımıydı, bir tanesi gerçek uyumsuzluk (tuzak #74).

**Faz D2 notları (arkadaş denemesi: büyük dosyalar ve sıkıştırma)**: Şehir/bölge planlama öğrencisi bir arkadaşın denemesinden dört madde geldi; hepsi ölçülerek kapatıldı (tuzak #68–#73). Dosya başına sınır 1 GB → **8 GB** (toplam 16 GB); yükleme akışla, bellek kullanmadan yazılır, disk alanı önceden denetlenir. Ölçümler (bu makine, başsız Edge): 2,0 GB / 150 sayfalık PDF 10–35 sn'de yüklenir (disk önbelleğine göre), ilk küçük resim 3 sn; 7,8 GB / 594 sayfa 47–120 sn'de yüklenir, ilk küçük resim 8–13 sn; ekran durunca tarayıcı yalnızca görünen sayfaların baytlarını tutar (2 GB'ta 648 MB = 48 sayfanın 13'er MB'lık resmi). Sıkıştırma: yazı tipi alt kümesi her seviyede; güçlü seviyede Ghostscript yalnızca işe yarayacakken; ilerleme ve geçen süre görünür; az kazançta neden açıklanır. Bilinçli kalanlar: çok büyük sayfa resimleri (A0 pafta, 100 MP) küçük resim için tarayıcıda tam çözülür, sunucuda küçük resim üretmek sonraki iyileştirme adayı; `rewrite_images` tek uzun çağrıdır, kendi içinde ilerleme vermez (iş panelinde "birkaç dakika sürebilir" + geçen süre).

**Faz D notları (ürün deneyimi)**: Ayarlar ekrandan değişir (`PUT /api/settings`, yalnızca bu bilgisayardan): saklama süresi, Obsidian kasası (Windows'un klasör seçme penceresi, `native.pick_folder`; göreli yol, olmayan klasör ve sürücü kökü reddedilir), Markdown için varsayılan tema/kağıt (katman sırası: yerleşik < Ayarlar < ön bilgi < ekran seçimi; CLI de uygular), port ve telefon modu. Yazılan dosya okunan `config.toml`, yoksa veri klasöründeki (`settings_file`); dosyadaki diğer ayarlar korunur, BOM'lu dosya okunur, açıklamalar kaybolur (örnek dosyada yazıyor). Saklama süresi temizlik döngüsünde her turda okunur. Port ve telefon modu yeniden başlatma ister: masaüstü uygulamasında "Şimdi yeniden başlat" sunucuyu kapatıp yeni ayarlarla açar, pencere açık kalır ve arayüz yeni adrese geçer (`desktop._Server`, `restart.ts`; istenen port doluysa eski porta dönülür); `serve`'de "baslat.bat ile yeniden aç" denir. Masaüstü uygulaması artık telefon modunu açabilir (0.0.0.0; pencere 127.0.0.1'de); açıkken üst çubukta "Telefon modu açık". Geliştirici bilgileri (port, yollar, motor yolları, kütüphaneler) "Gelişmiş" altında. İlk açılış: kısa tanıtım + eksik motorlar ve ne yapılacağı (LibreOffice'i kur düğmesi), `welcome_done` ayara yazılır, Ayarlar'dan yeniden gösterilir. Hata sınırı: ekran çökerse beyaz sayfa yerine açıklama, hata kimliği (`/api/client-error` → günlük), "Yeniden dene"; gezinme çalışır, başka ekrana geçince sıfırlanır. Genel bildirim (`toast.ts`): kaydetme, yeniden adlandırma, silme, yakalanmamış söz hataları. İşler: bütün iş türleri Türkçe (tek kaynak `labels.ts`, kapsamı pytest denetler), satır içi yeniden adlandırma (uzantı korunur), "Klasörde göster" (yalnızca bu bilgisayarda: kopya gerçek adıyla `Dışa aktarılanlar/<id>/` altına, depodaki sürüm dosyalarına dokunulmaz, silinen dosyaların kopyaları temizlenir); dar ekranda dosya tablosu kart düzeni. Erişilebilirlik: atlama bağlantısı, ekran değişince odak içeriğe ve sekme başlığı, `aria-current`, sayfa düzenleyici klavyeyle tam kullanılır (oklar, Boşluk, Shift/Ctrl, Alt+ok, Enter; işlemler canlı bölgede duyurulur, silmeden sonra odak yerinde), modal odağı geri verir. Ana sayfadaki "Faz N" kalıntısı (`tools.ts` `phase`) kaldırıldı. Arayüz testleri: vitest (jsdom; düzenleyici modeli, yönlendirici, taslaklar, şifreler, düzenleyici klavyesi, önizleme, bildirimler — 37 test) ve eslint (TypeScript + React kancaları, uyarısız); ikisi de CI'da. Lisans: AGPL-3.0 (`LICENSE`, `pyproject.toml`, pakette `LICENSE.txt`).
Doğrulama: yeni uçtan uca testlerin hepsi eski arayüz (main'deki `web/src` ayrı çalışma ağacında derlenip) ile çalıştırıldı ve kırmızıya döndü — kaydırma testi 5657 → 0 px, sırasız yanıt testi eski metni gösterdi, hata sınırı testi beyaz sayfa; yeni arayüzle yeşil. 1400 ve 390 px ekran görüntüleri (tanıtım, ana sayfa, ayarlar, gelişmiş, işler, düzenleyici, Markdown, hata sınırı) alındı, yatay taşma yok (ayrıca testli). Paket yeniden üretildi (`--yerel-ortam`, 257 MB, `LICENSE.txt` içinde) ve `LOCALAPPDATA` geçici klasöre çevrilerek kısayolsuz kuruldu (9 sn); kurulu Python'la masaüstü uygulaması (pencere yerine sahte pencere) başsız Edge'le sürüldü: tanıtım, Ayarlar'da port değişikliği + "Şimdi yeniden başlat" (0,8 sn'de yeni porta geçti, eski port kapandı), Markdown → PDF, klavyeyle döndür + kaydet, İşler'de Türkçe adlar, 390 px'te taşma yok; kapanışta öksüz süreç kalmadı. Bu deneme tuzak #62'deki CSP hatasını buldu (düzeltildi, uçtan uca testli).

**Faz C notları (paket)**: Önce bu makinede SAC açıkken ölçüldü (tuzak #52): imzasız ve indirilmiş (.exe + MOTW) dosya engelleniyor; imzalı python.org Python'u, PyPI tekerlekleri ve betikler çalışıyor. Bu yüzden PyInstaller / Inno Setup yerine: `paket/derle.py` → `build/PdfAtolyesi-<sürüm>.zip` = imzalı gömülü Python 3.11.9 (imzası derlemede doğrulanır) + `uv export` ile kilit dosyasındaki çalışma bağımlılıkları + pdfatolye tekerleği + derlenmiş arayüz (`pdfatolye/web`) + Tesseract (yalnızca `tesseract.exe`'nin PE içe aktarma kapanışındaki 26 DLL; tur, eng, osd) + Ghostscript + Noto fontları. `Kur.cmd` → `python -m pdfatolye.kurulum kur`: `%LOCALAPPDATA%\Programs\PdfAtolyesi`, masaüstü/Başlat/Gönder kısayolları, "Uygulamalar"da kaldırma kaydı; yönetici izni yok. Uygulama: `pythonw -m pdfatolye uygulama` = sunucu (port doluysa boş port) + Edge `--app` penceresi (ayrı profil `pencere-profili`), pencere kapanınca sunucu kapanır, `calisiyor.json` + `/api/health` ile tek örnek, süreç "kapanınca öldür" iş nesnesinde (zorla kapatılsa da LibreOffice/OCR/Edge öksüz kalmaz; testli, iş nesnesi olmadan alt sürecin yaşadığı ayrıca görüldü). Kod proje klasörüne bağlı değil (`paths.py`): arayüz ve fontlar paketin içinde, kurulum kökü işaret dosyasıyla bulunur, depo kökündeki `config.toml` yalnızca geliştirmede aranır. Editörün varsayılan fontu Noto Sans (Windows fontları varsa ek seçenek). LibreOffice pakete girmedi: Ayarlar ve Office ekranında onaylı "LibreOffice'i kur" (winget; yalnızca bu bilgisayardan istenebilir). Güncelleme: kullanıcı isterse GitHub Releases'e tek GET; yeni paket eskisinin üzerine kurulur, veri klasörü ayrı. Sürüm tek kaynak `pyproject.toml` (`__version__` paket meta verisinden, `web/package.json` testle eşit), 0.9.0. CI motorsuz paketi üretip kendi Python'uyla dener ve artifact yükler.
Doğrulama (bu makinede, SAC açık): paket (257 MB zip, açık 636 MB) indirilmiş gibi işaretlenip (7032 dosyaya Zone.Identifier) açıldı; uv/node/Python'suz PATH'le `Kur.cmd` 12 sn'de kurdu, kurulu `python.exe`'de MOTW yok; uygulama penceresi açıldı (kurulu `pythonw` + Edge `--app`); kurulu uygulamaya gerçek işler: sayfa düzenleme, MD→PDF (Türkçe), gömülü Tesseract'la Türkçe OCR, Office→PDF (sistemdeki LibreOffice), gömülü Ghostscript'le güçlü sıkıştırma; 1400/390 px ekranlarda taşma yok; pencere kapatılınca sunucu 1 sn'de kapandı, süreç ve kilit kalmadı; `Kaldir.cmd` kısayolları, kaldırma kaydını, kurulum klasörünü ve (onaylanınca) veriyi sildi. Denemede bulunup düzeltilen (testli): BOM'lu `config.toml` uygulamayı açtırmıyordu; kurulum çıktısı boruya giderken "→" cp1252'de çöküyordu. Yerel paket bu makinenin yavaş PyPI bağlantısı yüzünden `--yerel-ortam` ile (kilitle eşit `.venv`'den, aynı sürümler) üretildi; normal yol (ağdan) CI'da çalışıyor. Bilinçli bırakılanlar: Telefon modu metni hâlâ `baslat.bat --lan` diyor ve masaüstü uygulaması telefon modunu açmıyor (Faz D: düzenlenebilir ayarlar); uygulamanın kendi .exe'si yok, görev çubuğunda Edge simgesi görünebilir.

**Faz B notları (sağlamlık)**: Denetimde çalıştırılarak bulunan 13 madde kapatıldı; her biri `tests/test_robustness.py` ya da `tests/e2e/test_ui.py`'de testli. Her düzeltme kod değiştirilmeden (arka uçta bir pytest eklentisiyle monkeypatch, arayüzde eski `web/src` derlenerek) geri alındı ve ilgili testin kırmızıya döndüğü görüldü; bu yöntem iki zayıf testi yakaladı (`compose` iptali ve küçük resim testi düzeltme olmadan da geçiyordu, sıkılaştırıldı). Dosya türleri tek kaynakta (`formats.py`), arayüzün kabul listesi testle ona bağlı (CSV, `.docm/.xlsm/.pptm`, `.wpd`). Sayfa düzenleme/birleştirme başlık, yazar, XMP, sayfa etiketleri (sıralandıktan sonra da doğru) ve gömülü dosyaları taşır; birleştirmede belge bilgisi ilk dosyadan. İş kayıtlarına not metni yazılmaz, yanıtlar büyük istek alanlarını taşımaz, kayıtlar saklama süresiyle silinir (en fazla 200). İptal: sırada bekleyen hemen, çalışan iş alt süreç ağacı öldürülerek birkaç saniyede; sayfa düzenleme her parçadan sonra denetler; PyMuPDF'in tek uzun çağrıları (sıkıştırmada `rewrite_images`) kesilemez, bittiğinde iptal edilir. Temizlik, bir işin kullandığı (sıradakiler dahil) ve arayüzde açık dosyayı silmez (açık ekran 10 dakikada bir yoklar). Metin kod çözümü sunucuda tek yerde (`core/textio.py`, `/api/files/{id}/text`). Markdown ekranı: kaydedilmemiş değişiklik uyarısı, taslak tarayıcının yerel deposunda, "Notu indir (.md)". Kapanış koruması `JobManager.shutdown` ile; sunucu süreci zorla öldürülürse (Görev Yöneticisi) alt süreçler için Faz C'deki iş nesnesi (Job Object) gerekir.

**Faz A notları (güven)**: Denetimde çalıştırılarak bulunan açıklar kapatıldı; her biri `tests/test_trust.py`'de testli, en riskli dört koruma bilerek kapatılıp testlerin başarısız olduğu doğrulandı. Karartma açıklama ve form alanlarını da siler, başka yerde geçen metni uyarır. Şifreli dosya düzenlenince şifresi korunur (web ve CLI). Web'den gelen notun resmi yalnızca not klasöründen ve kasadan okunur (`confine`), önizleme resimleri artık oturum ister; CLI'da göreli `../` serbest ama yalnızca resim uzantıları çözülür. Baskıda ağ kapalı, yalnızca belgenin kendi dosyaları açılır; Markdown'da CSP notun betiklerini de durdurur, HTML'de betik çalışır ama dışarı çıkamaz. LibreOffice uzak resim bağlantısını varsayılan olarak çekmiyor (testli). Telefon modu: tek kullanımlık QR, cihaz başına oturum, kesme. API belgeleri kapalı. Bilinçli kalanlar: telefon modu HTTP; karartılmamış önceki sürüm depoda durur (söylenir).

**Faz 7 notları**: Beklenmeyen hatalar (iş ya da HTTP 500) 8 haneli **hata kimliği**yle kullanıcıya kısa, günlüğe ayrıntılı (yığın izi) yazılır. **Telefon modu** (`--lan` / `lan = true`): sunucu 0.0.0.0'da dinler, yerel ağ IP'leri izinli Host listesine eklenir; oturum çerezi yalnızca loopback'ten gelen isteğe ya da QR koddaki eşleştirme belirteciyle (`/?t=...`, oturum çerezinden ayrı) gelen cihaza verilir, ardından adres çubuğundan belirteç silinir (303). QR yalnızca bilgisayarda gösterilir (`/api/lan` loopback dışına kapalı). **Gönder → PDF'e çevir**: `gonder` komutu dosyaları türüne göre `md` / `resimden` / `cevir`'e dağıtır; `pdfe-cevir.bat` + `kurulum\kisayollar.ps1` (BOM'lu UTF-8, PowerShell 5.1 için) masaüstü ve SendTo kısayollarını kullanıcı klasörüne yazar. **E2E**: `tests/e2e` gerçek sunucuyu iş parçacığında, Edge'i başsız açar: yükle → sil → kaydet, editörde döndürülmüş sayfaya Türkçe yazı, ayarlar/araçlar. Sistem tepsisi simgesi ve PyInstaller paketi yapılmadı (isteğe bağlıydı; `baslat.bat` + kısayol yeterli görüldü).

**Faz 6 notları**: Sıkıştırma PyMuPDF `rewrite_images` + `garbage=4`/nesne akışlarıyla; "güçlü" seviyede Ghostscript `/ebook` da denenir, küçük olan alınır; sonuç büyükse orijinal kopyalanır. Şifreleme pikepdf ile AES-256 (R6); şifreler iş kaydına yazılmaz (`exclude`). Meta temizliği docinfo, XMP, gömülü dosyalar, belge/açılış JavaScript'i ve sayfa PieceInfo'yu siler. Onarım önce qpdf, olmazsa MuPDF. OCR `--skip-text --deskew --rotate-pages`, `output_type=pdf` (PDF/A değil: daha hızlı, Ghostscript'e bağımlı değil), `optimize=1`; şifreli girdi önce şifresiz geçici kopyaya çevrilir. Sayfa düzenleyici metni olmayan PDF'te "OCR ile aranabilir yap" önerir; "bozuk olabilir" hatası veren işte "Onarmayı dene" bağlantısı çıkar.

**Faz 5 notları**: Editör (`#/editor/<id>`) nesneleri tarayıcıda Konva ile tutar, "Uygula" `apply` işine işlem listesi gönderir; koordinatlar görünüm uzayında (döndürme + CropBox uygulanmış sayfa, sol üst köşe, nokta). Fontlar şimdilik Windows'tan (Segoe UI, Arial, Calibri, Times New Roman, Georgia, Consolas); `assets/fonts/` klasörüne aynı dosya adıyla konan TTF önceliklidir. Karartma `apply_redactions` ile yazıyı, resim piksellerini ve tamamen kapsanan çizimleri siler; "Beyazla kapat" yalnızca yazıyı siler, üstünü boyar. Vurgu, kutunun altındaki kelimelere oturur. İmzalar sabitlenmiş PNG (`tag="signature"`), kâğıt otomatik saydamlaşır. Sayfa numarasında "ilk sayfayı atla" kapağı numarasız bırakır, numaralama ikinci sayfadan başlangıç değeriyle sürer.

**Faz 4 notları**: `cevir` komutu ve "Office → PDF" ekranı Word/Excel/PowerPoint/ODT/RTF'yi LibreOffice ile, HTML ve TXT'yi tarayıcıyla çevirir. Eksik font kontrolü: belgede istenen ama hem PDF'e gömülmemiş hem de Windows'ta kurulu olmayan fontlar uyarılır (ör. yeni Office varsayılanı Aptos). HTML dosyasının göreli resimleri arayüzden yüklenince bulunamaz (tek dosya yüklenir); kendine yeten HTML önerilir.

**Faz 3 notları**: Arayüz dosya yolu görmez/göndermez; her şey depo kimliğiyle (32 hex) gider. Şifreler yalnızca sekmenin belleğinde tutulur ve iş kaydına yazılmaz. Sayfa düzenleyicide geri/ileri tarayıcıda, "Kaydet" sunucuda yeni sürüm oluşturur; "Önceki sürüme dön" sunucudaki sürümü geri alır.

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

### 10.1 Ürünleşme yol haritası

**Hedef**: Windows masaüstü uygulaması. İlk kitle: geliştirici ve arkadaşları; tek düğmeyle kurulup çalışacak. Para kazanma kararı sonraya bırakıldı. İlk sürüm: Türkçe, yeni büyük özellik yok. Çekirdek, API ve arayüz yeniden yazılmaz; masaüstü üstüne bir paketleme katmanıdır.

- **Faz A — Güven** ✅: karartma, şifre koruması, izin kısıtları, disk erişimi, ağ yalıtımı, güvenlik başlıkları, telefon modu, CI.
- **Faz B — Sağlamlık** ✅: uzun dosya adında uzantı kaybı; uygulama içi gezinmede kaydedilmemiş iş kaybı; geri al + kaydet sonrası eski küçük resim; bozuk `meta.json`'ın listeyi ve temizliği durdurması; iş kayıtlarındaki not metni ve kayıtların temizlenmemesi; sayfa düzenlemede başlık/yazar/etiket/gömülü dosya kaybı; CSV ve makrolu Office türleri; gerçek iptal ve kuyruk; açık dosyanın temizlikte silinmesi; Windows-1254 notlar; HTML baskısında sonsuz döngüye zaman aşımı.
- **Faz C — Paket** ✅: hazır arayüz, kurulum programı, uygulama penceresi, gömülü Tesseract + Türkçe paket ve Noto fontları, isteğe bağlı LibreOffice, kodu proje klasörüne bağlayan yerler (`settings.PROJECT_ROOT`, `WEB_DIST`, `fonts`), imzalama, güncelleme.
- **Faz D — Ürün deneyimi** ✅: düzenlenebilir ayarlar (masaüstünde yeniden başlatma, telefon modu), ilk kullanım akışı, hata sınırı + bildirimler, önizleme kaydırma konumu ve sırasız yanıtlar, işlerde Türkçe adlar, yeniden adlandırma, klasörde göster, klavye ve ekran okuyucu erişilebilirliği, vitest + eslint (CI), AGPL-3.0 LICENSE.
- **Faz E — Yayın**: gizlilik metni, CHANGELOG, sürümleme (1.0.0), GitHub Releases, tanıtım sayfası. (LICENSE Faz D'de eklendi.)
- **Faz F — PDF'ten Office'e ve büyük kağıt** ✅: PDF → Word (`convert/to_word.py`, pdf2docx; sayfa sayfa ilerleme ve iptal), PDF → Excel (`convert/to_excel.py`, PyMuPDF `find_tables` + openpyxl; çizgisiz tablo, sayfalara bölünmüş tabloyu birleştirme, TR/EN sayı biçimi, "=..." hücresi yazı), kağıt boyutları tek kaynak `core/paper.py` (A0–A5, Letter, Legal; arayüz `tools.ts` PAPERS, test denetler), PDF → Resim sınırı A0 @ 300 DPI.

### 10.2 Kullanıcı kararı bekleyenler

Bu kararlar verilene kadar yapılan, maddede yazılı; hiçbiri ücretli bir şey satın almayı ya da hesap açmayı gerektirmeden ilerlemeyi durdurmaz.

1. **Kod imzalama** (Kur.cmd'nin ve ileride bir .exe/.msi'nin "bilinmeyen yayımcı" uyarısı, SAC).
   - *a) İmzasız devam* (şu an): paket kendi .exe'sini taşımaz, SAC açıkken de çalışır; arkadaş "Daha fazla bilgi → Yine de çalıştır" der. Maliyet yok.
   - *b) Azure Trusted Signing* (Microsoft'un bulut imzası; aylık abonelik, kimlik doğrulaması bireysel geliştirici için ülke/koşullara bağlı): SmartScreen itibarı ve SAC için en kolay yol; tek .exe kurulum programı (Inno Setup) mümkün olur.
   - *c) OV/EV kod imzalama sertifikası* (yıllık ücret, donanım anahtarı): aynı sonuç, daha pahalı.
   - *d) Microsoft Store (MSIX)*: Store imzalar; geliştirici hesabı ve paketleme işi gerekir.
   - **Karar (2026-11-07): a) imzasız devam.** Dağıtım genişlerse yeniden bakılır.
2. **Lisans** — **Karar (2026-11-07): AGPL-3.0.** `LICENSE` eklendi, `pyproject.toml`'da `AGPL-3.0-only`, pakette `LICENSE.txt`. ("or-later" istenirse yalnızca SPDX ifadesi değişir.)
3. **Yayın (GitHub Releases)**: **0.9.1** hazırlandı (arkadaş denemesi sonrası; 0.9.0 kurulu olanlar "Güncellemeleri denetle" ile görsün diye numara artırıldı). `v0.9.1` etiketi gönderildi, değişiklikler `CHANGELOG.md`'de; Release'i oluşturup `build/PdfAtolyesi-0.9.1.zip`'i yüklemek depo sahibinin tarayıcıdan yapacağı iş (kimlik bilgisi gerektirir). İstenirse CI'a etiketle tetiklenen bir yayın işi eklenebilir (motorsuz paket CI'da üretilebiliyor; OCR'lı tam paket için Tesseract/Ghostscript'in CI'da kurulması gerekir).
4. **Ghostscript'i pakette tutmak** (+~40 MB, AGPL): şu an pakette (OCR ve güçlü sıkıştırma için). Alternatif: çıkarıp OCR'ı Ghostscript'siz yapılandırmak (OCRmyPDF sürümüne bağlı, denenmedi).
5. **1.0.0 sürüm numarası**: şimdilik 0.9.1. 1.0.0'ı arkadaş denemesi 0.9.1 ile sorunsuz geçtikten sonra vermeni öneririm.

### Sonraki sürüm adayları
Form doldurma (AcroForm alanları), iki PDF'i karşılaştırma, not gömme (`![[Not]]`), Pandoc/LaTeX alternatif MD motoru, PDF/A doğrulama, İngilizce arayüz.

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
- `config.toml` ile tüm ayarlar (port 8790, veri klasörü, saklama 24 saat, maks. yükleme 8 GB, motor yolları, kasa yolu).
