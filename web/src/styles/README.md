# Arayüz stil kılavuzu ("Sıcak Atölye" yenilemesi — 2026-11-21)

Bağlayıcı kurallar tasarım sözleşmesinde; bu belge ortak temelin kullanım kılavuzudur. Burada
yazılan her sınıf, belirteç ve bileşen kodda gerçekten var. 2026-11-21 `arayuz-revizyon` dalında
önceki "Ferah" temeli üzerine sıcak malzeme paleti, buzlu cam üst çubuk, renk kodlu dosya rozetleri,
kategori süzgeci/favoriler, genel sürükle-bırak katmanı ve `prefers-reduced-motion` uyumlu modern
geçişler eklendi.

## Dosyalar ve basamak sırası

`src/styles.css` yalnızca sıralı `@import` listesidir; sonraki dosya öncekini ezer.

| Dosya | İçerik |
| --- | --- |
| `01-temel.css` | Yazı tipi, belirteçler (açık/koyu), temel öğeler, ortak sınıflar, yönetim ekranı yapı taşları, bırakma alanı, ana sayfa |
| `02-araclar.css` | Araç ekranı yerleşimi ve ortak denetimler: kartlar, alanlar, sekme / bölmeli düğme, seçim kartı, dosya satırı, küçük resim kutusu |
| `03-duzenleyici.css` | Araç çubuğu (düzenleyici + editör), sayfa ızgarası |
| `04-is-paneli.css` | İş paneli (`JobPanel`) |
| `05-modal.css` | Pencere (`Modal`, `PasswordDialog`; ilk odak `data-autofocus`, `busy` iken kapanmaz) |
| `06-markdown.css` | Markdown stüdyosu |
| `07-isler.css` | İşler ve dosyalar, boş durum, dosya tablosu |
| `08-editor-filigran.css` | İçerik editörü, imza penceresi, filigran ve sayfa numarası |
| `10-ayarlar-karsilama.css` | Ayarlar, karşılama, bildirim, hata ekranı, atlama bağlantısı |
| `11-palet.css` | Kabuk: sayfa genişliği, üst çubuk, araç menüsü, araç ekranı başlığı (`PageHeader`), komut paleti |
| `12-yazdirma.css` | Sayfa Düzeni ve Yazdırma |

Ortak sınıfı bir ekrana göre değiştirmek istiyorsan kapsamla (`.layout-card .seg-track { … }`),
ortak kuralı ezme. Birden çok ekranın kullandığı kural ortak dosyada (01 / 02) durur.

## Renk belirteçleri

Değerler sözleşmede. Bileşene sabit renk gömme; hep `var(--…)`. İstisnalar: vurgu zemini
üstündeki yazı/ikon `#fff`, gölge ve perde `rgb(… / alfa)`.

| Belirteç | Ne zaman |
| --- | --- |
| `--bg` | Sayfa zemini (yalnızca `body`) |
| `--surface` | Kart, panel, girdi, açılır pencere zemini |
| `--surface-2` | Kart içinde ikincil zemin: satır üzerine gelme, nötr rozet, bilgi kutusu, tuval masası |
| `--border` | Kart ve ayırıcı çizgileri |
| `--border-strong` | Girdi kenarı, kesikli bırakma alanı, düğmenin üzerine gelme kenarı |
| `--text` / `--muted` | Ana metin / ikincil metin (ikisi de her zeminde ≥ 4.5:1) |
| `--accent` | Dolu vurgu: birincil düğme zemini, seçili kenar |
| `--accent-text` | Vurgu renginde YAZI ve ikon (bağlantı, seçili sekme). Koyu temada `--accent` yazı olarak okunmaz |
| `--accent-soft` | Seçili satır / etkin öğe zemini |
| `--accent-faint` | Çok hafif vurgu zemini (bırakma alanı, seçili kart) |
| `--ok` `--warn` `--bad` + `-soft` | Durum yazısı + aynı tonun zemini; hep çift kullan (`.chip.ok` gibi) |
| `--g1-bg/fg` … `--g4-bg/fg` | Araç grubu tonu; doğrudan değil `.g1`…`.g4` ile |
| `--paper` `--paper-ink` `--paper-shadow` | Kâğıt: PDF sayfası, imza, karekod zemini. Açık temada saf beyaz, koyu temada göz yormayan yumuşak krem (`#f3f1eb`) |
| `--shadow` / `--inset-top` | Kart gölgesi ve ince üst yüzey ışığı (koyu temada derinlik hissi verir) |
| `--ease-spring` / `--ease-out` | Dokunsal mikro-etkileşim ve üst katman geçiş eğrileri (yalnızca `prefers-reduced-motion: no-preference` altında etkin) |

