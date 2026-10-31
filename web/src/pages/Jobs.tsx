import { useCallback, useEffect, useState } from "react";
import { api, errorMessage, formatSize, type FileMeta, type Job } from "../api";
import { navigate } from "../router";

const TYPE_LABEL: Record<string, string> = {
  compose: "Sayfa düzenleme",
  merge: "Birleştirme",
  split: "Bölme",
  images_to_pdf: "Resim → PDF",
  pdf_to_images: "PDF → Resim",
  md_to_pdf: "Markdown → PDF",
};
const STATUS_LABEL: Record<Job["status"], string> = {
  bekliyor: "Sırada",
  calisiyor: "Çalışıyor",
  bitti: "Tamam",
  hata: "Hata",
  iptal: "İptal",
};

const time = (t: number) =>
  new Date(t * 1000).toLocaleString("tr-TR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

export default function Jobs() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [files, setFiles] = useState<FileMeta[]>([]);
  const [retention, setRetention] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [j, f, e] = await Promise.all([api.jobs(30), api.files(), api.engines()]);
      setJobs(j);
      setFiles(f);
      setRetention(e.retention_hours);
    } catch (err) {
      setError(errorMessage(err));
    }
  }, []);

  useEffect(() => {
    void load();
    const t = window.setInterval(load, 4000);
    return () => window.clearInterval(t);
  }, [load]);

  const act = async (fn: () => Promise<unknown>) => {
    try {
      await fn();
      await load();
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  return (
    <>
      {error && <div className="banner error">{error}</div>}
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
              <strong>{TYPE_LABEL[j.type] ?? j.type}</strong>
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
        {retention !== null && `${retention} saatten eski dosyalar otomatik silinir; saklamak istediklerini sabitle. `}
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
                <th aria-label="İşlemler" />
              </tr>
            </thead>
            <tbody>
              {files.map((f) => (
                <tr key={f.id}>
                  <td>
                    {f.pinned && <span title="Sabitlendi">📌 </span>}
                    {f.name}
                    {f.page_count ? <span className="muted small"> · {f.page_count} s.</span> : null}
                  </td>
                  <td className="muted">{formatSize(f.size)}</td>
                  <td className="muted">{f.version}</td>
                  <td className="muted">{time(f.updated)}</td>
                  <td className="row-actions">
                    {f.kind === "pdf" && (
                      <button type="button" className="link-button" onClick={() => navigate(`duzenle/${f.id}`)}>
                        Düzenle
                      </button>
                    )}
                    <a href={api.downloadUrl(f.id)}>İndir</a>
                    <button type="button" className="link-button" onClick={() => act(() => api.pin(f.id, !f.pinned))}>
                      {f.pinned ? "Sabitlemeyi kaldır" : "Sabitle"}
                    </button>
                    <button
                      type="button"
                      className="link-button danger"
                      onClick={() => window.confirm(`'${f.name}' silinsin mi?`) && act(() => api.remove(f.id))}
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
