import { lazy, Suspense, useEffect, useState } from "react";
import { api, errorMessage, type EnginesResponse } from "./api";
import Home from "./pages/Home";
import Jobs from "./pages/Jobs";
import Markdown from "./pages/Markdown";
import Merge from "./pages/Merge";
import { ImagesToPdf, PdfToImages } from "./pages/Images";
import Settings from "./pages/Settings";
import Split from "./pages/Split";
import { useRoute } from "./router";

// pdf.js büyük; yalnızca düzenleyici açılınca yüklensin.
const Organizer = lazy(() => import("./pages/Organizer"));

const NAV = [
  { route: "araclar", label: "Araçlar" },
  { route: "isler", label: "İşler ve dosyalar" },
  { route: "ayarlar", label: "Ayarlar" },
];

export default function App() {
  const route = useRoute();
  const [ready, setReady] = useState(false);
  const [engines, setEngines] = useState<EnginesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

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
        return loadEngines();
      })
      .catch((e) => setError(`Sunucuya ulaşılamadı: ${errorMessage(e)}`));
  }, []);

  const [page, id] = route.path;
  const section = page ?? "araclar";
  const current = NAV.some((n) => n.route === section) ? section : "araclar";

  let content;
  if (!ready) content = null;
  else if (section === "duzenle")
    content = (
      <Suspense fallback={<p className="muted">Düzenleyici yükleniyor…</p>}>
        <Organizer key={id ?? "yeni"} fileId={id} />
      </Suspense>
    );
  else if (section === "birlestir") content = <Merge route={route} />;
  else if (section === "bol") content = <Split route={route} />;
  else if (section === "md") content = <Markdown route={route} engines={engines} />;
  else if (section === "resimden") content = <ImagesToPdf route={route} />;
  else if (section === "resme") content = <PdfToImages route={route} />;
  else if (section === "isler") content = <Jobs />;
  else if (section === "ayarlar")
    content = <Settings data={engines} refreshing={refreshing} onRefresh={() => loadEngines(true)} />;
  else content = <Home engines={engines} />;

  return (
    <div className={`shell${section === "duzenle" || section === "md" ? " wide" : ""}`}>
      <header className="topbar">
        <a className="brand" href="#/araclar">
          <span className="brand-mark" aria-hidden="true" />
          PDF Atölyesi
        </a>
        <nav>
          {NAV.map((n) => (
            <a
              key={n.route}
              href={`#/${n.route}`}
              className={current === n.route && NAV.some((x) => x.route === section) ? "active" : undefined}
            >
              {n.label}
            </a>
          ))}
        </nav>
        <span className="offline-badge" title="Dosyalar bu bilgisayardan çıkmaz">
          Çevrimdışı
        </span>
      </header>
      <main>
        {error && (
          <div className="banner error" role="alert">
            {error}
          </div>
        )}
        {content}
      </main>
    </div>
  );
}