Diğerleri: `--radius-sm` 8px, `--radius` 12px, `--radius-lg` 18px, `--page-max` (1240px; geniş
çalışma ekranlarında 1500px), `--topbar-h` (aşağıda), `--font`, `--mono`.

## Yeni ortak bileşen ve geçiş kalıpları (`arayuz-revizyon`)

- **Buzlu cam üst çubuk (`.topbar`)**: `backdrop-filter: blur(14px) saturate(140%)`; `theme-color` meta rengi yine `--surface` (`#ffffff` / `#161a22`) ile eşleşir.
- **Renk kodlu kıvrık köşeli dosya rozeti (`.ftype.ft-*`)**: `fileTypeTone()` (`FilePicker.tsx`) ile `ft-pdf`, `ft-doc`, `ft-sheet`, `ft-slide`, `ft-img`, `ft-md`, `ft-other` sınıfları verilir.
- **Ana sayfa kontrolleri**: `.route-drawer` (açılır akıllı yönlendirme çekmecesi), `.home-filter` (kategori süzgeci), `.fav-strip` / `.fav-pill` / `.tool-fav` (sık kullanılan araçlar).
- **Genel sürükle-bırak katmanı (`.global-drop`)**: Pasif ekranlarda pencereye dosya sürüklenince açılan tam ekran buzlu cam katman (`GlobalDropOverlay.tsx`).
- **Üst katman & sayfa geçişleri**: `<dialog class="modal">` (`05-modal.css`) ve `<dialog class="cmd-palette">` (`11-palet.css`) `@starting-style`, `overlay` ve ayrı `transition-behavior: allow-discrete` ile animasyonlanır; bölüm geçişleri `router.ts` içinde `document.startViewTransition` kullanır (hızlı geçiş `AbortError` bastırılır, `prefers-reduced-motion: reduce` altında devre dışıdır).

## Yapışkan üst çubuk ve sayfa içi yapışkanlar

- Üst çubuk (`.topbar`) hep yapışkan (`top: 0`, opak zemin, `z-index: 40`). ≤ 760px'te iki satırdır;
  aşağı kaydırınca yalnızca gezinme satırı (Araçlar, tüm araçlar, İşler, Ayarlar) üstte kalır
  (`top: -52px`), marka / arama / tema ilk satırla kayar. 761–1000px'te tek satıra sığsın diye arama
  ve rozet yalnız ikon.
- `--topbar-h`: çubuğun **yapışık kalan** yüksekliği (geniş ekranda 73px, dar ekranda 67px).
  `TopBar` ölçüp `<html>`'e yazar (sarılma, yakınlaştırma, rozet); `01-temel.css`'teki değer yalnız
  ilk boyama için.
- Sayfa içinde yapışkan bir öğe eklersen ofseti buna bağla: `top: calc(var(--topbar-h) + 16px)`;
  ekran boyundan hesaplanan yükseklikte de düş: `max-height: calc(100vh - var(--topbar-h) - …)`.
  Sabit `top: 16px` yazma; öğe çubuğun altına girer.
- Katman sırası: sayfa içi yapışkanlar ≤ 20 < üst çubuk 40 (araç menüsü 41, perdesi 39) <
  bildirimler 90 < "İçeriğe geç" 100; `<dialog>` (pencere, komut paleti) zaten en üst katmanda.
- `html { scroll-padding-top }` çubuğun altını boş bırakır: sekmeyle odaklanan öğe, sayfa içi
  bağlantı ve `scrollIntoView` başlığı çubuğun altına sokmaz.

## Tema

- `<html data-theme="light|dark">`; öznitelik yoksa sistem tercihi. Koyu değerler `01-temel.css`'te
  iki kez yazılı (medya sorgusu + öznitelik); temaya göre değişen yeni belirteci İKİ yere de ekle.
