import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { api, errorMessage, type EnginesResponse, type SettingsResponse } from "./api";
import ErrorBoundary from "./components/ErrorBoundary";
import Toaster from "./components/Toaster";
import Home from "./pages/Home";
import Jobs from "./pages/Jobs";
import Markdown from "./pages/Markdown";
import Merge from "./pages/Merge";
import Office from "./pages/Office";
import Compress from "./pages/Compress";
import Ocr from "./pages/Ocr";
import Protect from "./pages/Protect";
import { ImagesToPdf, PdfToImages } from "./pages/Images";
import { PdfToExcel, PdfToWord } from "./pages/PdfToOffice";
import Settings from "./pages/Settings";
import Split from "./pages/Split";
import Welcome from "./pages/Welcome";
import { navigate, useRoute } from "./router";
import { toast } from "./toast";
import { TOOLS } from "./tools";

// pdf.js büyük; yalnızca düzenleyici açılınca yüklensin.
const Organizer = lazy(() => import("./pages/Organizer"));
const Editor = lazy(() => import("./pages/Editor"));
const Watermark = lazy(() => import("./pages/Watermark"));
const PageNumbers = lazy(() => import("./pages/PageNumbers"));

const NAV = [
  { route: "araclar", label: "Araçlar" },
  { route: "isler", label: "İşler ve dosyalar" },
  { route: "ayarlar", label: "Ayarlar" },
];

/** Ekranın başlığı (sekme / pencere başlığı; ekran okuyucu ekran değişimini buradan duyar). */
function titleFor(section: string): string {
  const nav = NAV.find((n) => n.route === section)?.label;
  const tool = TOOLS.find((t) => t.route === section)?.title;
  const name = nav ?? tool ?? (section === "araclar" ? "Araçlar" : null);
  return name ? `${name} · PDF Atölyesi` : "PDF Atölyesi";
}

