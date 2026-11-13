# PDF Atölyesi — Kapsamlı Kod İncelemesi, Hata Analizi ve Geliştirme Planı (v0.10.0)

> **İnceleme Tarihi:** 2026-11-13  
> **İncelenen Sürüm:** `0.10.0` (`pyproject.toml`, `SONRAKI_OTURUM.md`, `PLAN.md`)  
> **Kapsam:** `src/pdfatolye/` (core, convert, api, jobs, cli, desktop, kurulum), `web/src/` (React + TS + Konva + pdf.js), `paket/`, `kurulum/`, `tests/` ve `.github/workflows/ci.yml`  
> **İnceleme Yöntemi:** 4 ayrı salt-okunur denetim alt ajanı ile tüm kaynak dosyaların satır satır taranması. Mevcut `PLAN.md` §8'de zaten kapatılmış olan **81 tuzak** tekrar sayılmamış; yalnızca kodda **hâlâ açık olan** hatalar, çökme (crash) riskleri, yarış durumları, eksiklikler ve hızlandırma fırsatları raporlanmıştır.

---

## 1. Yönetici Özeti ve Mevcut Mimari Değerlendirmesi

PDF Atölyesi (`0.10.0`), başlangıçtaki "ders notu MD → PDF" hedefinin çok ötesine geçip **tam çevrimdışı, mahremiyet odaklı, Windows Smart App Control (SAC) uyumlu bir yerel PDF araç setine** dönüşmüş durumda.

- **Güçlü Yanları:**
  - Çekirdek iş mantığı (`core/`, `convert/`) arayüzden tamamen bağımsız; hem FastAPI hem Typer CLI aynı fonksiyonları çağırıyor.
  - Güvenlik katmanı (`TrustedHostMiddleware`, `SessionGuard`, `SameSite=Strict`, tek kullanımlık LAN QR eşleşmesi, ölü vekilli `OfflineBrowser`, `SANDBOX_CSP`, Excel formül enjeksiyonu koruması, gerçek `apply_redactions`) pek çok ticari masaüstü aracından daha titiz kurgulanmış.
  - Windows gerçekleri (SAC imzasız `.exe` engeli → imzalı gömülü Python, FontTools ile Türkçe font alt-kümeleme, döndürülmüş + kaydırılmış `CropBox` matematiği, Job Object ile öksüz süreç temizliği) derinlemesine çözülmüş.
- **Zayıf / Kırılgan Yanları:**
  - **Eşzamanlılık ve Windows Dosya Kilidi (WinError 5 / 32):** `Storage` kilitsiz `meta.json` okuması, aktif işin kullandığı dosyanın API'den silinebilmesi, `content.py`'de açık `doc` üzerine kaydetme, `office.py` geçici profil silme hataları.
  - **Büyük Dosya (8 GB) ve A0 Pafta Ölçeği:** Tarayıcıda A0 pafta zoom'unda canvas boyutunun GPU/RAM sınırını aşıp sekmeyi çökertmesi (`OOM`), `ocr.py`'de `read_bytes()` ile 8 GB'ı RAM'e çekme, `pages.py:split()` içinde büyük PDF'i her sayfa için sıfırdan açma, `compress.py` ve `images.py` içindeki RAM sıçramaları.
  - **Performans Darboğazları:** Her MD/HTML baskısında Edge'in sıfırdan başlatılması (~2 sn), `pdf.js` ile istemci tarafında thumbnail üretimi, SSE döngüsünde `O(N²)` disk okuması.
  - **Ön Yüz Durum & UX Bug'ları:** Konva editörde çizgi sürüklerken `onDragMove`'un Undo yığınını patlatması, URL'den açılan şifreli PDF'lerde şifre diyaloğunun açılmaması, `api.ts` `watchJob` içinde `JSON.parse` hatası.

### Kontrol Edilip Sağlam / Temiz Bulunan Alanlar (Sorun Tespit Edilmeyenler)

Denetimde özellikle kontrol edilen ancak mimarisi sağlam ve hatasız bulunan noktalar:

1. **Ağ ve XSS Yalıtımı:** `browser.py` (`--proxy-server=http://127.0.0.1:9`, `--proxy-bypass-list=<-loopback>`) + `document.py` CSP nonce + `SANDBOX_CSP` + `pdf.js` (`isEvalSupported: false`) zinciri sağlam.
2. **Türkçe Karakter ve Font Alt-Kümeleme (`core/fonts.py`):** NBSP/boşluk çakışmasını önleyen fontTools subsetting ve gömülü Noto ailesi doğru çalışıyor.
3. **Koordinat Geometrisi (`core/geometry.py`) ve `core/ranges.py` / `core/paper.py`:** 0/90/180/270 döndürme + `CropBox` matris dönüşümleri ve `1-3, 5, 8-` aralık ayrıştırması temiz.
4. **LAN / Telefon Modu Güvenliği (`api/security.py`, `api/app.py`):** Tek kullanımlık eşleştirme belirteci + 303 yönlendirmesi + `require_local` ayrımı sağlam.
5. **Şifre Hijyeni (`web/src/passwords.ts`, `core/security.py`):** Şifrelerin diske/localStorage'a yazılmaması, AES-256 R=6 şifreleme ve kısıt varken sahip şifresinin rastgele üretilmesi doğru.
6. **Büyük Dosyalarda HTTP Range Koruması (`web/src/pdf.ts`):** `disableAutoFetch: true` ve `disableStream: true` ile yalnızca görünen sayfaların baytlarının çekilmesi aktif ve testli.
7. **Windows Job Object (`desktop.py`) ve Alt Süreç Ağacı (`proc.py`):** Ana süreç zorla kapatılsa bile alt süreçlerin ölmesi işletim sistemi seviyesinde güvence altında.
8. **Excel Formül Enjeksiyon Koruması (`convert/to_excel.py`):** Hücrelerin `data_type = "s"` olarak zorlanması güvenli.

