import { useEffect, useState } from "react";
import { api, type EnginesResponse } from "./api";
import Home from "./pages/Home";
import Jobs from "./pages/Jobs";
import Settings from "./pages/Settings";

type Route = "araclar" | "isler" | "ayarlar";

const NAV: { route: Route; label: string }[] = [
  { route: "araclar", label: "Araçlar" },
  { route: "isler", label: "İşler" },
  { route: "ayarlar", label: "Ayarlar" },
];

function currentRoute(): Route {
  const hash = window.location.hash.replace(/^#\/?/, "");
  return NAV.some((n) => n.route === hash) ? (hash as Route) : "araclar";
}

export default function App() {
  const [route, setRoute] = useState<Route>(currentRoute);
  const [engines, setEngines] = useState<EnginesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    const onHash = () => setRoute(currentRoute());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const loadEngines = async (refresh = false) => {
    setRefreshing(true);
    try {
      setEngines(await api.engines(refresh));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => {
    void loadEngines();
  }, []);

  return (
    <div className="shell">
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
              className={route === n.route ? "active" : undefined}
              aria-current={route === n.route ? "page" : undefined}
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
            Sunucuya ulaşılamadı: {error}
          </div>
        )}
        {route === "araclar" && <Home engines={engines} />}
        {route === "isler" && <Jobs />}
        {route === "ayarlar" && (
          <Settings data={engines} refreshing={refreshing} onRefresh={() => loadEngines(true)} />
        )}
      </main>
    </div>
  );
}
