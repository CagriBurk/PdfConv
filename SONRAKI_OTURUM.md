# PDF Atölyesi — ürünleşme: Faz D (otonom çalışma)

Proje: `C:\Users\cbura\Desktop\Conv` — PDF Atölyesi (FastAPI + React/TS/Vite, PyMuPDF/pikepdf;
LibreOffice, Tesseract, Ghostscript, Edge). Remote: github.com/CagriBurk/PdfConv (açık depo).
Önce oku: `PLAN.md` (§8 tuzaklar #1–58, §10.1 yol haritası, §10.2 kullanıcı kararı bekleyenler,
Faz A/B/C notları), `README.md`.

## Durum
- Faz A (güven), Faz B (sağlamlık) ve Faz C (masaüstü paketi) bitti, `main`'de, CI yeşil.
- Faz C: `paket/derle.py` → `build/PdfAtolyesi-<sürüm>.zip` (imzalı gömülü Python + bağımlılıklar
  + arayüz + Tesseract/Ghostscript + Noto). `Kur.cmd` → `%LOCALAPPDATA%\Programs\PdfAtolyesi`,
  uygulama `pythonw -m pdfatolye uygulama` (Edge `--app` penceresi). Sürüm 0.9.0.
- Testler: `uv run python -m pytest` (~400 test, e2e dahil, ~4 dk).

## Bu makineye özgü (mutlaka bil)
- Akıllı Uygulama Denetimi açık: her zaman `uv run python -m pytest`, `uv run python -m ruff check .`,
  `uv run python -m pdfatolye ...`. İmzasız, indirilmiş .exe engellenir (tuzak #52).
- Shell PowerShell 5.1 (Bash aracı da var). Bash aracında heredoc `\\`'yi `\`'ye çeviriyor
  (tuzak #50): ters eğik çizgili betik/JSON'u Write aracıyla yaz. Commit mesajını dosyaya yaz,
  `git commit -F`.
- `gh` yok. CI durumu: `Invoke-RestMethod "https://api.github.com/repos/CagriBurk/PdfConv/actions/runs?head_sha=<sha>" -Headers @{'User-Agent'='pdfatolye-ci-check'}`;
  başarısız iş için kimliksiz `.../check-runs/<job id>/annotations` (betikler hatayı `::error::`
  ile yazar). Günlükler kimlik ister; git'teki kimlik bilgilerini kullanma.
- CI windows-latest: cp1252 konsol (Türkçe yazdırmadan önce UTF-8'e çevir, dosyalarda
  `encoding="utf-8"`), LibreOffice/Tesseract/Ghostscript yok. pwsh'tan çağrılan powershell.exe'de
  `PSModulePath`'i temizle (tuzak #57).
- `%LOCALAPPDATA%\PdfAtolye` gerçek veri klasörüm: testlerde ve denemelerde HER ZAMAN geçici
  `data_dir`; silme içeren testte yolun `tmp_path` altında olduğunu iddia et (tuzak #58).
- Bu makinede PyPI çok yavaş: `uv sync`/paket derlemesi uzun sürebilir; arka planda çalıştır.
- Playwright'ta `page.route_web_socket` ve `wait_for_function("dize")` kullanma (CSP engeller;
  `expect(locator)` kullan). Takılan denemede yalnızca kendi başsız Edge süreçlerini kapat
  (`--pa-isaret` ya da `--headless` geçenler); komut satırında kendi süreç kimliğini hariç tut.

## Çalışma kuralları
1. `main`'den `faz-d-deneyim` dalı aç, mantıklı commit'ler, Türkçe mesaj, sonunda attribution.
2. Her hata düzeltmesi regresyon testiyle gelir; düzeltmeyi kodu değiştirmeden geçici olarak
   devre dışı bırakıp (monkeypatch / eski kodu derleyip) testin kırmızıya döndüğünü gör.
3. Bitti demeden: ruff temiz, `npm --prefix web run build` başarılı, tam test paketi geçiyor;
   arayüz değiştiyse başsız Edge ile 1400 px ve 390 px ekran görüntüsü al, yatay taşma olmasın.
4. Faz bitince `main`'e birleştir, `git push origin main`, CI'ın iki işi de (test, paket) yeşil
   olsun. Force push yok.
5. PLAN: Faz D notları, yeni tuzaklar #59'dan, §10.1'de ✅. README'de kullanıcıyı etkileyenler.
6. Ücretli bir şey yok; kullanıcı kararı gerekenler §10.2'ye, beklemeden devam.

## Faz D — Ürün deneyimi
- Ayarlar düzenlenebilir olsun (saklama süresi, Obsidian kasa yolu, varsayılan tema/kağıt,
  port, telefon modu): şu an salt okunur ve `config.toml` gerektiriyor; masaüstü kullanıcısı
  dosya düzenlemez. Ayarlar `data_dir/config.toml`'a yazılsın (kurulu pakette proje kökü yok).
  Telefon modu ekranı "baslat.bat --lan" diyor: masaüstü kurulumu için düzelt. Geliştirici
  bilgilerini (kütüphane sürümleri, yollar) "Gelişmiş" altına al.
- İlk açılış akışı: motor durumu, eksikse ne yapılacağı (LibreOffice'i kur düğmesi var), kısa tanıtım.
- React hata sınırı (ErrorBoundary) + genel bildirim (toast); beyaz sayfa olmasın.
- Markdown önizlemesi her güncellemede başa atlıyor (srcdoc yeniden yükleniyor): kaydırma
  konumunu koru ya da içeriği yerinde güncelle; gecikmiş önizleme yanıtları sırayı bozmasın.
- İşler ekranında tür adları Türkçe (`Jobs.tsx` `TYPE_LABEL` eksik: merge dışındakiler,
  `install_engine` dahil), dosya yeniden adlandırma arayüzü (API var), "klasörde göster"
  (yalnızca loopback).
- Klavye ve ekran okuyucu erişilebilirliği: sayfa düzenleyicide klavyeyle seçim, odak yönetimi.
- `vitest` (en azından `editor/model.ts`, `router.ts`, `passwords.ts`, `drafts.ts`) ve `eslint`;
  CI'a bağla.
- Ana sayfada kalan "Faz N" etiket mantığını temizle (`tools.ts` `phase`, `Home.tsx`).
- Bittiğinde: paketi yeniden üret (`uv run python paket/derle.py`), geçici veri klasörüyle kur,
  aç, ekran görüntüsü al.

## Bittiğinde
Türkçe kısa rapor: commit'ler, CI bağlantıları, neyi nasıl doğruladın, yapamadıkların, §10.2
için benden ne istediğin, sonraki adım tek cümle.