---

## 2. Tespit Edilen Hatalar, Crash (Çökme) Riskleri ve Kod Kusurları

### 🔴 Kritik Öncelikli (Doğrudan Crash, OOM, Veri Kaybı veya Kilitlenme)

| # | Konum | Sorunun Mekanizması | Çözüm Önerisi |
|---|---|---|---|
| **K1** | `web/src/editor/PageCanvas.tsx:80-95` | **A0 Pafta / Yüksek DPI'da Tarayıcı Sekmesi Çökmesi (OOM):** A0 pafta (2384×3370 pt) %150+ zoom ve 2× `devicePixelRatio` ile `7152×10110`+ px (~72–225 MP, ~290–900 MB VRAM) canvas oluşturuyor; Chromium 16.384 px / doku sınırında sekme çöküyor (`STATUS_BREAKPOINT`). Ayrıca unmount/değişimde `canvas.width = 0` yapılmıyor. | `scale * ratio` çarpanını maksimum piksel bütçesine göre (ör. `maxSide = 4096` veya `maxPixels = 16_000_000`) kırp (clamp); cleanup içinde `canvas.width = 0; canvas.height = 0;` sıfırla. |
| **K2** | `src/pdfatolye/core/ocr.py:175` | **8 GB PDF'te `MemoryError`:** OCR çıktısı `out.write_bytes(result_pdf.read_bytes())` ile aktarılıyor. 8 GB dosya RAM'e çekilmeye çalışıldığında süreç patlar. | `compress.py:166` gibi `shutil.copyfile(result_pdf, out)` kullan. |
| **K3** | `src/pdfatolye/core/content.py:527, 576` & `pdfio.py:55-76` | **Windows Yerinde Düzenlemede `PermissionError`:** `content.apply_ops` içinde `with opened(src, password) as doc:` bloğu kapanmadan `save_pdf(doc, output)` çağrılıyor. `src == output` olduğunda (CLI `filigran`/`sayfa-no -o a.pdf`) `os.replace` açık dosya üzerinde `WinError 5` ile çöker. | `doc`'u geçici bir ara dosyaya/tampona kaydedip `with` bloğundan çıktıktan (handle kapandıktan) sonra `os.replace` yap (`pages.py` modeli gibi) veya girdiyle çıktı aynıysa önce kapat. |
| **K4** | `src/pdfatolye/storage.py:150-160, 252-270` | **Windows `meta.json` Okuma/Yazma Yarış Durumu:** `get()` `self._lock` almadan `meta.json` okur; aynı anda `_save_meta()` `tmp.replace()` yaparsa Windows `[WinError 32]` fırlatır. Üstelik `get()` `PermissionError`'ı `except (OSError, ValueError)` içinde yakalayıp sağlam dosyayı kalıcı olarak `CorruptMetaError` (404) ilan eder! | `FileStore` okuma ve yazma işlemlerinde `self._lock` (veya dosya başına `RLock`) kullan; Windows'ta geçici kilit çakışmalarına karşı kısa retry + `PermissionError`'ı bozuk meta sanma. |
| **K5** | `src/pdfatolye/storage.py:317-320` & `routes_files.py:151-155` | **Aktif İşin Kullandığı Dosyanın Silinebilmesi:** `delete()` metodu `self.in_use(file_id)` kontrolü yapmaz ve kilitsizdir. Kullanıcı çalışan bir OCR/sıkıştırma işinin dosyasını silerse iş `FileNotFoundError` ile çöker. | `delete()` içinde `self._lock` altında `if self.in_use(file_id):` kontrolü yap ve HTTP `409 Conflict` ("Dosya şu an bir işlemde kullanılıyor") döndür. |
| **K6** | `src/pdfatolye/jobs/manager.py:208-219` | **Shutdown / Kuyruk İptalinde `store.hold` Sızıntısı:** Kuyrukta bekleyen işler `cancel_futures=True` ile iptal edildiğinde `_run` hiç çalışmaz, `finally: store.release(held)` atlanır; dosyalar `_busy` sayacında kilitli kalır. | Bekleyen job iptalinde/shutdown'da `held` listesindeki dosyalar için `store.release()` garantilenmeli. |
| **K7** | `src/pdfatolye/jobs/manager.py:68-71, 133-140` & `routes_jobs.py:61-79` | **SSE Döngüsünde Kilitsiz `asdict` Çökmesi:** İş parçacığı `job.outputs` veya `job.warnings` listesini güncellerken SSE `asdict(self)` çalıştırırsa `RuntimeError: list changed size during iteration` ile SSE akışı kopar. | `job.view()` içinde `JobManager._lock` altında kopyalama (snapshot) al. |
| **K8** | `src/pdfatolye/proc.py:188-208` | **`run_lines` İçinde 30 Dakikalık Kilitlenme Riski:** `pump()` thread'i `lines.put(None)` satırına ulaşamadan hata alırsa döngü `proc.poll()` kontrolü yapmadığı için `GS_TIMEOUT_S = 1800` saniye (30 dk) kilitli kalır. | `pump()` bloğunu `try...finally: lines.put(None)` içine al ve `queue.Empty` durumunda `proc.poll() is not None` kontrolü ekle. |
| **K9** | `src/pdfatolye/convert/to_word.py:95-103` | **`pdf2docx` 2. Aşamada `try...except` Eksikliği:** 3. ve 4. aşamalarda sayfa bazlı hata yakalanırken, 2. aşamada (`RawPageFactory.create`, `raw.restore`, `raw.process_font`, `raw.parse_section`) hiç koruma yok; tek bozuk sayfa tüm dönüştürmeyi çökertir. | 2. aşamayı da sayfa bazlı `try...except Exception` içine alıp hatalı sayfayı `failed` listesine ve uyarılara ekle. |
| **K10** | `src/pdfatolye/convert/office.py:84-98, 177-184, 199` | **LibreOffice Profil Kilidi & Toplu Dönüşüm Çökmesi:** 1) `TemporaryDirectory` çıkışında kilitli LO profili `PermissionError` verir (`ignore_cleanup_errors=True` yok). 2) `convert_office_many` içinde `shutil.copyfile` ve `shutil.move` hataları tek bir dosya bozuksa bütün toplu işi durduruyor. | `TemporaryDirectory(..., ignore_cleanup_errors=True)` kullan; `copyfile` ve `shutil.move` (`PermissionError`) hatalarını dosya bazında yakalayıp yalnızca o dosyayı başarısız işaretle. |
| **K11** | `src/pdfatolye/convert/markdown/document.py:223-225` & `render.py:189-190` | **Bozuk `%` İçeren Resim Yolunda 90 sn Kilitlenme:** `KATEX_SCRIPT` içinde `decodeURI(i.getAttribute('src'))` geçersiz yüzde kodunda (`bad%80.png`) yakalanmayan `URIError` fırlatır; `window.__sonuc` tanımlanmaz ve `wait_for_function` 90 sn donup timeout'la çöker. | `decodeURI` çağrısını güvenli yardımcı fonksiyonla (`try { return decodeURI(s); } catch { return s; }`) sarmala ve tüm script gövdesini `try...catch` ile koru. |
| **K12** | `web/src/editor/PageCanvas.tsx:424-428` & `pages/Editor.tsx:124-131` | **Çizgi/Ok Tutamacı Sürüklerken Undo Yığınının Çökmesi:** `onDragMove` her piksel hareketinde `commit()` tetikliyor (saniyede 60–120 kayıt). 1 saniyelik sürükleme `slice(-99)` geçmiş sınırını doldurup önceki tüm Undo geçmişini siliyor ve sahneyi donduruyor. | `onDragMove` sırasında yalnızca geçici görsel state güncellenmeli; `commit()` yalnızca `onDragEnd` anında çağrılmalı. |
| **K13** | `web/src/pages/Merge.tsx`, `Split.tsx`, `Watermark.tsx`, `PageNumbers.tsx`, `Protect.tsx`, `Compress.tsx`, `Ocr.tsx`, `PdfToOffice.tsx` | **URL/Yönlendirmeyle Açılan Şifreli PDF'lerde Şifre Sorulmaması:** `FilePicker` şifre diyaloğu açıyor ama `?dosya=ID` ile başka ekrandan gelindiğinde `PasswordDialog` yok; iş doğrudan "Şifreli dosya" hatasıyla düşüyor. | `useFiles` veya ortak bir `useEncryptedGuard` kancasıyla şifreli dosya tespit edildiğinde tüm araç ekranlarında `PasswordDialog` göster. |

