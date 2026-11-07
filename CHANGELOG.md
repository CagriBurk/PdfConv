# Değişiklikler

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
