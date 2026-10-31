import { useEffect, useState } from "react";
import type { FileMeta } from "../api";
import FilePicker, { FileRow } from "../components/FilePicker";
import JobPanel from "../components/JobPanel";
import PageHeader from "../components/PageHeader";
import SortableList from "../components/SortableList";
import { useFiles, useJob } from "../hooks";
import { passwords } from "../passwords";
import { idsFrom, type Route } from "../router";
import { ACCEPT } from "../tools";

export default function Merge({ route }: { route: Route }) {
  const initial = useFiles(idsFrom(route));
  const [files, setFiles] = useState<FileMeta[]>([]);
  const [bookmarks, setBookmarks] = useState(true);
  const [name, setName] = useState("");
  const job = useJob();

  useEffect(() => {
    if (initial.files.length) setFiles(initial.files.filter((f) => f.kind === "pdf"));
  }, [initial.files]);

  const totalPages = files.reduce((n, f) => n + (f.page_count ?? 0), 0);

  return (
    <>
      <PageHeader title="Birleştir" />
      <div className="tool-layout">
        <section>
          <FilePicker
            accept={ACCEPT.pdf}
            kind="pdf"
            compact={files.length > 0}
            title={files.length ? "+ PDF ekle" : "Birleştirilecek PDF'leri bırak"}
            onAdd={(added) => setFiles((f) => [...f, ...added])}
          />
          {files.length > 0 && (
            <>
              <p className="muted small">Sırayı değiştirmek için sürükle.</p>
              <SortableList
                items={files}
                getKey={(f) => f.id}
                onChange={setFiles}
                render={(f) => (
                  <FileRow draggable file={f} onRemove={() => setFiles((all) => all.filter((x) => x.id !== f.id))} />
                )}
              />
            </>
          )}
        </section>
        <aside className="options">
          <h2>Seçenekler</h2>
          <label className="check">
            <input type="checkbox" checked={bookmarks} onChange={(e) => setBookmarks(e.target.checked)} />
            Her dosya için adıyla yer imi ekle
          </label>
          <label className="field">
            Çıktı adı
            <input className="input" placeholder="otomatik" value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <button
            type="button"
            className="primary block"
            disabled={files.length < 2 || job.running}
            onClick={() =>
              job.start({
                type: "merge",
                files: files.map((f) => f.id),
                bookmark_per_file: bookmarks,
                name: name || undefined,
                passwords: passwords.forFiles(files.map((f) => f.id)),
              })
            }
          >
            {files.length < 2 ? "En az iki PDF ekle" : `Birleştir (${totalPages} sayfa)`}
          </button>
          <JobPanel job={job.job} error={job.error ?? initial.error} />
        </aside>
      </div>
    </>
  );
}