### 🟠 Orta Öncelikli (Bellek Şişmesi, Bozuk Dosya Kenar Durumları, Mantık Hataları)

| # | Konum | Sorunun Mekanizması | Çözüm Önerisi |
|---|---|---|---|
| **O1** | `src/pdfatolye/core/compress.py:97` | **`image_share` Gereksiz Bellek Tahsisi:** Resim boyutunu toplamak için `len(doc.xref_stream_raw(xref) or b"")` kullanılıyor; büyük paftalarda dev ham akışları RAM'e çeker. | Nesne sözlüğünden `/Length` değerini (`doc.xref_get_key(xref, "Length")`) oku. |
| **O2** | `src/pdfatolye/core/images.py:192-193` | **Saydam Maskeli Görselde `pix.tobytes("png")` RAM Patlaması:** A0/139 MP görselde RGBA pixmap (~600 MB) + PNG bytes (~250 MB) döngüde açıkça `pix = None` edilmiyor. | Büyük görsellerde pixmap'i hemen serbest bırak (`pix = None`), mümkünse doğrudan diske yaz (`pix.save(target)`). |
| **O3** | `src/pdfatolye/core/pdfio.py:29-41` & `security.py:203-212` | **Korunmasız `page_count` ve `repair` `doc.save`:** Ağır hasarlı PDF'te `open_pdf` içindeki `doc.page_count` veya `repair` içindeki `doc.save(..., clean=True)` try bloğu dışında `RuntimeError` fırlatıp 500 hatasına ve açık handle'a yol açar. | İlgili erişimleri `try...except Exception` içine alıp `doc.close()` sonrası `BrokenPdfError` yükselt. |
| **O4** | `src/pdfatolye/core/content.py:318` | **Döndürülmüş Sayfada TextBox Uzatma Hatası:** `box.y1 += -rc + 1` görünüm uzayında `y1`'i artırır, ancak 90°/270° döndürülmüş sayfada `-rc` sayfa genişliği/yüksekliği ekseniyle ters düşer. | Sayfa dönüş açısına göre genişletilecek ekseni (`x1` veya `y1`) `page.rotation` değerine göre seç veya görünüm koordinatından sayfa rect'ine göre çevir. |
| **O5** | `src/pdfatolye/core/content.py:478-480` | **Sayfa Numaralarında `{N}` Değerinin Yanlış Hesaplanması:** `total = op.start + len(targets) - 1` formülü `pages="5-7"` veya `skip_first=True` olduğunda belgenin gerçek sayfa sayısını değil seçili aralığı yazar. | `{N}` için `doc.page_count` (veya opsiyonel olarak seçili aralık toplamı) netleştirilmeli; varsayılan `{N}` = `doc.page_count` olmalı. |
| **O6** | `src/pdfatolye/core/pages.py:398-402` | **Yer İmine Göre Bölmede Aynı Sayfadaki Başlıkların Atlanması:** İki 1. seviye yer imi aynı sayfayı gösteriyorsa `end > start` False olur ve ilk yer imi sessizce silinir. | Aynı sayfayı gösteren ardışık yer imlerini tek grupta birleştir veya kullanıcıya uyarı ver. |
| **O7** | `src/pdfatolye/core/images.py:163, 198` | **Çıktı Dosya Adlarında `safe_filename` Eksikliği:** `extract_images` ve `pdf_to_images` `input.stem`'i doğrudan kullanıyor (`CON`, `?`, `:` gibi adlarda Windows `OSError`). | `safe_filename(input.stem)` uygula. |
| **O8** | `src/pdfatolye/convert/to_word.py:88, 94` & `to_excel.py:190-191` | **Boş Aralıkta `ZeroDivisionError`:** Sayfa aralığı boş dönerse `total = 0` bölme hatası verir. | İşlem başında `if not pages:` kontrolü yapıp anlamlı hata/boş sonuç döndür. |
| **O9** | `src/pdfatolye/convert/to_excel.py:136-137, 218-262` | **Birleştirilmiş Hücrelerde Metin Tekrarı / Boşluk:** PyMuPDF birleşik hücrelerde aynı rect'i tekrarlarsa metin Excel'de yan yana sütunlara kopyalanıyor; `None` dönerse boş kalıyor ve `ws.merge_cells()` hiç çağrılmıyor. | Birleşik hücre rect'lerini tekilleştirip `openpyxl` `ws.merge_cells()` uygula. |
| **O10** | `src/pdfatolye/convert/browser.py:152-156` | **`path.resolve()` Route Hatası:** Bozuk `file:///` URI'sinde `path.resolve()` `OSError`/`ValueError` fırlatıp route callback'ini bozabilir. | `try...except (OSError, ValueError):` ile yakalayıp `r.abort()` çağır. |
| **O11** | `src/pdfatolye/convert/markdown/render.py:274-280` | **Tek Başlık Eşleşmezse Tüm TOC'un Atlanması:** `all(p is not None ...)` şartı yüzünden tek bir formüllü başlık eşleşmezse bütün yer imi ağacı yazılmıyor. | Eşleşen başlıkları yaz, eşleşmeyenler için en yakın bilinen sayfa/uyarı mekanizması kur. |
| **O12** | `src/pdfatolye/desktop.py:76-90, 197-217` | **Tek Örnek Yarışı & Port Değişiminde Pencere Donması:** `calisiyor.json` geç yazılıyor (çift tıkta iki örnek açılabilir). Ayarlar'dan port değişip restart yapıldığında mevcut Edge `--app` penceresi eski portta `ERR_CONNECTION_REFUSED`'da kalabiliyor (`restart.ts`'teki URL yönlendirmesiyle çakışabilen pencere/sağlık kontrolü zamanlamaları). | Windows Named Mutex (`CreateMutexW`) ile atomik tek örnek kilidi kur; restart sırasında pencere yeniden açma veya `restart.ts` çift slash (`//`) bug'ını (`restart.ts:27`) düzelt. |
| **O13** | `src/pdfatolye/native.py:85-86` | **`explorer.exe /select` Tırnak Hatası:** Boşluklu yolda `"/select,C:\..."` tırnaklanması Explorer'da Belgeler klasörünü açar. | Argüman biçimini Explorer'ın beklediği şekle getir (`/select,"..."` veya Win32 `SHOpenFolderAndSelectItems`). |
| **O14** | `web/src/editor/PageCanvas.tsx:79-101` & `PagePreview.tsx:22-28` & `pdf.ts:106-112` | **`page.cleanup()` Eksikliği & Sonsuz Cache:** `pdf.js` sayfa nesneleri temizlenmiyor, `thumbs` ve `images` Map'leri sınırsız büyüyor, `Thumb` unmount olunca kuyruktaki render iptal edilmiyor. | `try...finally { page.cleanup(); }` ekle; `thumbs` için LRU sınırı (ör. 100 öğe) ve `AbortSignal` iptali uygula. |
| **O15** | `web/src/pages/Editor.tsx:222-237` | **Kaydetme Sonrası `pageIndex` Sınır Aşımı:** Yeni sürümde sayfa sayısı azaldıysa `doc.getPage(pageIndex + 1)` çöküyor. | `pageIndex`'i `Math.min(pageIndex, pageCount - 1)` ile sınırla. |
| **O16** | `web/src/api.ts:248-268` | **`watchJob` JSON Parse & Polling Fırtınası:** SSE `onmessage` içinde `JSON.parse` try/catch'siz; fallback `poll()` hata durumunda sonsuza kadar 700 ms'de bir istek atıyor. | `JSON.parse`'ı `try/catch` içine al; polling için üstel gecikme (backoff) ve max hata sınırı ekle. |
| **O17** | `src/pdfatolye/api/routes_files.py:158-179` | **ZIP İndirmede Geçici Dosya Sızıntısı:** `zf.write` hata verirse `%TEMP%\pa-zip-*.zip` dosyası asla silinmez. Ayrıca `ZIP_DEFLATED` zaten sıkışmış PDF/JPEG'lerde boşuna CPU harcar. | `try...except` içinde `tmp_name`'i temizle ve `zipfile.ZIP_STORED` kullan. |
| **O18** | `src/pdfatolye/jobs/workers.py:256-258` | **`md_to_pdf` Ek Dosya Adı Çakışması:** Farklı klasörlerden aynı adlı iki resim (`resim.png`) eklenirse sessizce birbirinin üzerine yazılır. | Çakışma varsa uyar veya göreli yol/benzersiz isimlendirme destekle. |

### 🟡 Düşük Öncelikli / Kenar Durumlar

| # | Konum | Açıklama |
|---|---|---|
| **D1** | `src/pdfatolye/core/content.py:598` | `prepare_signature` içinde `extrema[0] == 255` kontrolü tek bir yarı saydam pikselde kağıt beyazını temizlemeyi atlar (`>= 250` eşiği daha dayanıklıdır). |
| **D2** | `src/pdfatolye/core/geometry.py:86-90` | `fit_inside` içinde `pymupdf.Rect(box).normalize()` çağrılmıyor. |
| **D3** | `src/pdfatolye/core/content.py:576` & `cli.py:47-49` | `cli.py` `@friendly_errors` `PermissionError` yakalamıyor (açık PDF üzerine yazarken ham traceback çıkar). |
| **D4** | `src/pdfatolye/settings.py:167-194` | Eşzamanlı `PUT /api/settings` isteklerinde `save_settings` kilitsiz olduğundan son yazan diğerini ezebilir (lost update). |
| **D5** | `src/pdfatolye/api/app.py:135-136` & `lan.py:18-36` | LAN modunda Wi-Fi/IP değişirse açılışta alınan `allowed_hosts` güncellenmez, telefon `400 Invalid Host` alır. |
| **D6** | `src/pdfatolye/jobs/manager.py:124-132` | `_persist` hata verirse `.tmp` dosyaları birikir; `_load` sadece `*.json` temizler. |
| **D7** | `web/src/editor/SignatureDialog.tsx:40-55` | Sekme/modal animasyonu bitmeden `offsetWidth` okunursa imza pedi `0x0` boyutunda kalabilir (`ResizeObserver` gerekir). |
| **D8** | `web/src/pages/Editor.tsx:485-488` | `<textarea>`'da her harf vuruşunda `commit()` çağrılıyor; metin alanı için debounce/onBlur commit gerekir. |
| **D9** | `web/src/router.ts:43-52` | `confirmLeave` iptal edildiğinde `pushState` kullanılması tarayıcı geri yığınını bozar. |
| **D10** | `web/src/components/Modal.tsx:36` | Modal içinden dışarı metin sürükleyip bırakınca (`mouseup` backdrop'ta) modal istenmeden kapanır (`onMouseDown` + `onClick` kontrolü gerekir). |
| **D11** | `web/src/restart.ts:27` | `${url}/${window.location.hash}` birleşimi `//#/` çift slash üretiyor. |
| **D12** | `web/src/pages/Markdown.tsx:192` | `URL.revokeObjectURL` sabit 1000 ms sonra çalışıyor; yavaş sistemlerde indirme kesilebilir. |
| **D13** | `paket/derle.py:37-38` & `kurulum.py:186, 226-231` | Sabit `C:\Program Files` motor yolları; kurulum/kaldırmada Windows Gezgini/antivirüs kilidinde sabit 2 sn bekleme yetersiz kalabilir. |
| **D14** | `src/pdfatolye/proc.py:82-96, 134-152` | `spawn` çıkışında süreç normal bitse bile her seferinde tüm sistem süreçleri `psutil.process_iter` ile taranıyor (yalnızca hata/iptal/timeout durumunda veya yalnızca başlatılan PID ağacı için çalışmalı). |

---

## 3. Eksiklikler (Özellik, UX ve Test Boşlukları)

### 3.1. Markdown → PDF & Obsidian Eksikleri
- **Not Gömme (`![[Başka not]]`):** `parser.py:142-143` şu an sadece uyarı metni basıyor (`PLAN.md` §5.1'de v1.1 olarak planlanmıştı: derinlik sınırı 3 + döngü kontrolü).
- **Mermaid Diyagramları:** Ders notlarında AI'ların çok sık ürettiği ```` ```mermaid ```` blokları şu an ham kod olarak basılıyor.
- **Tıklanabilir İç Linkler:** Obsidian `[[#Başlık]]` veya aynı belge içi bağlantılar `<a>` yerine düz `<span>` olarak kalıyor (`obsidian.py:195-204`).
- **CSS Baskı Taşmaları (`base.css`):**
  - `pre.code { break-inside: avoid; }` (satır 61) ve `.callout { break-inside: avoid; }` (satır 114): Bir sayfadan uzun kod blokları veya callout kutuları bölünemediği için sayfa altından kesilip kayboluyor.
  - Çok sütunlu geniş Markdown tabloları sayfa sağ kenarından taşabiliyor.
  - Kapak sayfasında (`cover=True`) "Sayfa 1 / N" altbilgisi gizlenmiyor (`render.py:213-218`).
  - Aynı metne sahip birden fazla başlıkta `slugify` benzersizleştirme (`-1`, `-2`) yapılmıyor (`parser.py:39-43`).

### 3.2. PDF Çekirdeği ve İş Kuyruğu Eksikleri
- **Yazdırma / Pafta Araçları:** `SONRAKI_OTURUM.md`'de aday olarak bekleyen: sayfa boyutu değiştirme (ölçekle A4'e sığdır), bir kağıda N sayfa (N-up, ders slaytları için kritik!), A0 paftayı A4 karelere bölme (poster/tile), kitapçık (booklet), sayfa kırpma (crop/margin trim).
- **Toplu İşlem Koruma Sınırı:** `compress` işi için `LIMITS` tanımı olmaması nedeniyle 4 paralel Ghostscript süreci sistemi kilitleyebilir. `split` ile 5.000 sayfalık PDF'i "her sayfa" bölmek binlerce `meta.json` yaratıp API'yi boğar (büyük bölmelerde doğrudan ZIP çıktısı üretmek daha sağlıklı).
- **`to_word.py` Kırılganlığı:** `pdf2docx<0.6` iç sınıflarına (`RawPageFactory`, `Fonts.extract`) sıkı bağımlılık; uzun süren tek sayfalık vektör çizimlerinde iptal edilememe; çok büyük PDF'lerde `Document()` RAM birikimi.
- **Güncelleme Doğrulama (`update.py`):** Sadece sürüm etiketi kontrolü yapıyor; indirilen zip için SHA-256 doğrulama yok.

### 3.3. Ön Yüz ve Test Kapsamı Eksikleri
- **500+ Sayfada Sanallaştırma (Virtualization) Yok:** `Organizer.tsx` tüm sayfaları gerçek DOM'a basıyor ve klavye geziniminde `offsetTop` ile senkron reflow (layout thrashing) yapıyor.
- **Zombi Arka Uç İşleri (`hooks.ts:37-50`):** Kullanıcı arka arkaya iş başlattığında önceki sunucu işi iptal edilmiyor.
- **CI Boşlukları (`.github/workflows/ci.yml`):** Windows işinde LibreOffice/Tesseract/Ghostscript yok (ilgili testler skip oluyor), Playwright tarayıcısı kurulmuyor (`test_ui.py` atlanıyor), yalnızca `--motorsuz` paket derleniyor.
- **Frontend Test Eksikliği:** `Editor.tsx`, `PageCanvas.tsx`, `Organizer.tsx`, `JobPanel.tsx`, `FilePicker.tsx`, `PasswordDialog.tsx` için React bileşen testi yok.

---

## 4. Performans Analizi: Projeyi Ne Kadar ve Nasıl Hızlandırabiliriz?

| Alan | Mevcut Darboğaz | Önerilen İyileştirme | Beklenen Kazanç |
|---|---|---|---|
| **MD → PDF & HTML → PDF** | Her dönüşümde `OfflineBrowser` sıfırdan Edge başlatıp kapatıyor (~1.5–2.5 sn soğuk başlangıç). KaTeX varlıkları her seferinde diske kopyalanıyor (`render.py:124`). Vault her notta baştan `os.walk` ile taranıyor (`parser.py:86`). | **1) Sıcak Tarayıcı Havuzu (Warm Browser Pool):** Uzun ömürlü tek Edge süreci + her baskıda temiz `BrowserContext` (bellek/çerez izole).<br>**2) KaTeX Doğrudan Erişim:** Kopyalamadan `ASSETS / "katex"` okuma + CSS `@functools.cache`.<br>**3) Kasa Önbelleği:** Vault dosya indeksini TTL/mtime ile önbelleğe alma. | **5x – 10x hızlanma** (Tekil 1-2 sayfalık MD → PDF dönüşümü **~2.5–3 sn'den ~0.3–0.5 sn'ye** iner). |
| **Sayfa Düzenleyici Küçük Resimler** | `pdf.js` tarayıcıda 100 MP A0 paftaları veya 400 sayfalık dosyaları JS Worker + Canvas ile render edip base64 string olarak RAM'de biriktiriyor. | **Sunucu Taraflı Thumbnail Uç Noktası:** `/api/files/{id}/thumb/{page}?w=240` ile PyMuPDF C çekirdeğinden doğrudan WebP/JPEG dönmek (`Cache-Control` ile tarayıcı önbellekli). | **10x – 50x hızlanma**; A0 paftada tarayıcı OOM riski tamamen sıfırlanır, JS bellek tüketimi %90 düşer. |
| **Sayfa Bölme (`pages.py:split`)** | `split` döngüde her parça için `compose` çağırıp 8 GB'lık PDF'i yüzlerce kez sıfırdan açıp kapatıyor. | Girdi `doc`'u döngü dışında **tek kez** açıp sayfaları kopyalamak + her adımda iptal kontrolü. | **50x – 200x hızlanma** (500 sayfalık PDF'i bölmede dakikalar → saniyeler). |
| **SSE ve İş Takibi** | `routes_jobs.py` 250 ms'de bir polling yapıyor ve her turda `job.outputs` içindeki tüm `meta.json`'ları okuyor (`O(N²)`). | `asyncio.Event` tabanlı bildirim + `outputs` meta okumasını yalnızca iş bittiğinde (veya önbellekten) yapma. | CPU/Disk I/O yükü %95 azalır, anlık (1 ms) UI tepkisi sağlanır. |
| **PNG İşleme & ZIP** | `images.py` ve `content.py`'de `optimize=True` ile PNG kaydı (5 zlib denemesi); `routes_files.py` ZIP'te `ZIP_DEFLATED`. | Büyük resimlerde `optimize=False`, ZIP indirmede `ZIP_STORED` (zaten sıkışmış PDF/JPEG). | **3x – 8x daha hızlı** resim/ZIP üretimi. |
| **Sıkıştırma & Redaction** | `compress.py:97` tüm ham image stream'lerini okuyor; `content.py:431` tek kelime karartmada 5.000 sayfanın tamamını tarıyor. | `/Length` anahtarından boyut okuma; karartma uyarı taramasında iptal kontrolü + sayfa başına hafifletme. | Büyük dosyalarda bellek tepe noktası ve bekleme süresi dramatik düşer. |
| **Sanallaştırılmış Izgara** | `Organizer.tsx` 500+ karoyu DOM'da tutuyor ve klavyede `offsetTop` reflow tetikliyor. | `@tanstack/react-virtual` (veya pencerelemeli ızgara) + `React.memo(PageTile)`. | 1.000+ sayfalık PDF'lerde 60 FPS akıcı kaydırma ve anlık klavye hareketi. |

