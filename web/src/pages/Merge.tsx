import { useEffect, useState } from "react";
import type { FileMeta } from "../api";
import FilePicker, { FileRow, FilesCard, filesSummary } from "../components/FilePicker";
import JobPanel, { ActionCard } from "../components/JobPanel";
import PageHeader from "../components/PageHeader";
import PasswordDialog from "../components/PasswordDialog";
import SortableList from "../components/SortableList";
import { useFiles, useJob, useUnlockQueue } from "../hooks";
import { passwords } from "../passwords";
import { idsFrom, type Route } from "../router";
import { ACCEPT } from "../tools";

export default function Merge({ route }: { route: Route }) {
  const initial = useFiles(idsFrom(route));
  const [files, setFiles] = useState<FileMeta[]>([]);
  const [bookmarks, setBookmarks] = useState(true);
  const [name, setName] = useState("");
  const job = useJob();

  const unlock = useUnlockQueue({
    onUnlock: (accepted) => setFiles((curr) => [...curr, ...accepted]),
    onCancel: (cancelled) => setFiles((curr) => curr.filter((f) => f.id !== cancelled.id)),
  });
  const queueUnlock = unlock.queue;

  useEffect(() => {
    if (initial.files.length) queueUnlock(initial.files.filter((f) => f.kind === "pdf"));
  }, [initial.files, queueUnlock]);

  const totalPages = files.reduce((n, f) => n + (f.page_count ?? 0), 0);

  return (
    <>
      <PageHeader title="Birleştir" />
      <div className="tool-layout">
        <div className="tool-main">
          <FilesCard count={files.length} hint={files.length > 0 && "Sırayı değiştirmek için sürükle."}>
            {files.length > 0 && (
              <SortableList
                items={files}
                getKey={(f) => f.id}
                onChange={setFiles}
                render={(f) => (
                  <FileRow draggable file={f} onRemove={() => setFiles((all) => all.filter((x) => x.id !== f.id))} />
                )}
              />
            )}
            <FilePicker
              accept={ACCEPT.pdf}
              kind="pdf"
              compact={files.length > 0}
              title={files.length ? "PDF ekle" : "Birleştirilecek PDF'leri bırak"}
              onAdd={(added) => setFiles((f) => [...f, ...added])}
            />
          </FilesCard>
          <section className="card">
            <h2>Seçenekler</h2>
            <label className="check">
              <input type="checkbox" checked={bookmarks} onChange={(e) => setBookmarks(e.target.checked)} />
              Her dosya için adıyla yer imi ekle
            </label>
            <label className="field">
              Çıktı adı
              <input className="input" placeholder="otomatik" value={name} onChange={(e) => setName(e.target.value)} />
            </label>
          </section>
        </div>
        <aside className="tool-side">
          <ActionCard
            rows={[
              ["Dosya", filesSummary(files, "PDF")],
              ["Toplam", files.length ? `${totalPages} sayfa` : "—"],
            ]}
            label={files.length < 2 ? "En az iki PDF ekle" : `Birleştir (${totalPages} sayfa)`}
            disabled={files.length < 2 || job.running}
            busy={job.running}
            done={job.job?.status === "bitti"}
            onRun={() =>
              job.start({
                type: "merge",
                files: files.map((f) => f.id),
                bookmark_per_file: bookmarks,
                name: name || undefined,
                passwords: passwords.forFiles(files.map((f) => f.id)),
              })
            }
          />
          <JobPanel job={job.job} error={job.error ?? initial.error} />
        </aside>
      </div>
      {unlock.locked && <PasswordDialog file={unlock.locked} onDone={unlock.onDone} />}
    </>
  );
}
