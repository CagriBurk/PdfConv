import { useEffect, useState } from "react";
import type { EnginesResponse, FileMeta } from "../api";
import FilePicker, { FileRow } from "../components/FilePicker";
import JobPanel from "../components/JobPanel";
import InstallLibreOffice from "../components/InstallLibreOffice";
import PageHeader from "../components/PageHeader";
import SortableList from "../components/SortableList";
import { useFiles, useJob } from "../hooks";
import { idsFrom, type Route } from "../router";
import { ACCEPT } from "../tools";

const KINDS: FileMeta["kind"][] = ["office", "html", "text"];

interface Props {
  route: Route;
  engines: EnginesResponse | null;
  onEnginesChanged: () => void;
}

export default function Office({ route, engines, onEnginesChanged }: Props) {
  const initial = useFiles(idsFrom(route));
  const [files, setFiles] = useState<FileMeta[]>([]);
  const [merge, setMerge] = useState(false);
  const [pdfa, setPdfa] = useState(false);
  const [name, setName] = useState("");
  const job = useJob();
  const lo = engines?.engines.find((e) => e.key === "libreoffice");
  const needsLo = files.some((f) => f.kind === "office");

  useEffect(() => {
    if (initial.files.length) setFiles(initial.files.filter((f) => KINDS.includes(f.kind)));
  }, [initial.files]);

  return (
    <>
      <PageHeader title="Office → PDF" />
      {lo && !lo.ok && needsLo && (
        <div className="banner error">
          LibreOffice bulunamadı; Word/Excel/PowerPoint dosyaları çevrilemez. HTML ve TXT çevrilebilir.
          {engines?.windows ? (
            <InstallLibreOffice onInstalled={onEnginesChanged} />
          ) : (
            lo.install_hint && <code className="small">{lo.install_hint}</code>
          )}
        </div>
      )}
      <div className="tool-layout">
        <section>
          <FilePicker
            accept={ACCEPT.office}
            kind={KINDS}
            compact={files.length > 0}
            title={files.length ? "+ Dosya ekle" : "Word, Excel, PowerPoint, ODT, RTF, HTML ya da TXT dosyalarını bırak"}
            onAdd={(added) => setFiles((f) => [...f, ...added])}
          />
          {files.length > 0 && (
            <>
              <p className="muted small">
                {merge ? "Birleştirme sırası bu listedeki sıradır; sürükleyerek değiştir." : "Her dosya ayrı bir PDF olur."}
              </p>
              <SortableList
                items={files}
                getKey={(f) => f.id}
                onChange={setFiles}
                render={(f) => (
                  <FileRow draggable={merge} file={f} onRemove={() => setFiles((all) => all.filter((x) => x.id !== f.id))} />
                )}
              />
            </>
          )}
        </section>
        <aside className="options">
          <h2>Seçenekler</h2>
          <label className="check">
            <input type="checkbox" checked={merge} onChange={(e) => setMerge(e.target.checked)} />
            Hepsini tek PDF'te birleştir (her dosya için yer imi)
          </label>
          {merge && (
            <label className="field">
              Çıktı adı
              <input className="input" placeholder="otomatik" value={name} onChange={(e) => setName(e.target.value)} />
            </label>
          )}
          <label className="check">
            <input type="checkbox" checked={pdfa} onChange={(e) => setPdfa(e.target.checked)} />
            Arşiv için PDF/A (Office dosyaları)
          </label>
          <p className="muted small">
            Bozuk ya da parolalı bir dosya diğerlerini durdurmaz; uyarı olarak bildirilir. Bilgisayarda olmayan fontlar da
            uyarılır.
          </p>
          <button
            type="button"
            className="primary block"
            disabled={!files.length || job.running}
            onClick={() =>
              job.start({ type: "office_to_pdf", files: files.map((f) => f.id), merge, pdfa, name: name || undefined })
            }
          >
            {job.running ? "Dönüştürülüyor…" : files.length > 1 ? `${files.length} dosyayı dönüştür` : "PDF'e dönüştür"}
          </button>
          <JobPanel job={job.job} error={job.error ?? initial.error} zipName="pdfler" />
        </aside>
      </div>
    </>
  );
}