---

## 5. Güncellenmiş Faz Planlaması (Yol Haritası)

Mevcut `PLAN.md` (§10.1) ve `SONRAKI_OTURUM.md` durumu (`v0.10.0`, Faz 0–7, A–D3, F tamam) temel alınarak, yeni özelliklerden **önce** hata temizliği ve hız optimizasyonuna odaklanan güncellenmiş faz sırası:

### Faz G0 — Debug, Crash Önleme ve Eşzamanlılık Sağlamlaştırması *(Öncelik 1 — Hemen)*
*Amaç: Mevcut v0.10.0'daki tüm çökme, bellek patlaması, dosya kilidi ve UI state hatalarını kapatmak.*
1. **Storage & Jobs Kilitleri (`storage.py`, `manager.py`, `routes_files.py`, `routes_jobs.py`):**
   - `FileStore` okuma/yazma/`delete`/`touch` için lock + `delete` öncesi `in_use()` kontrolü (`409 Conflict`).
   - `JobManager` shutdown/iptalinde `store.release()` garantisi ve `job.view()` snapshot kilidi.
   - `routes_files.py:zip_files` hata anında `%TEMP%` temizliği.
2. **Büyük Dosya & Windows Crash Düzeltmeleri (`core/`, `convert/`, `proc.py`):**
   - `ocr.py:175` `read_bytes()` → `shutil.copyfile()`; `compress.py:97` `/Length` okuması; `images.py` `smask` bellek serbest bırakma + `safe_filename`.
   - `content.py` yerinde kaydetmede dosya kilidi çözümü; `pdfio.py` ve `security.py:repair` try-except kapsamı.
   - `proc.py:run_lines` `try...finally` + `proc.poll()` deadlock koruması.
   - `to_word.py` 2. aşama `try...except` + boş aralık `ZeroDivisionError` koruması; `office.py` `ignore_cleanup_errors=True` ve toplu kopyalama/taşıma dayanıklılığı.
   - `document.py` güvenli `decodeURI`, `browser.py` güvenli `path.resolve()`, `native.py` `explorer /select` düzeltmesi.
