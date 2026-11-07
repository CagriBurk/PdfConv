# PDF Atölyesi

Kendi bilgisayarında çalışan, çevrimdışı PDF araç seti: Markdown / Office → PDF,
sayfa düzenleme, içerik ekleme, sıkıştırma, OCR, şifreleme. Dosyalar internete çıkmaz.
Ayrıntılı plan: [PLAN.md](PLAN.md).

## Arkadaşlar için kurulum (tek dosya, hiçbir şey bilmeden)

Uygulamayı kullanmak için uv, Node, git ya da Python **gerekmez**.

1. `PdfAtolyesi-<sürüm>.zip` dosyasını indir, sağ tıkla → **Tümünü ayıkla**.
2. Açılan klasördeki **Kur** (`Kur.cmd`) dosyasına çift tıkla. Windows "Windows bilgisayarınızı
   korudu" ya da "yayımcı doğrulanamadı" derse **Daha fazla bilgi → Yine de çalıştır** (kurulum
   dosyası imzalı değil; içinde çalışan Python python.org imzalıdır). Yönetici izni istemez.
3. Kurulum bir iki dakika sürer, bitince uygulama penceresi açılır. İlk açılışta kısa bir tanıtım
   ve eksik bir şey varsa (ör. LibreOffice) ne yapılacağı gösterilir. Sonra masaüstündeki **PDF
   Atölyesi** simgesini kullan. İndirdiğin zip'i ve ayıkladığın klasörü silebilirsin.

- Kurulum yeri: `%LOCALAPPDATA%\Programs\PdfAtolyesi`; belgeler ve ayarlar:
  `%LOCALAPPDATA%\PdfAtolye` (ayrı tutulur, güncellemede korunur).
- Uygulama kendi penceresinde açılır (Edge'in uygulama kipi, ayrı profil; kendi Edge sekmelerine
  karışmaz). Pencereyi kapatınca uygulama da kapanır. Simgeye ikinci kez tıklamak yeni bir
  pencere açar, ikinci bir uygulama başlatmaz.
- OCR (Tesseract, Türkçe + İngilizce) ve Ghostscript pakette gelir. **Word / Excel / PowerPoint
  → PDF** için LibreOffice gerekir (pakete konmadı, ~350 MB): Ayarlar'da ya da Office ekranında
  **LibreOffice'i kur** düğmesi (winget ile; Windows izin isteyebilir).
- Sağ tık → Gönder → **PDF'e çevir** de kurulur.
- **Ayarlar** ekrandan değişir (dosya düzenlemek gerekmez): dosyaların ne kadar saklanacağı,
  Obsidian kasası (Klasör seç…), Markdown için varsayılan tema ve kağıt, telefon modu. Port ve
  kütüphane sürümleri gibi geliştirici bilgileri **Gelişmiş** altında.
