import { ArrowLeftRight, ArrowRight, ChevronRight, FileText, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import type { EnginesResponse, FileMeta } from "../api";
import DropZone from "../components/DropZone";
import Icon from "../components/Icon";
import RecentFiles from "../components/RecentFiles";
import { useUpload } from "../hooks";
import { navigate } from "../router";
import { commonConvertTargets, GROUP_TONE, GROUPS, TOOLS } from "../tools";

type Query = Record<string, string | string[]>;
type Dropped = Pick<FileMeta, "id" | "name" | "kind">;

/** Bırakılan dosyalar için yapılacak iş: doğrudan bir araca git, PDF ile başka biçim arasında
 * seçtir ya da birlikte işlenemediklerini söyle. */
export type HomeRoute =
  | { type: "go"; path: string; query?: Query }
  | { type: "choose"; pdfPath: string; ids: string[]; targets: string[]; what: string }
  | { type: "error"; message: string };

/** Bırakılan dosyaların türüne göre en uygun araç. Hepsi resim ya da hepsi Office belgesiyse ve
 * ortak bir dönüştürme hedefi varsa PDF ile başka biçim arasında seçim sorulur. */
export function homeRoute(files: Dropped[]): HomeRoute {
  const md = files.find((f) => f.kind === "markdown");
  if (md) {
    const ek = files.filter((f) => f.id !== md.id).map((f) => f.id);
    return { type: "go", path: "md", query: ek.length ? { dosya: md.id, ek } : { dosya: md.id } };
  }
  const ids = files.map((f) => f.id);
  const all = (...kinds: FileMeta["kind"][]) => files.every((f) => kinds.includes(f.kind));
  if (all("pdf")) {
    return ids.length === 1 ? { type: "go", path: `duzenle/${ids[0]}` } : { type: "go", path: "birlestir", query: { dosya: ids } };
  }
  const pdfPath = all("image") ? "resimden" : all("office", "html", "text") ? "office" : null;
  if (!pdfPath) return { type: "error", message: "Bu dosya türleri birlikte işlenemiyor. PDF, resim ya da Markdown bırak." };
  // HTML / TXT'nin dönüştürme hedefi yok; yalnız saf resim ya da saf Office seçimi sorulur.
  const targets = pdfPath === "resimden" || all("office") ? commonConvertTargets(files.map((f) => f.name)) : [];
  if (!targets.length) return { type: "go", path: pdfPath, query: { dosya: ids } };
  const n = files.length;
  const what = pdfPath === "resimden" ? `${n} resim yüklendi.` : n === 1 ? "Belge yüklendi." : `${n} belge yüklendi.`;
  return { type: "choose", pdfPath, ids, targets, what };
}

/** Hedeflerin kısa adları: [".jpg", ".png"] → "JPG, PNG". */
export function targetNames(targets: string[]): string {
  return targets.map((t) => t.replace(/^\./, "").toUpperCase()).join(", ");
}

// `homeRoute`un sırasıyla aynı: Markdown varsa yanındakiler eki sayılır.
const ROUTES: [string, string][] = [
  ["Tek PDF", "düzenleyicide açılır"],
  ["Birden çok PDF", "birleştirilir"],
  ["Resimler", "tek PDF ya da başka biçim"],
  ["Markdown (+ resimleri)", "PDF'e dönüşür"],
  ["Word, Excel, PowerPoint", "PDF ya da başka biçim"],
  ["HTML, TXT", "PDF olur"],
];

export default function Home({ engines, onSearch }: { engines: EnginesResponse | null; onSearch: () => void }) {
  const { upload, uploading, progress, error } = useUpload();
  const [notice, setNotice] = useState<string | null>(null);
  const [choice, setChoice] = useState<Extract<HomeRoute, { type: "choose" }> | null>(null);
  const [uploads, setUploads] = useState(0);
  const hero = useRef<HTMLElement>(null);
  const toPdf = useRef<HTMLButtonElement>(null);

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

  const closeChoice = useCallback(() => {
    // Odak karttaysa kaybolmasın: bırakma alanına döner.
    const inside = hero.current?.querySelector(".home-choice")?.contains(document.activeElement);
    setChoice(null);
    if (inside) hero.current?.querySelector<HTMLElement>(".dropzone")?.focus();
  }, []);

  // Seçim kartı: odak birincil düğmede (Enter = PDF'e çevir); Esc kapatır.
  useEffect(() => {
    if (!choice) return;
    toPdf.current?.focus();
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || e.defaultPrevented || document.querySelector("dialog[open], .modal")) return;
      e.preventDefault();
      closeChoice();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [choice, closeChoice]);

  const missing = (keys: string[] = []) =>
    engines ? engines.engines.filter((e) => keys.includes(e.key) && !e.ok).map((e) => e.name) : [];

  const onFiles = async (files: File[]) => {
    setNotice(null);
    setChoice(null);
    const metas = await upload(files);
    if (!metas.length) return;
    setUploads((n) => n + 1);
    const next = homeRoute(metas);
    if (next.type === "go") navigate(next.path, next.query);
    else if (next.type === "choose") setChoice(next);
    else setNotice(next.message);
  };

  return (
    <div className="home">
      <div className="home-top">
        <section ref={hero} className="card home-hero" aria-labelledby="home-baslik">
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
          {choice && (
            <section className="home-choice" aria-labelledby="home-secim">
              <div className="home-choice-head">
                <div>
                  <h2 id="home-secim">Ne yapmak istiyorsun?</h2>
                  <p className="muted small">{choice.what}</p>
                </div>
                <button type="button" className="icon-button" aria-label="Kapat (Esc)" title="Kapat (Esc)" onClick={closeChoice}>
                  <Icon icon={X} />
                </button>
              </div>
              <div className="home-choice-actions">
                <button
                  ref={toPdf}
                  type="button"
                  className="primary"
                  onClick={() => navigate(choice.pdfPath, { dosya: choice.ids })}
                >
                  <Icon icon={FileText} />
                  PDF'e çevir
                </button>
                <button
                  type="button"
                  aria-describedby="home-secim-hedef"
                  onClick={() => navigate("donustur", { dosya: choice.ids })}
                >
                  <Icon icon={ArrowLeftRight} />
                  Başka biçime dönüştür
                </button>
              </div>
              <p id="home-secim-hedef" className="muted small">
                Başka biçim: {targetNames(choice.targets)}
              </p>
            </section>
          )}
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
        <span>Toolia{engines ? ` ${engines.version}` : ""}</span>
        <span>Dosyaların bu bilgisayarda kalır · kayıt yok, reklam yok</span>
      </footer>
    </div>
  );
}