3. **Ön Yüz Bug & UX Temizliği (`web/src/`):**
   - `PageCanvas.tsx` A0 canvas max piksel sınırı + `page.cleanup()` + `canvas.width=0`; `onDragEnd`'de `commit()` (Undo yığını düzeltmesi).
   - URL'den açılan şifreli PDF'lerde tüm araç sayfalarında `PasswordDialog` desteği.
   - `Editor.tsx` `pageIndex` clamp + textarea debounce; `api.ts` `watchJob` güvenli `JSON.parse` + backoff; `Modal.tsx` drag-out kapanma düzeltmesi; `router.ts` history düzeltmesi; `restart.ts` çift slash düzeltmesi.
4. **Regresyon Testleri:** Her düzeltme için eski kodda kırmızı yanan test (`SONRAKI_OTURUM.md` kuralı).

### Faz G1 — Performans ve Hızlandırma Sıçraması *(Öncelik 2)*
*Amaç: Uygulamayı "hızlı bir yerel araçtan" "anlık tepki veren masaüstü stüdyosuna" çıkarmak.*
1. **Sunucu Taraflı Küçük Resim (Thumbnail) Uç Noktası:** PyMuPDF ile `/api/files/{id}/thumb/{page}` + HTTP cache; `Organizer.tsx` sanallaştırma + `React.memo`.
2. **Sıcak Tarayıcı Havuzu (Warm Browser Pool):** MD/HTML → PDF için kalıcı Edge örneği + izole `BrowserContext`; KaTeX kopyalamasını kaldırma + CSS & vault indeks önbelleği.
3. **Çekirdek Hızlandırmalar:** `pages.py:split` tek seferde `open_pdf` + iptal desteği; `routes_jobs.py` event-driven SSE + `O(N²)` disk okumasını kaldırma; `ZIP_STORED`; `optimize=False` PNG kaydı; `LIMITS["compress"] = 1`.
4. **Tek Örnek Mutex (`desktop.py`):** Win32 `CreateMutexW` + port değişiminde Edge pencere senkronizasyonu.

