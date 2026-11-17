import { ArrowRight, ChevronRight } from "lucide-react";
import { useEffect, useState } from "react";
import type { EnginesResponse, FileMeta } from "../api";
import DropZone from "../components/DropZone";
import Icon from "../components/Icon";
import RecentFiles from "../components/RecentFiles";
import { useUpload } from "../hooks";
import { navigate } from "../router";
import { GROUP_TONE, GROUPS, TOOLS } from "../tools";

/** Bırakılan dosyaların türüne göre en uygun araca yönlendirir. */
function routeFor(files: FileMeta[]): string | null {
  const ids = (k: FileMeta["kind"]) => files.filter((f) => f.kind === k).map((f) => f.id);
  const md = files.find((f) => f.kind === "markdown");
  if (md) {
    const ek = files.filter((f) => f.id !== md.id).map((f) => f.id);
    navigate("md", ek.length ? { dosya: md.id, ek } : { dosya: md.id });
    return null;
  }
  const pdfs = ids("pdf");
  if (pdfs.length === files.length) {
    navigate(pdfs.length === 1 ? `duzenle/${pdfs[0]}` : "birlestir", pdfs.length > 1 ? { dosya: pdfs } : undefined);
    return null;
  }
  const imgs = ids("image");
  if (imgs.length === files.length) {
    navigate("resimden", { dosya: imgs });
    return null;
  }
  const docs = files.filter((f) => f.kind === "office" || f.kind === "html" || f.kind === "text");
  if (docs.length === files.length) {
    navigate("office", { dosya: docs.map((f) => f.id) });
    return null;
  }
  return "Bu dosya türleri birlikte işlenemiyor. PDF, resim ya da Markdown bırak.";
}

// `routeFor`un sırasıyla aynı: Markdown varsa yanındakiler eki sayılır.
const ROUTES: [string, string][] = [
  ["Tek PDF", "düzenleyicide açılır"],
  ["Birden çok PDF", "birleştirilir"],
  ["Resimler", "tek PDF olur"],
  ["Markdown (+ resimleri)", "PDF'e dönüşür"],
  ["Word, Excel, PowerPoint, HTML, TXT", "PDF olur"],
];

export default function Home({ engines, onSearch }: { engines: EnginesResponse | null; onSearch: () => void }) {
  const { upload, uploading, progress, error } = useUpload();
  const [notice, setNotice] = useState<string | null>(null);
  const [uploads, setUploads] = useState(0);

  // "/" araç aramasını (komut paleti) açar; yazı alanında ya da açık pencerede değilken.
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "/" && !e.ctrlKey && !e.metaKey && !e.altKey) {
        if (document.querySelector("dialog[open], .modal")) return;
        const target = e.target as HTMLElement | null;
        const tag = target?.tagName;
        if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || target?.isContentEditable) {
          return;
        }
        e.preventDefault();
        onSearch();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onSearch]);

  const missing = (keys: string[] = []) =>
    engines ? engines.engines.filter((e) => keys.includes(e.key) && !e.ok).map((e) => e.name) : [];

  const onFiles = async (files: File[]) => {
    setNotice(null);
    const metas = await upload(files);
    if (metas.length) {
      setUploads((n) => n + 1);
      setNotice(routeFor(metas));
    }
  };

  return (
    <div className="home">
      <div className="home-top">
        <section className="card home-hero" aria-labelledby="home-baslik">
          <div>
            <h1 id="home-baslik">Ne yapmak istersin?</h1>
            <p className="home-lead">Dosyayı bırak, uygun araç kendiliğinden açılsın. Hiçbir dosya bu bilgisayardan çıkmaz.</p>
          </div>
          <DropZone
            hero
            onFiles={onFiles}
            disabled={uploading}
            title={uploading ? `Yükleniyor… %${Math.round((progress ?? 0) * 100)}` : "Dosyayı buraya bırak"}
            hint="PDF, Word, Excel, PowerPoint, Markdown ya da fotoğraf · birden çok dosya olur"
          />
          {(error || notice) && (
            <div className="banner error" role="alert">
              {error ?? notice}
            </div>
          )}
          <div>
            <h2 className="home-sub" id="home-yonlendirme">
              Bırakınca ne olur?
            </h2>
            <ul className="route-list" aria-labelledby="home-yonlendirme">
              {ROUTES.map(([what, result]) => (
                <li key={what} className="route">
                  <b>{what}</b> <Icon icon={ArrowRight} size={14} /> {result}
                </li>
              ))}
            </ul>
          </div>
        </section>
        <RecentFiles retentionHours={engines?.retention_hours} refreshKey={uploads} />
      </div>

      <section aria-labelledby="home-araclar">
        <div className="home-tools-head">
          <div>
            <h2 id="home-araclar">Tüm araçlar</h2>
            <p className="muted">
              {TOOLS.length} araç, {GROUPS.length} başlıkta. Birine tıkla ya da dosyanı yukarı bırak.
            </p>
          </div>
          <p className="home-keys">
            Klavyeden <kbd>Ctrl</kbd>
            <kbd>K</kbd> ya da <kbd>/</kbd>
          </p>
        </div>
        <div className="tool-groups">
          {GROUPS.map((group) => {
            const tools = TOOLS.filter((t) => t.group === group);
            const tone = GROUP_TONE[group];
            return (
              <div key={group} className="card tool-group">
                <div className="tool-group-head">
                  <span className={`dot ${tone}`} aria-hidden="true" />
                  <h3 id={`grup-${tone}`}>{group}</h3>
                  <span className="tool-group-count" aria-hidden="true">
                    {tools.length}
                  </span>
                </div>
                <ul className="tool-list" aria-labelledby={`grup-${tone}`}>
                  {tools.map((t) => {
                    const lacking = missing(t.needs);
                    return (
                      <li key={t.id}>
                        <a className="tool-card active" href={`#/${t.route}`}>
                          <span className={`tile ${t.tone}`}>
                            <Icon icon={t.icon} size={19} strokeWidth={1.9} />
                          </span>
                          <span className="tool-card-text">
                            <span className="tool-card-title">{t.title}</span>
                            <span className="tool-card-desc">{t.description}</span>
                            {lacking.length > 0 && <span className="chip warn small">Eksik: {lacking.join(", ")}</span>}
                          </span>
                          <Icon icon={ChevronRight} size={16} className="go" />
                        </a>
                      </li>
                    );
                  })}
                </ul>
              </div>
            );
          })}
        </div>
      </section>

      <footer className="home-foot">
        <span>PDF Atölyesi{engines ? ` ${engines.version}` : ""}</span>
        <span>Dosyaların bu bilgisayarda kalır · kayıt yok, reklam yok</span>
      </footer>
    </div>
  );
}
