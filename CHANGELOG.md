# Değişiklikler

## Yaklaşan (`arayuz-revizyon` dalı) — 2026-11-21

Kapsamlı UI/UX denetimi ve "Sıcak Atölye" arayüz yenilemesi (yalnızca ön yüz `web/src/`).

### Eklenenler
- **Evrensel Biçim Dönüştür**: Tek ekranda PDF (`→ PNG, JPG, Word .docx, Excel .xlsx`), resimler (`JPG/PNG/WEBP/TIFF/HEIC → JPG/PNG/WEBP/TIFF/PDF`) ve Office/HTML/TXT belgeleri (`→ PDF` veya kendi ailesi içi) dönüştürülebiliyor; belge türüne göre hedef sekmesi ve seçenekler kendiliğinden uyarlanıyor.
- **Sık kullanılanlar (favoriler) & kategori süzgeci**: Ana sayfada araçlar kategori sekmeleriyle (`Tümü | Dönüştür | Düzenle | Ekle | Optimize`) süzülebiliyor; kartlardaki yıldızla sabitlenen araçlar üstte **Sık kullanılanlar** şeridinde (`localStorage`) kalıyor.
- **Her ekrandan sürükle-bırak**: İşler, Ayarlar ve Ana Sayfa'da dosya pencereye sürüklenince buzlu cam bırakma katmanı açılıyor ve dosya türüne göre doğru araca yönlendiriliyor.
- **Renk kodlu kıvrık köşeli dosya rozetleri**: PDF, Word, Excel, Sunu, Resim ve Markdown dosyaları tek bakışta renk ve biçimle ayrılıyor.
- **Modern geçiş ve geri bildirimler**: Bölümler arası `View Transitions API` geçişleri, `<dialog>` ve komut paletinde `@starting-style` + `allow-discrete` animasyonları, yelpaze gibi açılan bırakma illüstrasyonu, çalışan iş çubuğunda parıltı, tamamlanınca çizilerek beliren SVG onay işareti ve Sıkıştır ekranında önce/sonra görsel tasarruf çubuğu.

### İyileştirilenler & Sadeleştirilenler
- **Sıcak Atölye görsel dili**: Soğuk gri tuval yerine sıcak fildişi zemin (`#f6f4ef`), koyu temada ince üst ışık kenarları, buzlu cam üst çubuk (`backdrop-filter`) ve 3B tuş görünümlü `<kbd>` kısayolları.
- **Ana sayfa dengesi**: *Dönüştür* grubu tam genişlikte öne çıkarılıp **Biçim Dönüştür** vurgulu ana kart yapıldı; 6 kutuluk statik "Bırakınca ne olur?" bloğu tek satırlık açılır **Akıllı yönlendirme** çekmecesine sadeleştirildi.
- **Koyu tema & erişilebilirlik**: Önizleme kâğıdı koyu temada göz yormayan yumuşak kreme alındı; tekil odak/hover parlaklıkları, mobil (390 px) ve tablet (900 px) düzenleri sıfır yatay taşmayla doğrulandı.

## 0.12.2 — 2026-11-21

- **Masaüstü simgesi artık değişiyor**: 0.12.1'i kurunca masaüstünde eski turuncu "PDF" simgesi
  kalıyordu (Windows simgeyi dosya yoluna göre önbelleğe alıyor, yol aynıydı). Simge dosyasının
  adı artık sürümü taşıyor ve kurulum Windows'un simge önbelleğini yeniliyor.
- **Görev çubuğu simgesi keskin**: bulanık görünüyordu; artık her boyut için ayrı çizilmiş simge
  kullanılıyor.
- **Pencerenin başlık çubuğu temayı izliyor**: uygulamada koyu temayı seçince başlık çubuğu da
  koyu oluyor (önce Windows açık temadaysa koyu sayfanın üstünde beyaz bir şerit kalıyordu).

## 0.12.1 — 2026-11-21

- **Yeni simge**: turuncu "PDF" simgesinin yerine Toolia'nın kelebeği (masaüstü, Başlat, Gönder
  menüsü, "Uygulamalar" listesi, tarayıcı sekmesi ve uygulamanın üst çubuğu). Kanatlar
  uygulamadaki dört araç grubunun renginde.