### Faz E — v1.0.0 Yayın, Paket Küçültme ve CI Otomasyonu *(Öncelik 3)*
*Amaç: Arkadaş geri bildirimleriyle birlikte 1.0.0 sürümünü olgunlaştırmak.*
1. **Paket Optimizasyonu (301 MB → Hedef ~150 MB altı veya modüler seçenek):**
   - `derle.py`'de Ghostscript'in gereksiz ICC/dokümantasyon/örnek dosyalarını ayıklama.
   - OpenCV/pdf2docx ağır bağımlılığı için seçenek değerlendirmesi veya yalnızca gerekli binary'lerin tutulması.
2. **Güncelleme Güvenliği (`update.py`):** GitHub Release'e `SHA256SUMS.txt` üretip güncelleme denetiminde doğrulama.
3. **CI Güçlendirmesi (`.github/workflows/ci.yml`):** Playwright tarayıcı + motorlarla E2E testlerinin CI'da düzenli koşması; etiketle otomatik Release taslağı/zip üretimi.
4. **Gizlilik Metni & 1.0.0 Sürümleme.**

### Faz G2 — Yazdırma, Ders Slaytı ve Pafta Araçları *(Öncelik 4 — Günlük Hayat & Öğrenci Odaklı)*
*`SONRAKI_OTURUM.md`'deki adayların en yüksek getirili olanları:*
1. **Bir Kağıda N Sayfa (N-up) & Slayt Düzeni:** Ders PDF slaytlarını 2×2, 3×2 veya 2×1 (yanına not alma boşluklu!) olarak tek A4'e basma.
2. **Sayfa Boyutu Değiştirme / Normalize Etme:** Farklı boyutlu sayfaları tek tip A4/A3'e orantılı sığdırma.
3. **A0 Paftayı A4 Parçalara Bölme (Poster / Tile):** Şehir planlama / mühendislik paftalarını ev yazıcısından çıkacak şekilde bindirmeli (overlap) A4 sayfalara bölme.
4. **Sayfa Kırpma (Crop / Kenar Boşluğu Kesme) & Kitapçık (Booklet) Sıralaması.**