- `src/theme.ts`: `useTheme()`, `setTheme("dark")`, `storedTheme()`, `applyTheme()`. Seçim
  `localStorage` `pa-tema`. İlk boyamadan önce `public/tema.js` uygular (CSP satır içi betiğe izin
  vermez; `<head>`'de engelleyici yüklenir), `main.tsx` yeniden uygular. Bileşende temaya göre dal
  açma; belirteç kullan.

## Tipografi

Tek aile: Plus Jakarta Sans (pakette, latin + latin-ext). `--mono` yalnızca kod, yol, sürüm.

| Öğe | Ölçü |
| --- | --- |
| Sayfa başlığı (`h1`) | 28px / 750 / -0.02em (ana sayfa ve yönetim ekranı 30px; çalışma ekranı 22px) |
| Bölüm / kart başlığı (`h2`) | 17px / 700 / -0.01em (büyük bölüm 22px / 750) |
| Grup başlığı (`h3`) | 15px / 700 (araç grubu 13.5px) |
| Gövde | 15px / 1.5 (`body`) |
| Açıklama | 13–14px, `--muted` |
| Yardımcı / rozet | 12.5–13px (`.small` 13px) |

## Boşluk, köşe, dokunma

- Kart: köşe 18px (`.card`; kahraman kartı 20px), iç boşluk 22px (dar ekranda 16–18px).
- Düğme ve girdi: 40px (`.small` 32px, eylem düğmesi 48px), köşe 10px.
- Liste satırı: iç boşluk 8–10px, köşe 12px, üzerine gelince `--surface-2`.
- Dokunma hedefi ≥ 40px: dar ekranda (≤ 640px) ve dokunmatikte küçük denetimler 40px'e büyür
  (`@media (pointer: coarse), (max-width: 640px)`). 360px'te yatay kaydırma olmamalı.

## Temel öğeler (`01`)

| Sınıf | Görünüm |
| --- | --- |
| `button`, `.button` | Kenarlıklı yüzey düğmesi, 40px |
| `.primary` | Dolu vurgu, beyaz yazı (ekranda tek ana eylem) |
| `button.danger` | Kırmızı yazılı, kırmızımsı kenarlı (geri alınamaz eylem) |
| `.small` | 32px sık düğme |
| `.link-button` | Bağlantı görünümlü düğme (`--accent-text`); `.danger` kırmızı |
| `.icon-button` | Yalnız ikonlu, zeminsiz 40×40; `.outline` kenarlıklı. `aria-label` zorunlu |
| `.text-link` | Altı çizgisiz vurgu bağlantısı ("Tümünü gör") |
| `.input`, `select` | 40px, `--border-strong` kenar |
| `.banner.error` / `.banner.warn` | Hata / uyarı bandı (blok; içinde ikonla yan yana dizmek için kapsamlı `display: flex`) |
| `.muted` `.small` `.mono` `.center` `.block` `.break` `.error-text` `.warn-line` `.sr-only` | Yardımcılar |

Odak halkası her yerde `:focus-visible` (2px `--accent-text`); kendi bileşeninde `outline: none` yazma.

```jsx
<section className="card">…</section>                      // yüzey + kenar + 18px köşe + gölge
<span className="chip ok">Hazır</span>                      // rozet: .ok .warn .bad .accent, .small 24px
<span className={`tile ${tool.tone}`}><Icon icon={tool.icon} /></span>  // ikon kutusu: .sm .lg, ton .g1–.g4
<span className="dot g2" aria-hidden="true" />             // grup rengi nokta
<kbd>Ctrl</kbd>  <button className="kbd-button" aria-label="Kapat (Esc)">Esc</button>
<span className="ftype" aria-hidden="true">PDF</span>      // dosya türü rozeti (FilePicker.fileType)
<Icon icon={LoaderCircle} className="spin" />              // döner (azaltılmış harekete saygılı)
```

Yönetim ekranları (İşler, Ayarlar): başlık `header.screen-head` (`h1` 30px + açıklama), kart başlığı
`.section-head` (`h2` + sağda eylem), motor listesi `.engine*`, anahtar-değer `dl.kv`; boş durum
`.empty-state` (`.tile.lg` + `.empty-title` + açıklama + düğme; `07`).

## Araç ekranı (`02`) ve bileşenleri

```tsx
<PageHeader title="Sıkıştır" />
<div className="tool-layout">                 // solda içerik, sağda 340px eylem sütunu; ≤ 900px alt alta
  <div className="tool-main">                 // kartlar alt alta (20px)
    <FilesCard count={files.length} hint="…">  // section.card.tool-files: .card-head (h2 + sayı), .card-hint
      <ul className="file-list"><li><FileRow file={f} onRemove={…} /></li></ul>
      <FilePicker accept={ACCEPT.pdf} kind="pdf" compact={files.length > 0} title="…" onAdd={…} />
    </FilesCard>
    <section className="card">…seçenekler…</section>
  </div>
  <aside className="tool-side">               // yapışkan sütun (üst çubuğun altında)
    <ActionCard rows={[["Dosya", filesSummary(files, "PDF")]]} note="…" label="Sıkıştır" onRun={…} />
    <JobPanel job={job.job} error={job.error} summary={…} />
  </aside>
</div>
```

- `FilePicker.tsx`: varsayılan `FilePicker` (yükleme + tür + şifre), `FilesCard`, `FileRow`
  (`.file-row` > `.ftype` + `.file-text` [`.file-name` tek satır, `.file-meta`] + çıkar düğmesi),
  `fileType(ad, tür)` (rozet metni), `fileSummary(dosya)` ("12 sayfa · 2.3 MB"),
  `filesSummary(dosyalar, "PDF")` ("2 PDF · 26.8 MB").
- `JobPanel.tsx`: varsayılan `JobPanel` (`job`, `error`, `zipName`, `summary` = bitince başlığın
  altındaki kısa sonuç) ve `ActionCard` (`section.options`: "Özet" `dl.summary`, `.side-note`,
  `button.primary.action`; ikon aracın kendisi). Çıktı satırında ad tam genişlikte, eylemler
  (`.output-actions`) altında; yalnız "İndir" varsa ya da liste 520px'ten genişse tek satır.
- `.options`: sağ sütun kartı, ilk öğesi `h2` başlık ("Özet", "Seçenekler"; editörde seçili nesnenin
  türü ya da "Özellikler"). Seçenekleri kendi yan panelinde tutan ekranlar (Filigran, Sayfa
  Numarası, editör özellikleri) da aynı kartı kullanır; içindeki `JobPanel` gölgesiz iç kutuya döner.
- Alanlar: `.fields` (otomatik ızgara), `label.field` (etiket üstte), `.field.inline`,
  `fieldset.field.plain` (kenarsız grup) + `.checks` (yan yana onay kutuları), `label.check`.
- Seçim: `.radio-cards` > `label.radio-card(.on)` > `.radio-card-head` (`strong` + `.radio-dot`).
- Sekme / bölmeli düğme: `.tabs` / `.segmented` (seçili `button.on`); gri raylı görünüm için
  `+ .seg-track` (Filigran türü, hizalama, imza sekmeleri, Sayfa Düzeni). Dar ekranda 40px.
- Küçük resim: `.thumb-box` (kare, içindeki `img` kâğıt gibi) + `.thumb-placeholder`.
- Diğer: `.summary`, `.side-note`, `.tool-intro`, `.install-engine`, `.sortable-list/grid`, `.image-tile`.

## İşler: dosya tablosu (`07`)

`table.file-table`: ad hücresi `.file-cell` (`.ftype` + `.file-cell-text` [`.file-cell-name`,
`.file-cell-meta`]), ölçü hücreleri `td[data-label]`, eylemler `td.row-actions` (yalnız ikonlu
düğmeler; her birinde `aria-label` + `title`). ≤ 860px'te tablo kart yığınına döner (`data-label`
etiket olarak yazılır); yatay kaydırma yok.

