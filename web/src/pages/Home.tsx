import { useEffect, useRef, useState } from "react";
import type { EnginesResponse, FileMeta } from "../api";
import DropZone from "../components/DropZone";
import { useUpload } from "../hooks";
import { navigate } from "../router";
import { GROUPS, TOOLS } from "../tools";

/** Arama eşleştirmesinde Türkçe harf ve büyük/küçük harf duyarlılığını kaldırır. */
function normalizeTr(str: string): string {
  return str
    .replace(/İ/g, "i")
    .replace(/I/g, "ı")
    .toLocaleLowerCase("tr")
    .replace(/ç/g, "c")
    .replace(/ğ/g, "g")
    .replace(/ı/g, "i")
    .replace(/ö/g, "o")
    .replace(/ş/g, "s")
    .replace(/ü/g, "u")
    .trim();
}

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

export default function Home({ engines }: { engines: EnginesResponse | null }) {
  const { upload, uploading, progress, error } = useUpload();
  const [notice, setNotice] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const searchRef = useRef<HTMLInputElement>(null);

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
        searchRef.current?.focus();
        searchRef.current?.select();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const missing = (keys: string[] = []) =>
    engines ? engines.engines.filter((e) => keys.includes(e.key) && !e.ok).map((e) => e.name) : [];

  const onFiles = async (files: File[]) => {
    setNotice(null);
    const metas = await upload(files);
    if (metas.length) setNotice(routeFor(metas));
  };

  const q = normalizeTr(query);
  const filteredTools = q
    ? TOOLS.filter((t) => normalizeTr(t.title).includes(q) || normalizeTr(t.description).includes(q))
    : TOOLS;
  const firstMatch = q && filteredTools.length > 0 ? filteredTools[0] : null;

  const onSearchKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && firstMatch) {
      e.preventDefault();
      navigate(firstMatch.route);
    } else if (e.key === "Escape") {
      setQuery("");
      searchRef.current?.blur();
    }
  };

  return (
    <>
      <DropZone
        onFiles={onFiles}
        disabled={uploading}
        title={uploading ? `Yükleniyor… %${Math.round((progress ?? 0) * 100)}` : "Dosyayı buraya bırak"}
        hint="PDF → sayfa düzenleyici · birden çok PDF → birleştir · resimler → PDF · Markdown (+ resimleri) → PDF · Word/Excel/PowerPoint → PDF"
      />
      {(error || notice) && (
        <div className="banner error" role="alert">
          {error ?? notice}
        </div>
      )}

      <div className="home-search" style={{ margin: "1.5rem 0 1rem" }}>
        <input
          ref={searchRef}
          type="search"
          className="input"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={onSearchKeyDown}
          placeholder="Araç ara… (/)"
          aria-label="Araç ara"
        />
      </div>

      {q && filteredTools.length === 0 && (
        <p className="muted center" style={{ margin: "2rem 0" }}>
          Eşleşen araç bulunamadı.
        </p>
      )}

      {GROUPS.map((group) => {
        const groupTools = filteredTools.filter((t) => t.group === group);
        if (!groupTools.length) return null;
        return (
          <section key={group} className="tool-group">
            <h2>{group}</h2>
            <div className="tool-grid">
              {groupTools.map((t) => {
                const lacking = missing(t.needs);
                return (
                  <a key={t.id} className="tool-card active" href={`#/${t.route}`}>
                    <div className="tool-card-head">
                      <h3>{t.title}</h3>
                    </div>
                    <p>{t.description}</p>
                    {lacking.length > 0 && <p className="warn-line">Eksik: {lacking.join(", ")}</p>}
                  </a>
                );
              })}
            </div>
          </section>
        );
      })}
    </>
  );
}