- **Daha küçük paket**: indirilen zip 301 → 230 MB, kurulu hâli 755 → 618 MB. Kullanılmayan
  parçalar (bir kütüphanenin kapalı tuttuğumuz yapay zekâ modülü, video desteği) artık pakete
  girmiyor; hiçbir özellik değişmedi.

## 0.12.0 — 2026-11-20

PDF'in yanında artık biçim dönüştürme: fotoğraflar ve Office belgeleri. Uygulamanın yeni adı **Toolia** (eski adı PDF Atölyesi).

**Kurulum ve güncelleme**: yeni paketi indirip ayıkla, **Kur**'a çift tıkla. Eski sürümü
kaldırmaya gerek yok; belgelerin, imzaların ve ayarların korunur. Kurarken uygulama
penceresi kapalı olmalı. Masaüstündeki "PDF Atölyesi" simgesi "Toolia" olur (eskisi
kendiliğinden silinir).
Eski "PDF Atölyesi" kurulumu kendiliğinden kaldırılır; belgelerin, imzaların, şablonların
ve ayarların ilk açılışta yeni klasöre (`%LOCALAPPDATA%\Toolia`) taşınır.

### Yeni araç: Biçim Dönüştür
- **Resimler**: JPG, PNG, WEBP, HEIC (iPhone), GIF, TIFF, BMP → JPG, PNG, WEBP ya da TIFF.
  Telefon fotoğrafları doğru yönde çıkar; saydam resim JPG'e giderken saydam yerler seçtiğin
  renkle (varsayılan beyaz) dolar; JPG/WEBP'te kalite ayarlanır. Hareketli GIF'in yalnız ilk
  karesi alınır (söylenir).
- **Office belgeleri** (LibreOffice ile, aynı tür içinde): Word ↔ DOCX, ODT, RTF, TXT; Excel ↔
  XLSX, ODS, CSV; PowerPoint ↔ PPTX, ODP. Eski `.doc`, `.xls`, `.ppt` dosyalarını yeni biçime
  çevirmek de bununla olur.
- CSV, Türkçe Excel'de çift tıklayınca doğru açılır (`;` ayraç, ğ/ş/ı bozulmaz). Birden çok
  sayfalı kitaptan CSV'ye yalnız ilk sayfa gider; bu söylenir.
- Parolalı bir Office belgesi beklemeden "parola korumalı" hatası verir.
- Birden çok dosya birlikte çevrilir; biri bozuksa diğerleri yine çevrilir.

### Yeni yollar
- Ana sayfaya resim ya da Office belgesi bırakınca "PDF'e çevir" ya da "Başka biçime
  dönüştür" diye sorulur.
- İşler ve dosyalar'da uygun her dosyada **Dönüştür…** düğmesi.
- Sağ tık → Gönder → **JPG'ye çevir**: HEIC/PNG/WEBP fotoğrafları uygulamayı açmadan JPG
  yapar, dosyanın yanına yazar.

### Düzeltmeler
- Sayfa aralığı yazarken: "1 3" artık sessizce 13. sayfa olmuyor, hata veriyor; tek başına
  "-" hata; "HEPSİ" ve "tümü" her yazılışta tanınıyor; çok büyük sayılar ve "²" gibi
  karakterler çökme yerine anlaşılır hata veriyor.

## 0.11.0 — 2026-11-17

Yeni görünüm, yeni araç (Sayfa Düzeni ve Yazdırma), Markdown şablonları ve telefon modunun
tek tıkla açılması.

**Kurulum ve güncelleme**: yeni paketi indirip ayıkla, **Kur**'a çift tıkla. Eski sürümü
kaldırmaya gerek yok; belgelerin, imzaların ve ayarların korunur. Kurarken PDF Atölyesi
penceresi kapalı olmalı.

### Yeni görünüm
- Arayüz baştan tasarlandı: ferah açık zemin, her araç grubunun kendi rengi ve ikonu, daha
  okunur yazı tipi. **Açık / koyu tema** düğmesi üst çubukta (seçmezsen Windows'un temasını
  izler).