## İkonlar

`lucide-react`, her zaman `components/Icon.tsx` üzerinden: `<Icon icon={Download} />` (18px,
`aria-hidden`); anlam taşıyorsa `label="…"`. Adla içe aktar; `Image`/`File` yerine
`ImageIcon`/`FileIcon`. Emoji ve karakter-ikon yerine ikon. Araç ikonu ve tonu tek kaynaktan:
`src/tools.ts` (`TOOLS`, `GROUPS`, `GROUP_TONE`, `toolForRoute`).

## Kabuk bileşenleri

- `PageHeader title="…"`: konum çubuğu ("Araçlara dön" / grup / araç), tonlu ikon kutusu, `h1`,
  açıklama; `children` sağda (dar ekranda altta).
- `DropZone`: `compact` araç ekranlarında, `hero` yalnızca ana sayfa; bütün alan tek düğme.
- Üst çubuk (`TopBar`), araç menüsü (`ToolMenu`), komut paleti, iş rozeti, son dosyalar
  (`RecentFiles`): `App.tsx` / ana sayfa kurar. İş rozeti `hooks.ts` `useJob`'dan beslenir.

## Yapma

- Sabit hex renk, gradyan, emoji, sol kenarı renkli kart; `--accent`'i yazı rengi yapmak.
- Soluk gri üstüne soluk gri. `div`'e `onClick`. Yalnız ikonlu düğmede `aria-label`'ı unutmak.
- Test seçicilerini (sözleşmede listeli sınıflar, görünür adlar) yeniden adlandırmak.
- Dış kaynak (CDN, Google Fonts, uzak görsel).
- Kullanılmayan sınıf bırakmak: işaretlemeyi kaldırınca kuralını da kaldır.
