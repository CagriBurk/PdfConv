import { useCallback, useEffect, useRef, useState } from "react";
import { api, errorMessage, formatSize, type FileMeta, type Job } from "../api";
import { splitName } from "../filename";
import { jobLabel } from "../labels";
import { navigate } from "../router";
import { toast } from "../toast";

const STATUS_LABEL: Record<Job["status"], string> = {
  bekliyor: "Sırada",
  calisiyor: "Çalışıyor",
  bitti: "Tamam",
  hata: "Hata",
  iptal: "İptal",
};

const time = (t: number) =>
  new Date(t * 1000).toLocaleString("tr-TR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

/** Satır içi yeniden adlandırma: Enter kaydeder, Esc vazgeçer. Uzantı ayrı tutulur (yanlışlıkla
 * silinip dosya türü bozulmasın); kullanıcı uzantıyı yazarsa sunucu yine doğru olanı korur. */
function RenameField({ file, onDone }: { file: FileMeta; onDone: (renamed: boolean) => void }) {
  const { stem: initial, ext } = splitName(file.name);
  const [stem, setStem] = useState(initial);
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => input.current?.select(), []);

  const submit = async () => {
    const name = stem.trim();
    if (!name || `${name}${ext}` === file.name) return onDone(false);
    setBusy(true);
    try {
      const meta = await api.rename(file.id, `${name}${ext}`);
      toast.ok(`Yeni ad: ${meta.name}`);
      onDone(true);
    } catch (e) {
      toast.error(errorMessage(e));
      setBusy(false);
      input.current?.focus();
    }
  };

  return (
    <form
      className="rename-form"
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
    >
      <input
        ref={input}
        className="input"
        aria-label={`'${file.name}' için yeni ad`}
        value={stem}
        maxLength={180}
        disabled={busy}
        onChange={(e) => setStem(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            e.preventDefault();
            onDone(false);
          }
        }}
      />
      {ext && <span className="muted">{ext}</span>}
      <button type="submit" className="small" disabled={busy}>
        Kaydet
      </button>
      <button type="button" className="link-button" onClick={() => onDone(false)}>
        Vazgeç
      </button>
    </form>
  );
}

export default function Jobs() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [files, setFiles] = useState<FileMeta[]>([]);
  const [retention, setRetention] = useState<number | null>(null);
  const [local, setLocal] = useState(false);
  const [renaming, setRenaming] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [j, f, s] = await Promise.all([api.jobs(30), api.files(), api.settings()]);
      setJobs(j);
      setFiles(f);
      setRetention(s.values.retention_hours);
      setLocal(s.local);
      setError(null);
    } catch (err) {
      setError(errorMessage(err));
    }
  }, []);

  useEffect(() => {
    void load();
    const t = window.setInterval(load, 4000);
    return () => window.clearInterval(t);
  }, [load]);

  const act = async (fn: () => Promise<unknown>, okText?: string) => {
    try {
      await fn();
      if (okText) toast.ok(okText);
      await load();
    } catch (e) {
      toast.error(errorMessage(e));
    }
  };

  const retentionText =
    retention === null ? "" : retention % 24 === 0 ? `${retention / 24} günden` : `${retention} saatten`;

  return (
    <>
      {error && (
        <div className="banner error" role="alert">
          {error}
        </div>
      )}
      <h2>Son işler</h2>
      {jobs.length === 0 ? (
        <p className="muted">Henüz iş yok.</p>
      ) : (
        <ul className="job-list">
          {jobs.map((j) => (
            <li key={j.id} className={`status-${j.status}`}>
              <span className={`pill ${j.status === "bitti" ? "ok" : j.status === "hata" ? "bad" : "warn"}`}>
                {STATUS_LABEL[j.status]}
              </span>
              <strong>{jobLabel(j.type, j.request)}</strong>
              <span className="muted small">{time(j.created)}</span>
              {j.error && <span className="error-text small">{j.error}</span>}
              {j.warnings.length > 0 && <span className="warn-line">{j.warnings.length} uyarı</span>}
              <span className="job-files">
                {j.files.slice(0, 4).map((f) => (
                  <a key={f.id} href={api.downloadUrl(f.id)} className="small">
                    {f.name}
                  </a>
                ))}
                {j.files.length > 4 && (
                  <a href={api.zipUrl(j.files.map((f) => f.id))} className="small">
                    +{j.files.length - 4} dosya (ZIP)
                  </a>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}

      <h2>Dosyalar</h2>
      <p className="muted small">
        {retentionText && `${retentionText} uzun süre açılmamış dosyalar otomatik silinir; saklamak istediklerini sabitle (süre Ayarlar'dan değişir). `}
        Dosyalar yalnızca bu bilgisayarda durur.
      </p>
      {files.length === 0 ? (
        <p className="muted">Dosya yok.</p>
      ) : (
        <div className="table-wrap">
          <table className="file-table">
            <thead>
              <tr>
                <th>Ad</th>
                <th>Boyut</th>
                <th>Sürüm</th>
                <th>Tarih</th>
                <th>
                  <span className="sr-only">İşlemler</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {files.map((f) => (
                <tr key={f.id}>
                  <td>
                    {renaming === f.id ? (
                      <RenameField
                        file={f}
                        onDone={(renamed) => {
                          setRenaming(null);
                          if (renamed) void load();
                        }}
                      />
                    ) : (
                      <>
                        {f.pinned && (
                          <span title="Sabitlendi" aria-label="Sabitlendi">
                            📌{" "}
                          </span>
                        )}
                        {f.name}
                        {f.page_count ? <span className="muted small"> · {f.page_count} s.</span> : null}
                      </>
                    )}
                  </td>
                  <td className="muted" data-label="Boyut">
                    {formatSize(f.size)}
                  </td>
                  <td className="muted" data-label="Sürüm">
                    {f.version}
                  </td>
                  <td className="muted" data-label="Tarih">
                    {time(f.updated)}
                  </td>
                  <td className="row-actions">
                    {f.kind === "pdf" && (
                      <button type="button" className="link-button" onClick={() => navigate(`duzenle/${f.id}`)}>
                        Düzenle
                      </button>
                    )}
                    <a href={api.downloadUrl(f.id)} aria-label={`${f.name} indir`}>
                      İndir
                    </a>
                    <button
                      type="button"
                      className="link-button"
                      aria-label={`${f.name} yeniden adlandır`}
                      onClick={() => setRenaming(f.id)}
                    >
                      Yeniden adlandır
                    </button>
                    {local && (
                      <button
                        type="button"
                        className="link-button"
                        title="Dosyanın bir kopyasını gerçek adıyla Gezgin'de gösterir"
                        onClick={() => void act(() => api.reveal(f.id))}
                      >
                        Klasörde göster
                      </button>
                    )}
                    <button type="button" className="link-button" onClick={() => act(() => api.pin(f.id, !f.pinned))}>
                      {f.pinned ? "Sabitlemeyi kaldır" : "Sabitle"}
                    </button>
                    <button
                      type="button"
                      className="link-button danger"
                      onClick={() =>
                        window.confirm(`'${f.name}' silinsin mi?`) && act(() => api.remove(f.id), `'${f.name}' silindi.`)
                      }
                    >
                      Sil
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