export default function App() {
  const route = useRoute();
  const [ready, setReady] = useState(false);
  const [engines, setEngines] = useState<EnginesResponse | null>(null);
  const [settings, setSettings] = useState<SettingsResponse | null>(null);
  const [showWelcome, setShowWelcome] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const main = useRef<HTMLElement>(null);

  const loadEngines = async (refresh = false) => {
    setRefreshing(true);
    try {
      setEngines(await api.engines(refresh));
      setError(null);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => {
    // Oturum çerezi alınmadan API çağrıları reddedilir.
    api
      .session()
      .then(() => {
        setReady(true);
        api
          .settings()
          .then((s) => {
            setSettings(s);
            if (!s.values.welcome_done) setShowWelcome(true);
          })
          .catch(() => undefined);
        return loadEngines();
      })
      .catch((e) => setError(`Sunucuya ulaşılamadı: ${errorMessage(e)}`));
  }, []);

  // Yakalanmamış hata (ör. bir düğmenin işi): sessizce kaybolmasın, bildirim olarak görünsün.
  useEffect(() => {
    const onRejection = (e: PromiseRejectionEvent) => {
      if (e.reason instanceof Error) toast.error(e.reason.message);
    };
    window.addEventListener("unhandledrejection", onRejection);
    return () => window.removeEventListener("unhandledrejection", onRejection);
  }, []);

  const [page, id] = route.path;
  const section = page ?? "araclar";
  const current = NAV.some((n) => n.route === section) ? section : "araclar";
  const screenKey = `${section}/${id ?? ""}`;

  // Ekran değişince odak içeriğe: klavye ve ekran okuyucu kullanıcısı yeni ekranın başından başlar.
  const firstScreen = useRef(true);
  useEffect(() => {
    document.title = titleFor(section);
    if (firstScreen.current) {
      firstScreen.current = false;
      return;
    }
    // Yeni ekran odağı kendisi verdiyse (ör. tanıtım başlığı) ona dokunma.
    if (!main.current?.contains(document.activeElement)) main.current?.focus({ preventScroll: true });
  }, [screenKey, section]);

  const finishWelcome = () => {
    setShowWelcome(false);
    if (settings && !settings.values.welcome_done && settings.local) {
      api
        .saveSettings({ welcome_done: true })
        .then(setSettings)
        .catch(() => undefined);
    }
  };

  let content;
  if (!ready) content = null;
  else if (showWelcome && section === "araclar")
    content = <Welcome engines={engines} onRefresh={() => void loadEngines(true)} onDone={finishWelcome} />;
  else if (section === "duzenle")
    content = (
      <Suspense fallback={<p className="muted">Düzenleyici yükleniyor…</p>}>
        <Organizer key={id ?? "yeni"} fileId={id} />
      </Suspense>
    );
  else if (section === "editor")
    content = (
      <Suspense fallback={<p className="muted">Editör yükleniyor…</p>}>
        <Editor key={id ?? "yeni"} fileId={id} />
      </Suspense>
    );
  else if (section === "filigran")
    content = (
      <Suspense fallback={null}>
        <Watermark route={route} />
      </Suspense>
    );
  else if (section === "sayfa-no")
    content = (
      <Suspense fallback={null}>
        <PageNumbers route={route} />
      </Suspense>
    );
  else if (section === "sikistir") content = <Compress route={route} />;
  else if (section === "ocr") content = <Ocr route={route} engines={engines} />;
  else if (section === "guvenlik") content = <Protect route={route} />;
  else if (section === "birlestir") content = <Merge route={route} />;
  else if (section === "bol") content = <Split route={route} />;
  else if (section === "md") content = <Markdown route={route} engines={engines} />;
  else if (section === "office")
    content = <Office route={route} engines={engines} onEnginesChanged={() => void loadEngines(true)} />;
  else if (section === "resimden") content = <ImagesToPdf route={route} />;
  else if (section === "resme") content = <PdfToImages route={route} />;
  else if (section === "word") content = <PdfToWord route={route} />;
  else if (section === "excel") content = <PdfToExcel route={route} />;
  else if (section === "isler") content = <Jobs />;
  else if (section === "ayarlar")
    content = (
      <Settings
        data={engines}
        refreshing={refreshing}
        onRefresh={() => loadEngines(true)}
        settings={settings}
        onSettings={setSettings}
        onShowWelcome={() => {
          setShowWelcome(true);
          navigate("araclar");
        }}
      />
    );
  else content = <Home engines={engines} />;

  return (
    <div className={`shell${["duzenle", "md", "editor"].includes(section) ? " wide" : ""}`}>
      <a className="skip-link" href="#icerik" onClick={(e) => (e.preventDefault(), main.current?.focus())}>
        İçeriğe geç
      </a>
      <header className="topbar">
        <a className="brand" href="#/araclar">
          <span className="brand-mark" aria-hidden="true" />
          PDF Atölyesi
        </a>
        <nav aria-label="Ana menü">
          {NAV.map((n) => {
            const active = current === n.route && NAV.some((x) => x.route === section);
            return (
              <a key={n.route} href={`#/${n.route}`} className={active ? "active" : undefined} aria-current={active ? "page" : undefined}>
                {n.label}
              </a>
            );
          })}
        </nav>
        {settings?.running.lan ? (
          <a className="offline-badge lan" href="#/ayarlar" title="Aynı Wi-Fi'deki eşleşmiş cihazlar bağlanabilir">
            Telefon modu açık
          </a>
        ) : (
          <span className="offline-badge" title="Dosyalar bu bilgisayardan çıkmaz">
            Çevrimdışı
          </span>
        )}
      </header>
      <main id="icerik" ref={main} tabIndex={-1}>
        {error && (
          <div className="banner error" role="alert">
            {error}
          </div>
        )}
        <ErrorBoundary key={screenKey} where={screenKey}>
          {content}
        </ErrorBoundary>
      </main>
      <Toaster />
    </div>
  );
}
