import { useEffect, useState } from "react";
import { formatSize, type FileMeta } from "../api";
import FilePicker, { FileRow } from "../components/FilePicker";
import JobPanel from "../components/JobPanel";
import PageHeader from "../components/PageHeader";
import { useFiles, useJob } from "../hooks";
import { passwords } from "../passwords";
import { idsFrom, type Route } from "../router";
import { ACCEPT } from "../tools";

type Level = "kayipsiz" | "dengeli" | "guclu";

const LEVELS: { value: Level; label: string; hint: string }[] = [
  {
    value: "kayipsiz",
    label: "Kayıpsız",
    hint: "Kalite hiç değişmez: gereksiz veri atılır, yazı tipleri küçültülür. Yazı ağırlıklı PDF'lerde en iyisi.",
  },
  { value: "dengeli", label: "Dengeli", hint: "+ resimler 150 DPI. Taranmış belge ve paftalarda %50–80." },
  {
    value: "guclu",
    label: "Güçlü",
    hint: "+ resimler 100 DPI, düşük kalite. En küçük dosya; ekranda okumak ve e-postayla göndermek için.",
  },
];

export default function Compress({ route }: { route: Route }) {
  const initial = useFiles(idsFrom(route));
  const [files, setFiles] = useState<FileMeta[]>([]);
  const [level, setLevel] = useState<Level>("dengeli");
  const job = useJob();

  useEffect(() => {
    if (initial.files.length) setFiles(initial.files.filter((f) => f.kind === "pdf"));
  }, [initial.files]);

  const total = files.reduce((n, f) => n + f.size, 0);
  const after = job.job?.status === "bitti" ? job.job.files.reduce((n, f) => n + f.size, 0) : null;

  return (
    <>
      <PageHeader title="Sıkıştır" />
      <div className="tool-layout">
        <section>
          <FilePicker
            accept={ACCEPT.pdf}
            kind="pdf"
            compact={files.length > 0}
            title={files.length ? "+ PDF ekle" : "Küçültülecek PDF'leri bırak"}
            onAdd={(added) => setFiles((f) => [...f, ...added])}
          />
          {files.map((f) => (
            <FileRow key={f.id} file={f} onRemove={() => setFiles((all) => all.filter((x) => x.id !== f.id))} />
          ))}
          <fieldset className="radio-cards">
            <legend>Seviye</legend>
            {LEVELS.map((l) => (
              <label key={l.value} className={`radio-card${level === l.value ? " on" : ""}`}>
                <input type="radio" name="level" checked={level === l.value} onChange={() => setLevel(l.value)} />
                <strong>{l.label}</strong>
                <span className="muted small">{l.hint}</span>
              </label>
            ))}
          </fieldset>
        </section>
        <aside className="options">
          <p className="muted small">
            Sonuç orijinalden büyük çıkarsa orijinal korunur. Metin ve bağlantılar korunur; yalnızca resimler
            yeniden sıkıştırılır.
          </p>
          <button
            type="button"
            className="primary block"
            disabled={!files.length || job.running}
            onClick={() =>
              void job.start({
                type: "compress",
                files: files.map((f) => f.id),
                level,
                passwords: passwords.forFiles(files.map((f) => f.id)),
              })
            }
          >
            {files.length > 1 ? `${files.length} dosyayı sıkıştır` : "Sıkıştır"}
          </button>
          {after !== null && total > 0 && (
            <p className="result-line">
              Toplam: {formatSize(total)} → <strong>{formatSize(after)}</strong>
              {after < total && ` (%${Math.round((1 - after / total) * 100)} küçüldü)`}
            </p>
          )}
          <JobPanel job={job.job} error={job.error ?? initial.error} zipName="kucultulmus" />
        </aside>
      </div>
    </>
  );
}