- **Güncelleme**: Ayarlar → **Güncellemeleri denetle** (yalnızca basınca GitHub'a sorar). Yeni
  paketi indirip yine **Kur**'a çift tıkla; eskisinin üzerine kurar, belgelerin korunur.
- **Kaldırma**: Ayarlar → Uygulamalar → PDF Atölyesi → Kaldır (ya da kurulum klasöründeki
  `Kaldir.cmd`). Belgelerin, imzaların ve ayarların da silinsin mi diye sorar.

Paketi üretmek (geliştirici): `uv run python paket/derle.py` → `build/PdfAtolyesi-<sürüm>.zip`
(Tesseract ve Ghostscript bu bilgisayardaki kurulumdan alınır; `--motorsuz` ile alınmaz; ağ
yavaşsa `--yerel-ortam` bağımlılıkları kilitle eşit `.venv`'den kopyalar). Her gönderimde CI
motorsuz paketi üretip dener ve artifact olarak yükler.

## Geliştirici kurulumu (kaynak koddan, ~10 dakika)

1. **Programlar** (PowerShell'de, her biri bir kez):

   ```
   winget install astral-sh.uv
   winget install OpenJS.NodeJS.LTS
   winget install Git.Git
   winget install TheDocumentFoundation.LibreOffice
   winget install UB-Mannheim.TesseractOCR
   ```

   Kurulumdan sonra PowerShell'i kapatıp yeniden aç (PATH yenilensin). Python'u uv kendisi getirir;
   Edge Windows ile gelir.

2. **Türkçe OCR paketi**: `tur.traineddata` dosyasını github.com/tesseract-ocr/tessdata_fast
   deposundan indirip `C:\Program Files\Tesseract-OCR\tessdata\` içine kopyala (yönetici izni ister).

3. **Ghostscript** (OCR ve güçlü sıkıştırma için; winget'te yok):
   github.com/ArtifexSoftware/ghostpdl-downloads sürümlerinden `gs*w64.exe` dosyasını
   **kısa bir klasöre** (ör. `C:\Kur`) indirip çalıştır; uzun yoldan çalışınca sessizce çıkıyor.

4. **Proje**:

   ```
   git clone https://github.com/CagriBurk/PdfConv.git
   cd PdfConv
   ```

5. **Çalıştır**: `baslat.bat` dosyasına çift tıkla. İlk açılışta Python bağımlılıklarını kurar ve
   arayüzü derler (birkaç dakika), sonra tarayıcıda `http://127.0.0.1:8790` açılır.

6. **Kontrol**: arayüzde **Ayarlar** sayfasında dört motorun (LibreOffice, Edge, Tesseract,
   Ghostscript) hepsi "Hazır" görünmeli. Eksik olanın yanında kurulum komutu yazar.
   Komut satırından: `uv run python -m pdfatolye motorlar`

7. **Kısayollar** (isteğe bağlı): masaüstüne "PDF Atölyesi" ve sağ tık → Gönder menüsüne
   "PDF'e çevir" ekler. Yalnızca kendi kullanıcı klasörüne yazar; `-Kaldir` ile geri alınır.

   ```
   powershell -ExecutionPolicy Bypass -File kurulum\kisayollar.ps1
   ```

   Sonra bir Word/Markdown/resim dosyasına sağ tıkla → Gönder (Windows 11'de önce "Daha fazla
   seçenek göster") → **PDF'e çevir**; PDF dosyanın yanına yazılır.

Elle çalıştırmak istersen:

```
uv sync
npm --prefix web install
npm --prefix web run build
uv run python -m pdfatolye serve
```

Not: Windows'un Akıllı Uygulama Denetimi uv'nin ürettiği `pdfatolye.exe` başlatıcısını
engelleyebilir; bu yüzden komutlar `python -m pdfatolye` biçiminde.

### Linux (kaynak koddan)

Masaüstü paketi (Kur.cmd) yalnızca Windows içindir. Linux'ta uygulama kaynak koddan çalışır ve
tarayıcıda açılır; her gönderimde CI Ubuntu'da da bütün testleri çalıştırır. Debian/Ubuntu'da:

```
sudo apt install tesseract-ocr tesseract-ocr-tur ghostscript libreoffice-writer libreoffice-calc libreoffice-impress chromium
curl -LsSf https://astral.sh/uv/install.sh | sh     # uv; Node.js da gerekir (arayüzü derlemek için)
git clone https://github.com/CagriBurk/PdfConv.git && cd PdfConv
uv sync && npm --prefix web install && npm --prefix web run build
uv run python -m pdfatolye serve                    # http://127.0.0.1:8790
```

Markdown/HTML → PDF için Chromium, Google Chrome ya da Microsoft Edge'den biri yeterli (PATH'te
aranır). Ayarlar ve belgeler: `~/.local/share/PdfAtolye`. Linux'ta olmayanlar: masaüstü penceresi
ve kurulum programı, "Klasör seç…" ve "Klasörde göster" (yolu elle yaz), "LibreOffice'i kur"
düğmesi (paket yöneticisiyle kur). Telefon modu: `uv run python -m pdfatolye serve --lan`.

### Telefondan kullanmak (aynı Wi-Fi)

Masaüstü uygulamasında: **Ayarlar → Telefon modu** kutusunu işaretle, **Şimdi yeniden başlat**
(pencere açık kalır). Geliştirme sunucusunda: `baslat.bat --lan`. Ayarlar sayfasında (ve
terminalde) bir QR kod çıkar; telefonun kamerasıyla okut. Telefon modu açıkken üst çubukta
"Telefon modu açık" yazar; kapatmak için kutuyu kaldırıp yeniden başlat. QR kod tek kullanımlıktır: her cihaz için Ayarlar'da yenisi çıkar ve eşleşmemiş
cihazların istekleri reddedilir. Bağlı cihazları Ayarlar'da görür, istediğinde hepsinin bağlantısını
kesersin. Windows güvenlik duvarı ilk seferde izin isteyebilir ("Özel ağlar" yeterli). Bağlantı
yerel ağda şifresizdir (HTTP): yalnızca güvendiğin Wi-Fi'de kullan, işin bitince sunucuyu kapat.

### Sorun giderme

- Beklenmeyen bir hatada mesajda **hata kimliği** (ör. `3fa2c1b9`) yazar; aynı kimlik günlük
  dosyasında (`%LOCALAPPDATA%\PdfAtolye\logs\pdfatolye.log`, yolu Ayarlar → Gelişmiş'te)
  ayrıntısıyla bulunur. Arayüzün kendisinde bir ekran çökerse beyaz sayfa yerine "Bu ekranda bir
  şeyler ters gitti" ve hata kimliği çıkar; diğer ekranlar çalışmaya devam eder.
- "Diskte yer yok": yükleme, diske sığmayacaksa hiç başlamaz. Yer aç ya da İşler ve dosyalar'dan eski
  dosyaları sil. Dosya başına en fazla 8 GB (`max_upload_mb`), tek seferde toplam 16 GB
  (`max_request_mb`) yüklenir; ayar dosyasından değiştirilebilir. Yükleme sırasında dosyanın iki
  katı kadar boş yer gerekir (önce geçici klasöre, sonra depoya yazılır).
- "8790 portu başka bir program tarafından kullanılıyor": masaüstü uygulaması kendiliğinden boş bir
  port seçer. Geliştirme sunucusunda Ayarlar → Gelişmiş → Port (ya da `baslat.bat --port 8800`).
- Proje klasörünün yolu çok uzunsa (260+ karakter) LibreOffice ve Ghostscript bozulabilir; projeyi
  kısa bir yola (ör. `C:\PdfConv`) koy.

## Web arayüzü

- **Ana sayfa**: dosyayı bırak; türüne göre doğru araç açılır (tek PDF → sayfa düzenleyici,
  birden çok PDF → birleştir, resimler → PDF, Markdown + resimleri → MD → PDF).
- **Sayfa düzenleyici**: sürükleyerek sırala (seçili sayfalar blok hâlinde taşınır), Ctrl/Shift
  ile çoklu seçim, `R` / `Shift+R` döndür, `Delete` sil, `Ctrl+Z` / `Ctrl+Y` geri/ileri,
  başka PDF'leri alana bırakarak sayfalarını ekle, çift tıkla büyüt. "Kaydet" yeni sürüm oluşturur,
  "Önceki sürüme dön" ile geri alınır. **Yalnızca klavyeyle**: oklar sayfalar arasında gezer,
  `Boşluk` seçer, `Shift+ok` seçimi genişletir, `Ctrl+ok` yalnızca odağı taşır, `Alt+ok` seçili
  sayfaları taşır, `Enter` büyütür. Ekran okuyucu yapılan işlemi ("2 sayfa taşındı: 3. konum") duyurur.
- **Birleştir, Böl, Resim → PDF, PDF → Resim**: çok dosyalı çıktılar tek ZIP olarak indirilebilir.
- **Markdown → PDF**: yazdıkça canlı önizleme (baskıyla aynı tema; yazarken önizleme kaydığın
  yerde kalır), seçenekler, uyarılar. Tema ve kağıt "Otomatik"te notun ön bilgisi, o da yoksa
  Ayarlar'daki varsayılan kullanılır. Düzenlediğin
  not bu tarayıcıda taslak olarak tutulur (sekme kapansa da kaybolmaz, sonraki açılışta "Taslağı aç"
  önerilir); "Notu indir (.md)" düzenlenmiş notu UTF-8 olarak indirir. Windows'un eski "ANSI"
  (Windows-1254) biçimindeki notlar da doğru okunur.
- **İçerik Ekle** (editör): yazı, resim, imza, vurgu, dikdörtgen/elips/çizgi/ok, karartma, beyazla
  kapat. Nesneler taşınır, boyutlandırılır, döndürülür; `Delete` sil, `Ctrl+Z` / `Ctrl+Y`, oklar kaydırır.
  "Uygula" yeni sürüm oluşturur. **Karartma** kutunun altındaki yazıyı, resmi, çizimi, açıklamayı ve
  form alanını dosyadan gerçekten siler; aynı metin yer imlerinde, belge bilgilerinde ya da başka
  sayfalarda da geçiyorsa uyarır. Siyah dikdörtgen çizmek karartma değildir. Karartılmamış önceki
  sürüm bu bilgisayarda (Önceki sürüme dön için) silinene kadar durur. İmzalar ("İmzalarım") kalıcı
  saklanır.
- **Filigran** ve **Sayfa Numarası**: önizlemeli ayrı ekranlar.
- **Sıkıştır**: kayıpsız / dengeli / güçlü; önce-sonra boyutu gösterilir, büyürse orijinal korunur.
  Her seviye gömülü yazı tiplerini yalnızca kullanılan karakterlere indirir (yazı ağırlıklı PDF'te
  asıl kazanç bu, kalite değişmez). Dengeli/güçlü resimleri 150/100 DPI'a indirir (taranmış belge
  ve paftalarda %50–90). Güçlü, gerekirse Ghostscript'i de dener; ilerleme sayfa sayfa görünür.
  Az küçüldüyse nedenini söyler (ör. "dosyanın %0'ı resim"). Dosya başına 8 GB'a kadar.
- **OCR**: taranmış PDF'i Türkçe + İngilizce aranabilir yapar; metni olan sayfalar atlanır.
  Sayfa düzenleyici metni olmayan PDF'te bunu kendisi önerir.
- **Güvenlik ve bakım**: AES-256 şifre + izinler, şifre kaldırma (şifre kırma yok), meta veri
  temizliği, bozuk PDF onarımı. Şifreli bir PDF düzenlenince şifresi korunur; şifreyi yalnızca "Şifre
  kaldır" kaldırır. Birden çok kaynaktan üretilen dosyada şifre taşınamazsa bu açıkça söylenir.
- **İşler ve dosyalar**: son işler, tüm dosyalar; sabitlenmeyen dosyalar 24 saat sonra silinir (son
  açılıştan itibaren; açık bir ekranda ya da bir işte kullanılan dosya silinmez; süre Ayarlar'dan
  değişir). Dosyalar **yeniden adlandırılabilir** (uzantı korunur). **Klasörde göster** dosyanın
  bir kopyasını gerçek adıyla `%LOCALAPPDATA%\PdfAtolye\Dışa aktarılanlar` altına koyup Gezgin'de
  gösterir (yalnızca bu bilgisayarda; telefonda görünmez). Çalışan iş
  (LibreOffice, OCR, baskı dahil) "İptal" ile birkaç saniyede durur. Uzun süren OCR/Office işleri
  sıradayken basit işler beklemeden çalışır.
- **Kaydedilmemiş iş**: sayfa düzenleyicide, editörde ve Markdown ekranında kaydetmeden başka
  ekrana geçmek ya da sekmeyi kapatmak önce sorar.

Şifreli PDF'lerin şifresi yalnızca açık sekmenin belleğinde tutulur, hiçbir yere kaydedilmez.

**Güvenilmeyen dosyalar**: Markdown ve HTML baskısında ağ tamamen kapalıdır; belge internete bir şey
gönderemez, diskteki başka dosyaları PDF'e gömemez. Markdown notlarındaki betikler çalışmaz; HTML
dosyalarındaki betikler çalışır (JS ile üretilen raporlar için) ama dışarı çıkamaz.

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
uv run python -m pdfatolye filigran not.pdf --yazi TASLAK --aci 45 --opaklik 0.2
uv run python -m pdfatolye sayfa-no not.pdf --bicim "Sayfa {n} / {N}" --kapak
uv run python -m pdfatolye sikistir *.pdf --seviye dengeli     # kayipsiz | dengeli | guclu
uv run python -m pdfatolye ocr tarama.pdf                     # --mod redo | force
uv run python -m pdfatolye sifrele not.pdf --kopyalama-yok    # şifreyi sorar
uv run python -m pdfatolye sifre-kaldir not.pdf --sifre ...
uv run python -m pdfatolye meta-temizle not.pdf
uv run python -m pdfatolye onar bozuk.pdf
uv run python -m pdfatolye gonder rapor.docx not.md foto1.jpg foto2.jpg   # türüne göre PDF
```

### Office / HTML / metin → PDF

```
uv run python -m pdfatolye cevir rapor.docx                 # rapor.pdf
uv run python -m pdfatolye cevir *.docx *.pptx -o pdfler    # her biri ayrı
uv run python -m pdfatolye cevir a.docx b.xlsx --birlestir  # tek PDF, dosya başına yer imi
uv run python -m pdfatolye cevir tez.docx --pdfa            # arşiv için PDF/A-2b
```

Word, Excel, PowerPoint (makrolu `.docm/.xlsm/.pptm` dahil), ODT/ODS/ODP, RTF,
CSV, WordPerfect LibreOffice ile; HTML ve TXT Edge ile çevrilir.
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
uv run python -m pytest     # testler (tests/e2e: derlenmiş arayüz + Edge ile uçtan uca)
uv run python -m ruff check . # kod denetimi
npm --prefix web test       # arayüz birim testleri (vitest)
npm --prefix web run lint   # arayüz kod denetimi (eslint)
npm --prefix web run dev    # arayüz geliştirme sunucusu (API'yi 8790'e yönlendirir)
```

`python -m` şart: Windows'un Akıllı Uygulama Denetimi `pytest.exe` gibi başlatıcıları engelleyebilir.
Her gönderimde GitHub Actions aynı denetimleri çalıştırır ([ci.yml](.github/workflows/ci.yml)).

## Ayarlar

Ayarlar uygulamanın **Ayarlar** ekranından değişir ve `%LOCALAPPDATA%\PdfAtolye\config.toml`
dosyasına yazılır (geliştirmede proje kökünde bir `config.toml` varsa o). Ekranda olmayanlar
(yükleme sınırları, motor yolları, veri klasörü) bu dosyadan elle değiştirilir; açıklamalı örnek:
`config.example.toml`. Varsayılan veri klasörü: `%LOCALAPPDATA%\PdfAtolye`.

## Lisans

PDF Atölyesi [GNU AGPL v3](LICENSE) ile lisanslıdır (PyMuPDF ve Ghostscript de AGPL). Paketi
başkasına verirken ya da ağ üzerinden hizmet olarak sunarken kaynak kodu (değişikliklerinle
birlikte) aynı lisansla erişilebilir olmalıdır. Paketteki bileşenlerin lisansları: `LISANSLAR.txt`.