- Üst menü sayfayı kaydırınca da yerinde kalıyor. **Araçlar**'ın yanındaki ok, 16 aracın hepsini
  her ekrandan açıyor; **Araç ara** (Ctrl+K ya da `/`) yazarak araca götürüyor.
- Ana sayfada **Son dosyalar** ve bir dosyayı bırakınca hangi aracın açılacağı görünüyor.
- Bir iş başka ekrandayken biterse üst çubukta "1 iş bitti" yazıyor.
- Araç ekranları aynı düzende: solda dosyalar ve seçenekler, sağda özet ve büyük eylem
  düğmesi; sonuç kartında dosya adları artık kesilmiyor.

### Yeni araç: Sayfa Düzeni ve Yazdırma
- Bir kağıda birden çok sayfa (N-up), ders slaytlarının yanına çizgili not alanı, kenar kırpma ve
  büyük sayfayı birkaç A4'e bölerek poster basma.

### Markdown → PDF
- **Şablon ekle** menüsü: 14 hazır şablon (ders notu başlığı, ödev / lab raporu, tanım, teorem,
  örnek ve çözüm, soru – cevap, dikkat ve özet kutuları, 2 sütunlu sınav özeti, numaralı formül,
  tablo, kod, görev listesi, sayfa sonu).
- **Kendi şablonların**: editörde bir metni seç (ya da seçmeden notun tamamını) ve "şablon
  olarak kaydet"; sonra tek tıkla eklenir. Yeniden adlandırılabilir, silinebilir. Şablonlar
  belgelerin yanında `sablonlar` klasöründe `.md` dosyaları olarak durur, temizlikte silinmez.
- **Formülleri onar** düğmesi: ChatGPT gibi araçlardan yapıştırılan `\( … \)` ve `\[ … \]`
  formüllerini `$ … $` biçimine çevirir (Ctrl+Z ile geri alınır). Önizleme bu formülleri onarmadan
  da doğru çiziyor.
- Yeni "2 sütunlu sınav özeti" düzeni. Obsidian'daki `[[#Başlık]]` bağlantıları PDF'te o başlığa
  götüren tıklanır bağlantı oluyor.

### Telefon modu
- Ayarlar'da telefon modunu açınca ne olacağını anlatan bir pencere çıkıyor; **Aç ve yeniden
  başlat** deyince uygulama birkaç saniyede kendini yeniden başlatıyor ve QR kod görünüyor.
  Artık "baslat.bat'ı çalıştır" gibi bir adım yok.
- Wi-Fi Windows'ta "Ortak ağ" olarak görünüyorsa telefon bağlanamaz; pencere bunu ve nasıl
  düzeltileceğini anlatıyor.

### Düzeltmeler
- **Klasörde göster** her dosyada Belgeler klasörünü açıyordu; artık dosyanın klasörünü açıp
  dosyayı seçili gösteriyor.
- Şifre penceresi açılınca yazmaya doğrudan şifre alanında başlanıyor.
- Büyük ya da bozuk dosyalarda çökme ve bellek sorunları giderildi; sayfa düzenleyicide
  kaydetme sürerken ikinci bir kaydetme başlamıyor; büyük PDF'lerde küçük resimler daha hızlı.
- Koyu temada açılışta bir an beyaz ekran görünmüyor.

## 0.10.0 — 2026-11-08

Yeni araçlar: PDF → Word ve PDF → Excel; A0'a kadar kağıt.

**Kurulum ve güncelleme**: yeni paketi indirip ayıkla, **Kur**'a çift tıkla. Eski sürümü
kaldırmaya gerek yok; belgelerin, imzaların ve ayarların korunur. Kurarken PDF Atölyesi
penceresi kapalı olmalı.

### Yeni araçlar
- **PDF → Word**: yazı, paragraf, tablo ve resimler düzenlenebilir bir Word belgesine (.docx)
  aktarılıyor. Sayfa aralığı seçilebiliyor.
