# Güvenlik sertleştirme planı (2026-11-21)

Dal: `guvenlik-sertlestirme` (worktree: `C:\Users\cbura\Desktop\Conv-guvenlik`). `main` ve
`C:\Users\cbura\Desktop\Conv` klasörüne dokunulmaz: orada başka bir ajan arayüz üzerinde çalışıyor.

## Çalışma kuralları

1. **Önce kanıt, sonra düzeltme.** Her adım zararsız bir kavram kanıtıyla (PoC) başlar. Açık
   doğrulanmazsa düzeltme yazılmaz, adım "doğrulanmadı" diye kapanır.
2. Her düzeltmenin PoC'yi otomatikleştiren bir **regresyon testi** olur (`tests/test_guvenlik_*.py`).
3. Denemeler yalnızca geçici klasörde yapılır (`LOCALAPPDATA` scratchpad'e yönlendirilir). Gerçek
   `%LOCALAPPDATA%\Toolia` klasörüne dokunulmaz. Ağ denemeleri yalnızca 127.0.0.1 üzerindeki
   dinleyiciyle yapılır.
4. Her adım ayrı commit olur. Commit'ten önce şunlar çalışır: ruff, tam pytest, vitest (arayüz
   değiştiyse) ve build.
5. **Arayüz (`web/`) dosyalarına en az dokunulur.** Dokunmak gerekirse adımda ayrıca yazılır;
   birleştirmeden önce diğer ajanın değişiklikleriyle çakışma kontrol edilir.
6. Dal bitince `main`'e `--no-ff` ile birleştirilir ve yeni sürüm (0.13.0) çıkar. Kullanıcı onay
   vermeden birleştirme yapılmaz.

## Adımlar (önem sırasıyla)

### Adım 1 — Gönder menüsü: dosya adıyla komut çalıştırma 🔴
- **Sorun:** `pdfe-cevir.cmd` ve `jpge-cevir.cmd` dosya yollarını `%*` ile cmd.exe'ye veriyor.
  Gezgin, boşluk içermeyen yolları tırnak içine almıyor. Bu yüzden `x&calc&.pdf` adlı dosya
  komut çalıştırabilir.
- **Kanıt:** `deneme&calc&.pdf` dosyası hazırlanır. Kullanıcı Gezgin'de bu dosyayı seçip
  Gönder → PDF'e çevir der. Hesap makinesi açılırsa açık doğrulanmış olur.
- **Düzeltme:** Gönder kısayolları `.cmd` yerine doğrudan `python.exe -I -m toolia gonder --bekle`
  komutunu çalıştırır. Gezgin argümanları CreateProcess ile verir, arada cmd olmaz. Hata olunca
  pencerenin açık kalmasını (`pause`) Python sağlar (`--bekle`). Paketten iki `.cmd` dosyası
  kaldırılır; kurulum eski kısayolların üzerine yazar. Geliştirme ortamındaki `.bat` dosyaları ve
  `kurulum/kisayollar.ps1` aynı biçime getirilir.
- **Test:** `&`, `^`, `%`, `!` ve `,` içeren dosya adlarıyla `gonder`; kısayol hedefinin `.cmd`
  olmadığının denetimi.
- **Dosyalar:** `paket/derle.py`, `src/toolia/kurulum.py`, `src/toolia/cli.py`, `*.bat`,
  `kurulum/kisayollar.ps1`.

### Adım 2 — LibreOffice: dış bağlantılar, makrolar, yerel dosya okuma 🔴
- **Sorun:** Her çağrıda açılan taze profil LibreOffice'in varsayılanlarıyla geliyor:
  `BlockUntrustedRefererLinks=false`, `MacroSecurityLevel=2`, `DisableMacrosExecution=false`.
  Ağ tarafında da hiçbir kısıt yok.
- **Kanıt:** 127.0.0.1'de bir HTTP dinleyicisi açılır. Aşağıdaki belgeler Toolia'nın kendi
  dönüştürme işleviyle çevrilir:
  - (a) uzak resim içeren docx;
  - (b) uzak resim içeren odt;
  - (c) yerel dosyaya bağlı bölüm (`section-source`) içeren odt;
  - (d) `WEBSERVICE()` içeren xlsx;
  - (e) DDE bağlantısı içeren belge;
  - (f) dış şablon bağlantısı (`attachedTemplate`) içeren docx;
  - (g) Basic makrolu docm/odt.

  Dinleyiciye istek gelmesi ya da yerel dosyanın metninin PDF'te görünmesi açığı doğrular.
