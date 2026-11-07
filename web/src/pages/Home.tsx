import { useState } from "react";
import type { EnginesResponse, FileMeta } from "../api";
import DropZone from "../components/DropZone";
import { useUpload } from "../hooks";
import { navigate } from "../router";
import { GROUPS, TOOLS } from "../tools";

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

  const missing = (keys: string[] = []) =>
    engines ? engines.engines.filter((e) => keys.includes(e.key) && !e.ok).map((e) => e.name) : [];

  const onFiles = async (files: File[]) => {
    setNotice(null);
    const metas = await upload(files);
    if (metas.length) setNotice(routeFor(metas));
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

      {GROUPS.map((group) => (
        <section key={group} className="tool-group">
          <h2>{group}</h2>
          <div className="tool-grid">
            {TOOLS.filter((t) => t.group === group).map((t) => {
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
      ))}
    </>
  );
}