### Faz G3 — Akademik / Ders Çalışma Süper Güçleri (MD → PDF Evrimi) *(Öncelik 5)*
*Kullanıcının "AI'lara MD ders notu hazırlatıp PDF'e çevirme" ana senaryosu için:*
1. **Mermaid Diyagramları (Tam Çevrimdışı):** Yerel `mermaid.min.js` gömerek AI'ların ürettiği akış şemalarını, sıra diyagramlarını ve zihin haritalarını doğrudan vektörel PDF olarak basma.
2. **Obsidian Not Gömme (`![[Başka not]]` ve `![[Not#Başlık]]`):** Döngü korumalı (derinlik 3) birleşik not derleme + tıklanabilir belge içi `[[#Başlık]]` bağlantıları.
3. **CSS Baskı Kalitesi Düzeltmeleri:** Uzun `pre.code` ve `.callout` bloklarının sayfa ortasında kesilmeden bölünebilmesi, geniş tablolar için otomatik sığdırma, kapak sayfasında sayfa numarasının gizlenmesi, mükerrer başlık slug tekilleştirmesi.
4. **Akademik Temalar:** Çift sütunlu özet/sınav kağıdı ("cheat sheet") teması ve formül/teorem kutuları.

### Faz G4 — İleri PDF Araçları & İş Akışları *(Öncelik 6)*
1. **İki PDF Karşılaştırma (Visual & Text Diff):** Ders notu veya sözleşme revizyonları arasındaki farkları yan yana ve görsel vurgulu gösterme.
2. **Yer İmi (TOC / Outline) Düzenleyici:** PDF'lere elle içindekiler/yer imi ağacı ekleme, düzenleme ve yeniden adlandırma.
3. **Toplu İş Akışı (Pipeline / Makro):** Örneğin *"OCR yap → Dengeli sıkıştır → Filigran ekle → Şifrele"* adımlarını tek tıkla zincirleme çalıştırma.
4. **Çoklu Dil (İngilizce Arayüz):** `web/src/labels.ts` üzerinden i18n desteğiyle uluslararası açık kaynak yayılımı.