- **Düzeltme (iki katman):**
  1. Taze profile çalışmadan önce bir `registrymodifications.xcu` yazılır. İçeriği:
     - makrolar tümüyle kapalı (`DisableMacrosExecution=true`, `MacroSecurityLevel=3`);
     - `BlockUntrustedRefererLinks=true`;
     - Writer ve Calc'ta "bağlantıları güncelle" seçeneği `asla`.
  2. Kanıt hâlâ sızıntı gösterirse: çeviriden önce kopya üzerinde dış hedefler temizlenir.
     OOXML'de `TargetMode="External"` ilişkileri, ODF'de pakete ait olmayan `xlink:href`
     değerleri kaldırılır. Kullanıcıya "dış bağlantılar çevrimdışı olduğu için yüklenmedi"
     uyarısı gösterilir.
- **Test:** (a)–(g) belgelerinin hepsi dinleyiciye sıfır istekle ve yerel dosya metni olmadan
  çevrilir. LibreOffice kurulu değilse test atlanır (CI'da yok).
- **Dosyalar:** `src/toolia/convert/office.py` (ve gerekirse yeni `convert/office_temizle.py`).

### Adım 3 — HTML → PDF: `file://SUNUCU/` ile izin denetiminden kaçma 🟠
- **Sorun:** `browser.file_url_path` URL'nin sunucu adını (`netloc`) atıyor. Belgedeki betik
  `location.href` ile kendi yolunu öğrenip `file://saldirgan/C:/.../kendisi.html` adresini
  kurabilir. Denetim bunu "kendi dosyası" sanır. Tarayıcı bu adresi UNC/SMB olarak açarsa
  bağlantı proxy'yi atlar: NTLM özeti sızar ve "dosyalar internete çıkmaz" vaadi bozulur.
- **Kanıt:** `route` kararları kaydedilir; bu adrese izin verildiği gösterilir. Edge'in dışarı
  bağlanmaya çalışıp çalışmadığı süreç bağlantıları izlenerek ölçülür. Bunun için yönlendirilemeyen
  belgeleme adresi (192.0.2.1) kullanılır; dışarıya gerçekten bir şey gitmez.
- **Düzeltme:** `netloc` boş ya da `localhost` değilse ve yol UNC biçimindeyse (`\\`) adres
  reddedilir. Aynı denetim Markdown baskısında da geçerli olur. Ek olarak tarayıcıya
  `--disable-file-system`-benzeri ek bayraklar uygulanabilir mi araştırılır.
- **Test:** `file://host/...`, `file:////host/...`, `file://localhost/...`, `%5C%5Chost` gibi
  kodlanmış biçimler için birim testleri, ayrıca gerçek tarayıcıyla bir uçtan uca test.
- **Dosyalar:** `src/toolia/convert/browser.py`.

### Adım 4 — Ağ çıkışı denetimi: "dosyalar internete çıkmaz" vaadinin ölçülmesi 🟠
- Bütün dönüşüm türleri (PDF araçları, OCR, sıkıştırma, Office, HTML, MD, resim) sırayla
  çalıştırılır. Bu sırada `python`, `soffice.bin`, `gswin64c`, `tesseract` ve `msedge` süreçlerinin
  TCP/UDP bağlantıları izlenir.
- 127.0.0.1 dışında bir bağlantı görülürse ayrı bir adım olarak düzeltilir.
- Çıktı: tekrar çalıştırılabilir bir betik (`tests/guvenlik/ag_cikisi.py`, elle çalıştırılır).

### Adım 5 — Telefon modu (LAN) 🟠 — **kullanıcı kararı gerekiyor**
- **Sorun:** Bağlantı düz HTTP. Eşleştirme belirteci URL'de, oturum çerezi ve dosyalar Wi-Fi'de
  şifresiz gidiyor. Cihaz oturumu IP'ye bağlı değil ve süresi dolmuyor. Eşleşmiş cihaz bütün
  dosyaları görüyor.
- **Kanıt:** Bir cihaz eşleştirilir, çerezi başka bir istemciden (başka IP taklidiyle) kullanılır
  ve bütün dosyaların listelenip indirilebildiği gösterilir.
- **Önerilen düzeltme (arayüze az dokunur):**
  1. Cihaz oturumu eşleştiği IP'ye bağlanır.
  2. Oturumların süresi dolar (ör. 8 saat).
  3. Telefon modu belirli bir süre sonra kendiliğinden kapanır.
  4. Eşleşmiş cihaz yalnızca kendi yüklediği dosyaları ve onlardan üretilenleri görür.
  5. Ayarlar'da "yalnızca güvendiğin ağda aç" uyarısı gösterilir.
- **Seçenek:** HTTPS (kendinden imzalı sertifika). Telefonlar sertifika uyarısı gösterir;
  kullanıcı deneyimini bozar. Kararı kullanıcı verir.
- **Dosyalar:** `api/security.py`, `api/app.py`, `storage.py` (dosyanın sahibi alanı), Ayarlar
  sayfasında küçük bir metin.

### Adım 6 — Bağımlılık ve motor açıkları 🟡
- `pip-audit` (uv.lock) ve `npm audit` (web) çalıştırılır; bulunan açıklar için sürümler
  yükseltilir.
- Paketteki Ghostscript 10.08, Tesseract 5.4 ve kullanıcının kurduğu LibreOffice sürümü CVE
  listeleriyle karşılaştırılır. Motor taramasına **en düşük güvenli sürüm** denetimi eklenir:
  eski LibreOffice ya da Ghostscript varsa Ayarlar'da uyarı gösterilir.
- Paketteki Python 3.11.9, artık ikili güvenlik sürümü almayan bir dal. Daha yeni bir gömülü
  Python'a geçiş araştırılır (ayrı karar).
- CI'a `pip-audit` ve `npm audit --omit=dev` işleri eklenir.

### Adım 7 — Kaynak tüketme (DoS) 🟡
- **Kanıt:** zip bombası docx/xlsx, 100 000 sayfalık PDF, dev boyutlu ve bozuk HEIC, iç içe
  KaTeX formülü, çok sayıda eşzamanlı iş. Uygulama ayakta kalıyor mu, bellek ve disk ne oluyor?
- **Düzeltme (gerekirse):** Office kapsayıcılarında açılmış toplam boyut ve sıkıştırma oranı
  sınırı; PDF sayfa sınırı; eşzamanlı ağır iş sınırı.

### Adım 8 — Yerel sunucu sertleştirmesi 🟢
- Origin denetimi yalnızca host'a değil, tam kökene (şema + host + port) bakar. Arayüzün yeniden
  başlatmadan sonraki yoklaması (`restart.ts`) GET olduğu için etkilenmez; yine de denenir.
- Paylaşılan makineler (RDP, çok kullanıcılı): yerel bağlantıya otomatik oturum veriliyor. Windows'ta
  bağlanan sürecin sahibi denetlenebilir mi araştırılır; olmazsa README'de açıkça belgelenir.
- Uygulamanın kendi API'sine karşı genel testler: çerezsiz, sahte Host'lu ve sahte Origin'li
  istekler, dosya kimliği oynama, sürüm (`v=`) oynama, ZIP adı.

### Adım 9 — Dağıtım bütünlüğü 🟢
- Release'e `SHA256SUMS.txt` eklenir; README'ye ve OKUBENI'ye "indirdiğin zip'i nasıl doğrularsın"
  bölümü yazılır.
- Kod imzalama sertifikası: maliyet ve fayda notu (karar kullanıcının).

## Durum

| Adım | Kanıt | Düzeltme | Test | Commit |
|---|---|---|---|---|
| 1 Gönder menüsü | ✅ doğrulandı (calc açıldı) | ✅ | ✅ `test_guvenlik_gonder.py` | f21010b; Gezgin'de yeniden denendi ✅ |
| 2 LibreOffice | ❌ doğrulanmadı (26.8 sızdırmadı) | derinlemesine savunma | ✅ `test_guvenlik_office.py` | bu commit |
| 3 HTML file://host | ✅ doğrulandı (SMB SYN → 192.0.2.1:445) | ✅ | ✅ `test_guvenlik_html.py` | bu commit |
| 4 Ağ çıkışı | ⚠️ belge içeriği çıkmıyor; Edge'in kendi Microsoft trafiği var | karar bekliyor | `tests/guvenlik/ag_cikisi.py` | bu commit |
| 5 Telefon modu | ✅ (testler eski kodda kalıyor) | ✅ A | ✅ `test_guvenlik_lan.py` | bu commit |
| 6 Bağımlılıklar | – | – | – | – |
| 7 DoS | – | – | – | – |
| 8 Yerel sunucu | – | – | – | – |
| 9 Dağıtım | – | – | – | – |

## Notlar

- **Adım 1, kalan küçük risk:** Geliştirici kurulumundaki `baslat.bat` hâlâ `%*` aktarıyor; README
  `baslat.bat --lan` / `--port` kullanımını belgeliyor. Yalnızca geliştirme kurulumunda (paket
  değil) ve masaüstündeki "Toolia" simgesinin üstüne bir dosya sürüklenirse etkili. Paketteki
  masaüstü kısayolu doğrudan `pythonw.exe`'yi çalıştırır, bu sorundan etkilenmez.
- **Adım 1, güncellemeye etkisi:** Kurulum her güncellemede klasörü silip yeniden kopyalar ve
  kısayolları baştan yazar. Bu yüzden eski `pdfe-cevir.cmd` / `jpge-cevir.cmd` dosyaları ve onlara
  giden kısayollar 0.13.0'a güncellenince kendiliğinden gider. **0.12.x kullanan herkes
  güncellemeli;** o zamana kadar Gönder menüsü yalnızca güvenilen dosyalarda kullanılmalı.
- **Adım 2, kanıt sonucu (LibreOffice 26.8.2.2):** Uzak resimli ODT, yerel dosyaya bağlı
  bölümlü ODT, WEBSERVICE'li ODS ve XLSX, LibreOffice'in kendi ürettiği dış ilişkili
  (`TargetMode="External"`) resimli DOCX, `INCLUDEPICTURE`'lı DOCX ve RTF: 127.0.0.1'deki
  dinleyiciye **sıfır istek**, kanarya metni PDF'e **girmedi**. Bağlantılar `.fodt` çıktısında
  duruyordu, yani belgeler geçerliydi; LibreOffice başsız dönüşümde onları yüklemiyor (yerel
  resmi bile). `INCLUDEPICTURE` alanını hiç içe almıyor. Açılışta çalışan Basic makrosu
  çalışmadı; ancak makro güvenliği düşük profilde de çalışmadığı için bu kontrol **belirsiz**
  kaldı (`--convert-to` açılış olaylarını tetiklemiyor olabilir).
- **Adım 2, yapılan:** Bulgu doğrulanmadığı hâlde, ucuz olduğu ve kullanıcının kurduğu LibreOffice
  sürümünün varsayılanlarına güvenilemeyeceği için taze profile ayarlar açıkça yazılıyor:
  makrolar kapalı, `BlockUntrustedRefererLinks`, Writer/Calc bağlantı güncelleme "asla", Calc
  açılışta yeniden hesaplama "asla". Kalan önlem adım 6'da: en düşük güvenli LibreOffice sürümü
  denetimi. Belgedeki dış hedefleri çeviriden önce temizleme (planlanan 2. katman) gerekmedi.
- **Adım 3, kanıt (Edge, `print_html(confine=True)` — arayüzün kullandığı yol):** Betik
  `file://192.0.2.1` + `location.pathname` istedi; denetim izin verdi; Windows (System, PID 4)
  192.0.2.1:445'e SMB bağlantısı açmaya çalıştı (`SYN_SENT`). Markdown baskısı da aynı açığı
  taşıyordu (ham `<img src="file://SUNUCU/<notun resminin yolu>">`; testle gösterildi).
  Düzeltme: sunucu adı boş ya da `localhost` olmayan `file:` adresleri reddedilir. Testler eski
  kodda kalıyor, yeni kodda geçiyor; 192.0.2.1'e bağlantı yok.
- **Adım 4, ölçüm (`tests/guvenlik/ag_cikisi.py`, 12 dönüşüm türü):** PyMuPDF, Ghostscript,
  OCR (ocrmypdf + Tesseract), pdf2docx, openpyxl, Pillow ve LibreOffice **hiç dışarı
  bağlanmadı**. Belgenin kendi dış istekleri (HTML'de http/https resim, CSS, fetch, WebSocket,
  sendBeacon, `file://SUNUCU`; Markdown'da uzak resimler) **engellendi**.
  **Ama Edge, her baskıda ana süreçten `outlook.office365.com` / `substrate.office.com`
  (40.101.x, 40.104.x, 52.97.x) adreslerine HTTPS bağlantısı açıyor**; düz metin baskısında da.
  Bu trafik Chromium'un ağ katmanında görünmüyor (ayrıntılı günlükte yok), Windows'un sistem
  ağ katmanından gidiyor; bu yüzden ölü proxy onu durdurmuyor. `--inprivate`, `--guest` ve
  `--disable-features=msImplicitSignin` işe yaramadı. Belge içeriği bu bağlantıda değil
  (belgenin bütün istekleri engelli), ama "uygulama internete bağlanmaz" vaadi Edge kullanıldığında
  tam değil. Edge'in ağ katmanından geçen kendi arka plan istekleri (Bing, `edge.microsoft.com`)
  proxy'de düşüyor. Karar kullanıcıda (seçenekler sohbette).
- **Adım 4, not:** İkinci bir `--disable-features` bayrağı Playwright'ın kendi listesini ezer
  (Chromium son değeri alır); Edge bayrağı eklenecekse iki liste birleştirilmeli.
- **Adım 5, karar:** A (IP'ye bağlı ve süreli oturum, kendiliğinden kapanma, cihaz yalnızca kendi
  dosyalarını görür, güvenilen ağ uyarısı); HTTPS şimdilik yok. Kullanım: şimdilik arkadaşlar,
  büyütme planlanıyor — müşterilere yayılmadan önce HTTPS yeniden değerlendirilmeli.
- **Adım 5, yapılan (A):** Cihaz oturumu eşleştiği IP'ye bağlı, 8 saat sonra düşer; QR 10 dakika
  geçerli (arayüz zaten 3 sn'de bir yeniliyor); bu bilgisayarın oturumu telefon modunda yalnızca
  loopback'ten geçerli. Yeni `toolia.access`: isteğin sahibi `SessionGuard`'da bağlama yazılır;
  depo (`get`/`list`) ve işler (`get`/`list`/`submit`) süzer, iş başlatanın kimliğiyle çalışır,
  çıktılar ona yazılır. Cihaz başkasının dosyasını, imzasını, işini göremez (404 / "İş
  bulunamadı"); Obsidian kasası cihaza kapalı. Temizlik her zaman tam erişimle çalışır (görünmeyen
  dosya "kayıtsız klasör" sanılıp silinmesin). Arayüze dokunulmadı: "şifresiz HTTP, yalnızca
  güvendiğin Wi-Fi" uyarısı Ayarlar'da zaten vardı.
- **Adım 5, plandan sapma:** "Telefon modu kendiliğinden kapanır" sunucuyu kapatmak yerine
  oturum ve QR süreleriyle sağlandı: 8 saat sonra hiçbir cihaz erişemez, sunucu yalnızca kilit
  sayfasını gösterir. Ayar dosyasındaki `lan = true` kullanıcının seçimi olduğu için değiştirilmedi.
- **Adım 5, kalan:** Trafik hâlâ şifresiz (ağı dinleyen, aktarılan dosyaların içeriğini görebilir;
  aynı IP'yi taklit edebilen biri 8 saat içinde oturumu kullanabilir). Şablonlar (Markdown
  "Şablon ekle") cihazlarla ortak kaldı: düşük hassasiyet. Kullanıcı büyütmeyi planlıyor:
  müşterilere açılmadan önce HTTPS yeniden değerlendirilmeli.
