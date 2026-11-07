import { useEffect, useState, type ReactNode } from "react";
import type { FileMeta } from "../api";
import FilePicker, { FileRow } from "../components/FilePicker";
import JobPanel from "../components/JobPanel";
import PageHeader from "../components/PageHeader";
import { useFiles, useJob } from "../hooks";
import { passwords } from "../passwords";
import { idsFrom, type Route } from "../router";
import { ACCEPT } from "../tools";

/** Tek PDF alan dönüştürme ekranlarının ortak iskeleti (PDF → Word, PDF → Excel). */
function SinglePdfTool({
  route,
  title,
  intro,
  action,
  options,
  request,
}: {
  route: Route;
  title: string;
  intro: ReactNode;
  action: string;
  options?: ReactNode;
  request: (file: FileMeta) => Record<string, unknown>;
}) {
  const initial = useFiles(idsFrom(route));
  const [file, setFile] = useState<FileMeta | null>(null);
  const [spec, setSpec] = useState("");
  const job = useJob();

  useEffect(() => {
    const pdf = initial.files.find((f) => f.kind === "pdf");
    if (pdf) setFile(pdf);
  }, [initial.files]);

  return (
    <>
      <PageHeader title={title} />
      <div className="tool-layout">
        <section>
          {file ? (
            <FileRow file={file} onRemove={() => (setFile(null), job.reset())} />
          ) : (
            <FilePicker accept={ACCEPT.pdf} kind="pdf" multiple={false} title="PDF'i bırak" onAdd={([f]) => setFile(f)} />
          )}
          <div className="muted small tool-intro">{intro}</div>
        </section>
        <aside className="options">
          <h2>Seçenekler</h2>
          <label className="field">
            Sayfalar
            <input className="input" placeholder="hepsi (ör. 1-3, 5)" value={spec} onChange={(e) => setSpec(e.target.value)} />
          </label>
          {options}
          <button
            type="button"
            className="primary block"
            disabled={!file || job.running}
            onClick={() => file && job.start({ ...request(file), file: file.id, spec, passwords: passwords.forFiles([file.id]) })}
          >
            {action}
          </button>
          <JobPanel job={job.job} error={job.error ?? initial.error} />
        </aside>
      </div>
    </>
  );
}

export function PdfToWord({ route }: { route: Route }) {
  return (
    <SinglePdfTool
      route={route}
      title="PDF → Word"
      action="Word'e dönüştür"
      request={() => ({ type: "pdf_to_word" })}
      intro={
        <>
          <p>
            Yazılar, paragraflar, tablolar ve resimler düzenlenebilir bir Word belgesine (.docx) aktarılır. Sayfa
            yerleşimi korunmaya çalışılır; karmaşık sayfalarda (çok sütun, iç içe kutular) küçük kaymalar olabilir.
          </p>
          <p>Taranmış (fotoğraf gibi) bir PDF'te metin yoktur: önce OCR ile metni tanıt.</p>
        </>
      }
    />
  );
}

export function PdfToExcel({ route }: { route: Route }) {
  const [layout, setLayout] = useState("tek");
  const [numbers, setNumbers] = useState(true);
  return (
    <SinglePdfTool
      route={route}
      title="PDF → Excel"
      action="Excel'e dönüştür"
      request={() => ({ type: "pdf_to_excel", layout, numbers })}
      intro={
        <>
          <p>
            PDF'teki tablolar bulunur ve Excel dosyasına (.xlsx) yazılır: banka dökümü, fatura, fiyat listesi gibi.
            Çizgisiz tablolar yazıların hizasından tanınır. Tablo dışındaki düz yazı aktarılmaz; onun için PDF → Word.
          </p>
          <p>Taranmış (fotoğraf gibi) bir PDF'te metin yoktur: önce OCR ile metni tanıt.</p>
        </>
      }
      options={
        <>
          <label className="field">
            Düzen
            <select value={layout} onChange={(e) => setLayout(e.target.value)}>
              <option value="tek">Hepsi tek sayfada</option>
              <option value="ayri">Her tablo ayrı sayfada</option>
            </select>
          </label>
          <p className="muted small">
            {layout === "tek"
              ? "Tablolar alt alta yazılır; sayfadan sayfaya süren tablo tek tablo olur."
              : "Her tablo Excel'de kendi çalışma sayfasında (S3-T1: 3. sayfanın tablosu)."}
          </p>
          <label className="check">
            <input type="checkbox" checked={numbers} onChange={(e) => setNumbers(e.target.checked)} />
            Sayıları sayıya çevir (1.234,56 → toplanabilir sayı)
          </label>
        </>
      }
    />
  );
}
