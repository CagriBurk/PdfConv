import { Check, CircleX, Clock, LayoutGrid, LoaderCircle, Moon, Search, ShieldCheck, SlidersHorizontal, Smartphone, Sun } from "lucide-react";
import { useEffect, useLayoutEffect, useRef } from "react";
import { clearFinishedJobs, useJobActivity } from "../hooks";
import { setTheme, useTheme } from "../theme";
import { toolForRoute } from "../tools";
import BrandMark from "./BrandMark";
import Icon from "./Icon";
import ToolMenu from "./ToolMenu";

interface Props {
  section: string;
  /** Telefon modu (yerel ağ) açık mı. */
  lan: boolean;
  onSearch: () => void;
}

/** Bu oturumda başlatılan işlerin durumu; tıklayınca İşler ekranı. */
function JobBadge({ section }: { section: string }) {
  const { running, done, failed } = useJobActivity();

  // İşler ekranı biten işleri zaten gösteriyor: orada görülmüş sayılır.
  useEffect(() => {
    if (section === "isler" && (done || failed)) clearFinishedJobs();
  }, [section, done, failed]);

  let badge = null;
  if (running)
    badge = (
      <a className="chip accent" href="#/isler" title="İşlere git">
        <Icon icon={LoaderCircle} size={15} className="spin" />
        <span className="chip-label">{running === 1 ? "Çalışıyor…" : `${running} iş çalışıyor`}</span>
      </a>
    );
  else if (failed)
    badge = (
      <a className="chip bad" href="#/isler" title="İşlere git">
        <Icon icon={CircleX} size={15} />
        <span className="chip-label">{failed === 1 ? "1 iş başarısız" : `${failed} iş başarısız`}</span>
      </a>
    );
  else if (done)
    badge = (
      <a className="chip ok" href="#/isler" title="İşlere git">
        <Icon icon={Check} size={15} strokeWidth={2.4} />
        <span className="chip-label">{`${done} iş bitti`}</span>
      </a>
    );
  // Bölge hep yerinde: içerik değişince ekran okuyucu duyursun.
  return (
    <span className="job-status" aria-live="polite">
      {badge}
    </span>
  );
}

export default function TopBar({ section, lan, onSearch }: Props) {
  const theme = useTheme();
  const home = section === "araclar";
  // Araç ekranları da "Araçlar" altında sayılır (görsel olarak); `aria-current` yalnızca ana sayfada.
  const inTools = home || !!toolForRoute(section);
  const themeLabel = theme === "dark" ? "Açık temaya geç" : "Koyu temaya geç";
  const bar = useRef<HTMLElement>(null);

  // Çubuk yapışkan; yüksekliği dar ekranda, yakınlaştırmada ve rozet değişince değişir.
  // Sayfa içi yapışkan öğeler ve kaydırma boşluğu `--topbar-h`'yi kullanır.
  useLayoutEffect(() => {
    const el = bar.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const root = document.documentElement;
    // Dar ekranda çubuğun yalnızca alt satırı yapışık kalır (`top` eksi): görünen kısım ölçülür.
    const measure = () => {
      const stuck = el.getBoundingClientRect().height + Math.min(0, parseFloat(getComputedStyle(el).top) || 0);
      root.style.setProperty("--topbar-h", `${Math.ceil(stuck)}px`);
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    // Kırılma noktası geçilince yükseklik aynı kalıp `top` değişebilir.
    window.addEventListener("resize", measure);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", measure);
      root.style.removeProperty("--topbar-h");
    };
  }, []);

  return (
    <header className="topbar" ref={bar}>
      <div className="topbar-inner">
        <a className="brand" href="#/araclar">
          <BrandMark />
          Toolia
        </a>
        <nav aria-label="Ana menü" className="nav-tray">
          <span className={`nav-split${inTools ? " on" : ""}`}>
            <a className="nav-pill" href="#/araclar" aria-current={home ? "page" : undefined}>
              <Icon icon={LayoutGrid} size={16} />
              Araçlar
            </a>
            <ToolMenu section={section} />
          </span>
          <a
            className={`nav-pill${section === "isler" ? " on" : ""}`}
            href="#/isler"
            aria-current={section === "isler" ? "page" : undefined}
          >
            <Icon icon={Clock} size={16} />
            {/* Tek öğe: hapın `gap`'i sözcüklerin arasına girmesin. */}
            <span>
              İşler<span className="nav-long"> ve dosyalar</span>
            </span>
          </a>
          <a
            className={`nav-pill${section === "ayarlar" ? " on" : ""}`}
            href="#/ayarlar"
            aria-current={section === "ayarlar" ? "page" : undefined}
          >
            <Icon icon={SlidersHorizontal} size={16} />
            Ayarlar
          </a>
        </nav>
        <div className="topbar-end">
          <button
            type="button"
            className="search-btn"
            aria-label="Araç ara (Ctrl+K)"
            aria-keyshortcuts="Control+K Meta+K"
            onClick={onSearch}
          >
            <Icon icon={Search} size={17} />
            <span className="search-btn-label">Araç ara…</span>
            <kbd>Ctrl K</kbd>
          </button>
          <JobBadge section={section} />
          {lan ? (
            <a className="chip warn" href="#/ayarlar" title="Aynı Wi-Fi'deki eşleşmiş cihazlar bağlanabilir">
              <Icon icon={Smartphone} size={15} />
              <span className="chip-label">Telefon modu açık</span>
            </a>
          ) : (
            <span className="chip" title="Dosyalar bu bilgisayardan çıkmaz">
              <Icon icon={ShieldCheck} size={15} />
              <span className="chip-label">Çevrimdışı</span>
            </span>
          )}
          <button
            type="button"
            className="icon-button outline"
            aria-label={themeLabel}
            title={themeLabel}
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          >
            <Icon icon={theme === "dark" ? Sun : Moon} />
          </button>
        </div>
      </div>
    </header>
  );
}
