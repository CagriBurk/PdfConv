# Toolia kullanım kılavuzu

Kısa tanıtım ve hızlı kurulum: [README](../README.md).

## Ekranlar

| Ekran | Ne yapar |
|---|---|
| Ana sayfa | Dosyayı bırakınca türüne göre doğru araç açılır. Araçlar yıldızla sabitlenir; `Ctrl+K` komut paletini açar. |
| Biçim Dönüştür | PDF → PNG / JPG / Word / Excel; resim → JPG / PNG / WEBP / TIFF / PDF (HEIC dahil); Word, tablo ve sunum biçimleri arasında dönüştürme. Office dönüşümleri LibreOffice ister. |
| Sayfa düzenleyici | Sürükleyerek sıralama, döndürme, silme, başka PDF'ten sayfa ekleme, geri/ileri alma. Tamamen klavyeyle de kullanılır. |
| İçerik Ekle | Yazı, resim, imza, vurgu, şekil ve karartma. Karartma, kutunun altındaki içeriği dosyadan gerçekten siler. |
| Markdown → PDF | Canlı önizleme, temalar, LaTeX formüller, Obsidian sözdizimi. Yazılan not tarayıcıda taslak olarak saklanır. |
| Birleştir, Böl, Filigran, Sayfa Numarası | Önizlemeli ayrı ekranlar; çok dosyalı çıktılar tek ZIP olarak iner. |
| Sıkıştır | Kayıpsız, dengeli ve güçlü seviyeler; önce-sonra boyutu gösterilir, dosya büyürse orijinal korunur. |
| OCR | Taranmış PDF'i Türkçe + İngilizce aranabilir yapar; metni olan sayfaları atlar. |
| Güvenlik ve bakım | AES-256 şifreleme, şifre kaldırma, meta veri temizliği, bozuk PDF onarımı. |
| İşler ve dosyalar | Son işler ve dosyalar. Sabitlenmeyen dosyalar 24 saat sonra silinir (süre Ayarlar'dan değişir). Çalışan iş "İptal" ile durur. |

Her düzenleme yeni bir sürüm oluşturur; "Önceki sürüme dön" ile geri alınır. Kaydedilmemiş bir
iş varken ekrandan çıkmak önce onay ister. Şifreli PDF'lerin şifresi yalnızca açık sekmenin
belleğinde tutulur.

## Güvenlik

- Markdown ve HTML baskısında ağ tamamen kapalıdır: belge internete veri gönderemez, diskteki
  başka dosyaları okuyamaz, ağdaki başka bilgisayarlara bağlanamaz.
- LibreOffice her dönüşümde makroları kapalı, taze bir profille çalışır.
- Ağ çıkışını ölçmek için: `uv run python tests/guvenlik/ag_cikisi.py` (bütün dönüşümleri
  çalıştırıp ağ bağlantılarını izler).
- Bilinen istisna: Microsoft Edge kendi Microsoft hizmetlerine bağlanabiliyor. Bu bağlantıda
  belgenin içeriği yoktur (ölçüldü). Diğer motorlar hiç bağlanmaz.

Ayrıntılar: [GUVENLIK_PLANI.md](../GUVENLIK_PLANI.md).

## Komut satırı

Çıktı yolu (`-o`) verilmezse dosya girdinin yanına yazılır; var olan dosyanın üstüne yazılmaz.
Sayfa aralıkları 1'den sayar: `1-3, 5, 8-`, `son`, `5-1` (ters sıra).

```
uv run python -m toolia birlestir a.pdf b.pdf -o hepsi.pdf
uv run python -m toolia sec not.pdf "3,1,2"                 # sırala / sayfa çıkar
uv run python -m toolia bol not.pdf --mod aralik --aralik "1-3, 4-"
uv run python -m toolia sikistir *.pdf --seviye dengeli      # kayipsiz | dengeli | guclu
uv run python -m toolia ocr tarama.pdf
uv run python -m toolia sifrele not.pdf --kopyalama-yok
uv run python -m toolia cevir rapor.docx                     # Office / HTML / metin → PDF
uv run python -m toolia cevir a.docx b.xlsx --birlestir      # tek PDF, dosya başına yer imi
uv run python -m toolia donustur IMG_1234.heic --hedef jpg
uv run python -m toolia md not.md --tema rapor --icindekiler # Markdown → PDF
```

Bütün komutların listesi: `uv run python -m toolia --help`; bir komutun ayrıntısı:
`uv run python -m toolia <komut> --help`.

### Markdown ayarları

Notun ön bilgisinde verilebilir (komut satırındaki değer önceliklidir):

```yaml
---
title: Devre Analizi
pdf:
  tema: ders          # ders | rapor | sade
  kagit: A4
  icindekiler: true
  kapak: true
---
```

Desteklenenler: satır içi ve blok formüller, `\ce{...}` kimya formülleri, Obsidian callout'ları,
`[[not]]` bağlantıları ve `![[resim.png]]` gömmeleri, kod renklendirme, tablo, dipnot, görev
listesi. Hatalı bir formül baskıyı durdurmaz; satır numarasıyla uyarı verir.
Örnek not: [ornekler/ders-notu.md](../ornekler/ders-notu.md).

## Ayarlar

Ayarlar ekranından değişir ve `%LOCALAPPDATA%\Toolia\config.toml` dosyasına yazılır. Ekranda
olmayanlar (yükleme sınırları, motor yolları, veri klasörü) bu dosyadan değiştirilir; açıklamalı
örnek: `config.example.toml`.

## Telefondan kullanmak

1. **Ayarlar → Telefon modu** kutusunu işaretle ve **Aç ve yeniden başlat**'a bas.
2. Ayarlar sayfasında çıkan QR kodu telefonun kamerasıyla okut.

QR kod tek kullanımlık ve 10 dakika geçerlidir. Telefonun oturumu eşleştiği ağ adresine bağlıdır
ve 8 saat sonra kapanır. Telefon yalnızca kendi yüklediği dosyaları görür. Bağlantı yerel ağda
şifresizdir (HTTP): yalnızca güvendiğin Wi-Fi'de aç. Windows Wi-Fi'yi "Ortak ağ" olarak
görüyorsa telefon bağlanamaz; güvendiğin ağı "Özel" yap.

## Sorun giderme

- **Hata kimliği:** Beklenmeyen bir hatada mesajda bir kimlik yazar (ör. `3fa2c1b9`). Aynı
  kimlik `%LOCALAPPDATA%\Toolia\logs\toolia.log` dosyasında ayrıntısıyla bulunur.
- **Diskte yer yok:** Yükleme sırasında dosyanın iki katı kadar boş yer gerekir. Dosya başına
  sınır 8 GB'tır (`max_upload_mb`).
- **Port kullanımda:** Masaüstü uygulaması boş bir port seçer. Geliştirme sunucusunda:
  `baslat.bat --port 8800`.
- **Uzun klasör yolu:** Yol 260 karakteri geçerse LibreOffice ve Ghostscript bozulabilir;
  projeyi kısa bir yola (ör. `C:\Toolia`) koy.

## Kaynak koddan kurulum (Windows)

```
winget install astral-sh.uv
winget install OpenJS.NodeJS.LTS
winget install TheDocumentFoundation.LibreOffice
winget install UB-Mannheim.TesseractOCR
git clone https://github.com/CagriBurk/Toolia.git
cd Toolia
```

- **Türkçe OCR:** `tur.traineddata` dosyasını
  [tessdata_fast](https://github.com/tesseract-ocr/tessdata_fast) deposundan indirip
  `C:\Program Files\Tesseract-OCR\tessdata\` içine kopyala.
- **Ghostscript:** [ghostpdl-downloads](https://github.com/ArtifexSoftware/ghostpdl-downloads)
  sürümlerinden `gs*w64.exe` dosyasını kısa bir klasöre indirip çalıştır.
- **Çalıştır:** `baslat.bat` bağımlılıkları kurar, arayüzü derler ve `http://127.0.0.1:8790`
  adresini açar. Motorların durumu: `uv run python -m toolia motorlar`.
- **Kısayollar (isteğe bağlı):** `powershell -ExecutionPolicy Bypass -File kurulum\kisayollar.ps1`
  masaüstüne Toolia simgesini ve sağ tık → Gönder menüsüne "PDF'e çevir" ile "JPG'ye çevir"
  seçeneklerini ekler.

Komutlar `python -m toolia` biçimindedir, çünkü Windows'un Akıllı Uygulama Denetimi uv'nin
ürettiği `toolia.exe` başlatıcısını engelleyebilir.

### Linux

Masaüstü paketi yalnızca Windows içindir; Linux'ta uygulama kaynak koddan tarayıcıda çalışır.

```
sudo apt install tesseract-ocr tesseract-ocr-tur ghostscript libreoffice-writer libreoffice-calc libreoffice-impress chromium
curl -LsSf https://astral.sh/uv/install.sh | sh
git clone https://github.com/CagriBurk/Toolia.git && cd Toolia
uv sync && npm --prefix web install && npm --prefix web run build
uv run python -m toolia serve
```

### Paketi üretmek

`uv run python paket/derle.py` komutu `build/Toolia-<sürüm>.zip` paketini üretir. Tesseract ve
Ghostscript bu bilgisayardaki kurulumdan alınır; `--motorsuz` bayrağı onları pakete koymaz.