---

## 6. Projenin Tavanı: Bu Proje Nereye Gidebilir?

PDF Atölyesi halihazırda teknik temel olarak birçok açık kaynak web aracından ("Stirling-PDF", "BentoPDF" vb.) **iki konuda** çok daha güçlü bir noktaya sahip:
1. **Gerçek masaüstü kurulumu ve Windows SAC uyumluluğu** (Docker/Java/Node kurulumu istemeden tek ZIP ile çalışması).
2. **AI / Obsidian / LaTeX odaklı Markdown → PDF motoru** (Piyasadaki PDF araçlarının neredeyse hiçbirinde olmayan gerçek KaTeX + Obsidian callout + yerel kasa resim çözümleme hattı).

**Projenin ulaşabileceği tavan:**
- **Kısa Vadede (Faz G0–G1 + E):** Sıfır çökme, 8 GB paftalarda bile kasmayan sunucu-thumbnail'lı arayüz, saniyenin altında MD→PDF baskısı ve tek tıkla güncellenebilen **v1.0.0** kişisel/arkadaş ürünü.
- **Orta Vadede (Faz G2–G3):** *"Öğrenci ve Mühendisler için Çevrimdışı PDF & Ders Notu Stüdyosu"*. AI'dan (ChatGPT/Gemini/Claude) alınan Markdown + LaTeX + Mermaid notunu 1 saniyede kitap kalitesinde PDF'e çeviren; ardından N-up ders slaytı, pafta poster bölme, OCR ve akıllı sıkıştırma yapan benzersiz bir masaüstü aracı.
- **Uzun Vadede (Faz G4 ve ötesi):**
  - **Modüler Motor İndirici ile <40 MB Çekirdek Paket:** Python + PyMuPDF + arayüzü hafif çekirdek olarak tutup, Ghostscript/Tesseract/pdf2docx gibi ağır motorları ihtiyaç duyulduğunda tek tuşla uygulama içinden indirilebilir eklentilere çevirmek.
  - **Yerel LLM / Akıllı PDF Asistanı (Opsiyonel Eklenti):** Zaten OCR ve metin çıkarımı yapabilen çekirdeğin üzerine, kullanıcının kendi API anahtarı veya yerel Ollama/LM Studio bağlantısıyla PDF'ten Markdown ders notu çıkarma (`PDF → MD`) döngüsünü tamamlamak.
  - **Tam İki Yönlü Ekosistem:** `Markdown → PDF` ile başlayan projenin `PDF → Markdown (formüllü/tablolu)` + `PDF Karşılaştırma` + `İş Akışı Otomasyonu` ile kendi alanındaki kapalı/ücretli sitelere (ILovePDF, Smallpdf, Adobe Acrobat) olan ihtiyacı %100 ortadan kaldıran açık kaynaklı (`AGPL-3.0`) referans bir masaüstü uygulamasına dönüşmesi.

