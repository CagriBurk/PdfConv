import { useEffect, useState } from "react";
import { api, type FileMeta } from "../api";
import FilePicker, { FileRow } from "../components/FilePicker";
import JobPanel from "../components/JobPanel";
import PageHeader from "../components/PageHeader";
import SortableList from "../components/SortableList";
import { useFiles, useJob } from "../hooks";
import { passwords } from "../passwords";
import { idsFrom, type Route } from "../router";
import { ACCEPT } from "../tools";

// Tarayıcının doğrudan gösterebildiği biçimler (HEIC/TIFF için yalnızca ad gösterilir).
const VIEWABLE = /\.(jpe?g|png|webp|gif|bmp|svg)$/i;

export function ImagesToPdf({ route }: { route: Route }) {
  const initial = useFiles(idsFrom(route));
  const [files, setFiles] = useState<FileMeta[]>([]);
  const [pageSize, setPageSize] = useState("A4");
  const [orientation, setOrientation] = useState("otomatik");
  const [margin, setMargin] = useState(0);
  const [name, setName] = useState("");
  const job = useJob();

  useEffect(() => {
    if (initial.files.length) setFiles(initial.files.filter((f) => f.kind === "image"));
  }, [initial.files]);

  return (
    <>
      <PageHeader title="Resim → PDF" />
      <div className="tool-layout">
        <section>
          <FilePicker
            accept={ACCEPT.images}
            kind="image"
            compact={files.length > 0}
            title={files.length ? "+ Resim ekle" : "Resimleri bırak (JPG, PNG, HEIC, WEBP, TIFF)"}
            onAdd={(added) => setFiles((f) => [...f, ...added])}
          />
          {files.length > 0 && (
            <>
              <p className="muted small">Her resim bir sayfa olur. Sırayı sürükleyerek değiştir.</p>
              <SortableList
                grid
                items={files}
                getKey={(f) => f.id}
                onChange={setFiles}
                render={(f, i) => (
                  <figure className="image-tile">
                    <div className="thumb-box">
                      {VIEWABLE.test(f.name) ? (
                        <img src={api.rawUrl(f.id)} alt="" draggable={false} />
                      ) : (
                        <span className="thumb-placeholder">{f.name.split(".").pop()?.toUpperCase()}</span>
                      )}
                    </div>
                    <figcaption>
                      <span>{i + 1}. {f.name}</span>
                      <button
                        type="button"
                        className="icon-button"
                        aria-label={`${f.name} çıkar`}
                        onPointerDown={(e) => e.stopPropagation()}
                        onClick={() => setFiles((all) => all.filter((x) => x.id !== f.id))}
                      >
                        ×
                      </button>
                    </figcaption>
                  </figure>
                )}
              />
            </>
          )}
        </section>
        <aside className="options">
          <h2>Seçenekler</h2>
          <label className="field">
            Sayfa boyutu
            <select value={pageSize} onChange={(e) => setPageSize(e.target.value)}>
              <option value="A4">A4</option>
              <option value="A5">A5</option>
              <option value="A3">A3</option>
              <option value="Letter">Letter</option>
              <option value="Legal">Legal</option>
              <option value="resim">Resmin kendi boyutu</option>
            </select>
          </label>
          {pageSize !== "resim" && (
            <>
              <label className="field">
                Yön
                <select value={orientation} onChange={(e) => setOrientation(e.target.value)}>
                  <option value="otomatik">Otomatik (resme göre)</option>
                  <option value="dikey">Dikey</option>
                  <option value="yatay">Yatay</option>
                </select>
              </label>
              <label className="field">
                Kenar boşluğu: {margin} mm
                <input type="range" min={0} max={30} value={margin} onChange={(e) => setMargin(Number(e.target.value))} />
              </label>
            </>
          )}
          <label className="field">
            Çıktı adı
            <input className="input" placeholder="otomatik" value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <button
            type="button"
            className="primary block"
            disabled={!files.length || job.running}
            onClick={() =>
              job.start({
                type: "images_to_pdf",
                files: files.map((f) => f.id),
                page_size: pageSize,
                orientation,
                margin_mm: margin,
                name: name || undefined,
              })
            }
          >
            PDF oluştur
          </button>
          <JobPanel job={job.job} error={job.error ?? initial.error} />
        </aside>
      </div>
    </>
  );
}

export function PdfToImages({ route }: { route: Route }) {
  const initial = useFiles(idsFrom(route));
  const [file, setFile] = useState<FileMeta | null>(null);
  const [dpi, setDpi] = useState(150);
  const [fmt, setFmt] = useState("png");
  const [spec, setSpec] = useState("");
  const job = useJob();

  useEffect(() => {
    const pdf = initial.files.find((f) => f.kind === "pdf");
    if (pdf) setFile(pdf);
  }, [initial.files]);

  return (
    <>
      <PageHeader title="PDF → Resim" />
      <div className="tool-layout">
        <section>
          {file ? (
            <FileRow file={file} onRemove={() => (setFile(null), job.reset())} />
          ) : (
            <FilePicker accept={ACCEPT.pdf} kind="pdf" multiple={false} title="PDF'i bırak" onAdd={([f]) => setFile(f)} />
          )}
        </section>
        <aside className="options">
          <h2>Seçenekler</h2>
          <label className="field">
            Çözünürlük
            <select value={dpi} onChange={(e) => setDpi(Number(e.target.value))}>
              <option value={72}>72 DPI (ekran, küçük)</option>
              <option value={150}>150 DPI (önerilen)</option>
              <option value={200}>200 DPI</option>
              <option value={300}>300 DPI (baskı kalitesi)</option>
            </select>
          </label>
          <label className="field">
            Biçim
            <select value={fmt} onChange={(e) => setFmt(e.target.value)}>
              <option value="png">PNG (kayıpsız)</option>
              <option value="jpg">JPG (küçük dosya)</option>
            </select>
          </label>
          <label className="field">
            Sayfalar
            <input className="input" placeholder="hepsi (ör. 1-3, 5)" value={spec} onChange={(e) => setSpec(e.target.value)} />
          </label>
          <button
            type="button"
            className="primary block"
            disabled={!file || job.running}
            onClick={() =>
              file && job.start({ type: "pdf_to_images", file: file.id, dpi, fmt, spec, passwords: passwords.forFiles([file.id]) })
            }
          >
            Resimlere dönüştür
          </button>
          <JobPanel job={job.job} error={job.error ?? initial.error} zipName={file ? `${file.name.replace(/\.pdf$/i, "")}_resimler` : undefined} />
        </aside>
      </div>
    </>
  );
}
