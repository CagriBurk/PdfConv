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
| 3 HTML file://host | – | – | – | – |
| 4 Ağ çıkışı | – | – | – | – |
| 5 Telefon modu | – | karar bekliyor | – | – |
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