- **PDF → Excel**: PDF'teki tablolar (çizgili ya da çizgisiz) Excel dosyasına (.xlsx) yazılıyor.
  Sayfadan sayfaya süren tablo tek tablo olarak birleşiyor; "1.234,56" gibi tutarlar Excel'de
  toplanabilir sayı oluyor, telefon / hesap numarası ve tarihler olduğu gibi kalıyor.

### Büyük kağıtlar
- Resim → PDF ve Markdown → PDF'te **A2, A1 ve A0** kağıt seçilebiliyor (önce en büyüğü A3'tü).
- PDF → Resim A0 paftayı 300 DPI'da da çıkarabiliyor; sayfa çok büyükse seçilebilecek en yüksek
  DPI söyleniyor.

### Diğer
- Sayfa düzenleyicide büyük önizlemeyi Esc ile kapatıp hemen oklarla başka sayfaya geçince
  klavye odağı bazen önizlenen sayfaya geri sıçrıyordu; artık geçtiğin sayfada kalıyor.
- Linux'ta kaynak koddan çalışma (README'de "Linux" bölümü).

## 0.9.1 — 2026-11-07

İlk arkadaş denemesinden gelenler ve ürün deneyimi.

**Kurulum ve güncelleme**: yeni paketi indirip ayıkla, **Kur**'a çift tıkla. Eski sürümü
kaldırmaya gerek yok; belgelerin, imzaların ve ayarların korunur. Kurarken PDF Atölyesi
penceresi kapalı olmalı.

### Büyük dosyalar
- Dosya başına sınır 1 GB'tan **8 GB**'a çıktı (tek seferde toplam 16 GB).
- Çok büyük bir dosya sınırı aşarsa sayfa düzenleyici artık bunu söylüyor (önce hiçbir şey
  olmuyordu).
- Sayfa düzenleyici büyük PDF'lerde yalnızca ekranda görünen sayfaları yüklüyor; 2 GB'lık
  dosyanın tamamı tarayıcı belleğine çekilmiyor.

### Sıkıştırma
- **Güçlü** sıkıştırma taranmış/pafta dosyalarında çok daha hızlı (248 MB'lık örnekte 2,5 dk →
  30 sn) ve ilerlemeyi gösteriyor; uzun işlerde geçen süre yazıyor.
- Bütün seviyeler gömülü yazı tiplerini küçültüyor: yazı ağırlıklı PDF'ler belirgin biçimde daha
  çok küçülüyor (örnekte %20 → %61), kalite ve metin aynı kalıyor.
- Dosya az küçüldüyse nedeni söyleniyor (ör. "dosyanın çoğu yazı; büyük kazanç beklenmez").

### Ayarlar ve ilk açılış
- Ayarlar ekrandan değişiyor: dosyaların saklanma süresi, Obsidian kasası (Klasör seç…),
  Markdown için varsayılan tema ve kağıt, telefon modu. Geliştirici bilgileri "Gelişmiş" altında.
- Telefon modu masaüstü uygulamasından açılıyor; port ya da telefon modu değişince uygulama
  pencere kapanmadan yeniden başlıyor.
- İlk açılışta kısa tanıtım ve eksik bir şey varsa (ör. LibreOffice) ne yapılacağı.

### Kullanım
- Bir ekran hata verirse beyaz sayfa yerine açıklama ve hata kimliği çıkıyor.
- Markdown önizlemesi yazarken kaydığın yerde kalıyor.
- İşler ve dosyalar: bütün işlerin adı Türkçe, dosyalar yeniden adlandırılabiliyor, "Klasörde
  göster"; telefonda dosya listesi kart düzeninde.
- Sayfa düzenleyici yalnızca klavyeyle de kullanılabiliyor (oklar, Boşluk, Alt+oklarla taşıma).

### Lisans
- PDF Atölyesi GNU AGPL v3 ile lisanslı (LICENSE).

## 0.9.0 — 2026-11-07

İlk masaüstü paketi: tek dosyadan kurulum, kendi penceresinde çalışan uygulama, gömülü OCR
(Türkçe + İngilizce) ve Ghostscript.
