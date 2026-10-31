import { useEffect, useState } from "react";
import type { FileMeta } from "../api";
import FilePicker, { FileRow } from "../components/FilePicker";
import JobPanel from "../components/JobPanel";
import PageHeader from "../components/PageHeader";
import { useFiles, useJob } from "../hooks";
import { passwords } from "../passwords";
import { idsFrom, type Route } from "../router";
import { ACCEPT } from "../tools";

type Mode = "her" | "n" | "aralik" | "yer-imi";

const MODES: { value: Mode; label: string; hint: string }[] = [
  { value: "her", label: "Her sayfa ayrı", hint: "Her sayfa ayrı bir PDF olur." },
  { value: "n", label: "Her N sayfada bir", hint: "Eşit büyüklükte parçalar." },
  { value: "aralik", label: "Aralıklara göre", hint: "Virgülle ayrılmış her aralık bir dosya: 1-3, 4-10, 11-" },
  { value: "yer-imi", label: "Yer imlerine göre", hint: "Üst seviye her bölüm ayrı dosya (bölüm adıyla)." },
];

export default function Split({ route }: { route: Route }) {
  const initial = useFiles(idsFrom(route));
  const [file, setFile] = useState<FileMeta | null>(null);
  const [mode, setMode] = useState<Mode>("her");
  const [every, setEvery] = useState(2);
  const [spec, setSpec] = useState("");
  const job = useJob();

  useEffect(() => {
    const pdf = initial.files.find((f) => f.kind === "pdf");
    if (pdf) setFile(pdf);
  }, [initial.files]);

  const pages = file?.page_count ?? 0;
  const parts = mode === "her" ? pages : mode === "n" && every > 0 ? Math.ceil(pages / every) : null;

  return (
    <>
      <PageHeader title="Böl" />
      <div className="tool-layout">
        <section>
          {file ? (
            <FileRow file={file} onRemove={() => (setFile(null), job.reset())} />
          ) : (
            <FilePicker accept={ACCEPT.pdf} kind="pdf" multiple={false} title="Bölünecek PDF'i bırak" onAdd={([f]) => setFile(f)} />
          )}
          <fieldset className="radio-cards">
            <legend>Nasıl bölünsün?</legend>
            {MODES.map((m) => (
              <label key={m.value} className={`radio-card${mode === m.value ? " on" : ""}`}>
                <input type="radio" name="mode" value={m.value} checked={mode === m.value} onChange={() => setMode(m.value)} />
                <strong>{m.label}</strong>
                <span className="muted small">{m.hint}</span>
              </label>
            ))}
          </fieldset>
          {mode === "n" && (
            <label className="field inline">
              Kaç sayfada bir
              <input className="input narrow" type="number" min={1} value={every} onChange={(e) => setEvery(Number(e.target.value))} />
            </label>
          )}
          {mode === "aralik" && (
            <label className="field">
              Aralıklar
              <input className="input" placeholder="1-3, 4-10, 11-" value={spec} onChange={(e) => setSpec(e.target.value)} />
            </label>
          )}
        </section>
        <aside className="options">
          <button
            type="button"
            className="primary block"
            disabled={!file || job.running || (mode === "aralik" && !spec.trim())}
            onClick={() =>
              file &&
              job.start({
                type: "split",
                file: file.id,
                mode,
                every,
                spec,
                passwords: passwords.forFiles([file.id]),
              })
            }
          >
            {parts ? `Böl (${parts} dosya)` : "Böl"}
          </button>
          <JobPanel job={job.job} error={job.error ?? initial.error} zipName={file ? `${file.name.replace(/\.pdf$/i, "")}_parcalar` : undefined} />
        </aside>
      </div>
    </>
  );
}
