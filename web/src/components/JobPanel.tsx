import { useEffect, useState } from "react";
import { api, formatSize, type Job } from "../api";
import { navigate } from "../router";

const STATUS: Record<Job["status"], string> = {
  bekliyor: "Sırada",
  calisiyor: "Çalışıyor",
  bitti: "Tamamlandı",
  hata: "Hata",
  iptal: "İptal edildi",
};

interface Props {
  job: Job | null;
  error?: string | null;
  zipName?: string;
}

/** Çalışan işin bu ekranda geçen süresi (saniye). Sunucu saati kullanılmaz: telefon modunda
 * cihazın saati farklı olabilir. */
function useElapsed(jobId: string | undefined, running: boolean): number {
  const [since, setSince] = useState<{ id?: string; at: number }>({ at: Date.now() });
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (since.id !== jobId) setSince({ id: jobId, at: Date.now() });
  }, [jobId, since.id]);
  useEffect(() => {
    if (!running) return;
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, [running]);
  return Math.max(0, Math.round((now - since.at) / 1000));
}

export const formatElapsed = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

/** İşin ilerlemesi, uyarıları ve çıktıları (indir / düzenleyicide aç). */
export default function JobPanel({ job, error, zipName }: Props) {
  const active = !!job && (job.status === "bekliyor" || job.status === "calisiyor");
  const elapsed = useElapsed(job?.id, active);
  if (error) {
    return (
      <div className="banner error" role="alert">
        {error}
      </div>
    );
  }
  if (!job) return null;
  const running = job.status === "bekliyor" || job.status === "calisiyor";

  return (
    <section className={`job-panel status-${job.status}`} aria-live="polite">
      <div className="job-head">
        <strong>{STATUS[job.status]}</strong>
        {running && <span className="muted">{job.message}</span>}
        {running && elapsed >= 5 && (
          <span className="muted small" aria-label={`Geçen süre ${formatElapsed(elapsed)}`}>
            {formatElapsed(elapsed)}
          </span>
        )}
        {running && (
          <button type="button" className="link-button" onClick={() => void api.cancelJob(job.id)}>
            İptal
          </button>
        )}
      </div>
      {running && (
        <div className="progress" role="progressbar" aria-valuenow={Math.round(job.progress * 100)}>
          <div style={{ width: `${Math.max(4, job.progress * 100)}%` }} />
        </div>
      )}
      {job.error && <p className="error-text">{job.error}</p>}
      {job.error?.includes("bozuk olabilir") && typeof job.request.file === "string" && (
        <button
          type="button"
          className="link-button"
          onClick={() => navigate("guvenlik", { dosya: job.request.file as string, islem: "onar" })}
        >
          Onarmayı dene
        </button>
      )}
      {job.warnings.length > 0 && (
        <details className="warnings" open={job.warnings.length <= 5}>
          <summary>{job.warnings.length} ayrıntı / uyarı</summary>
          <ul>
            {job.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </details>
      )}
      {job.files.length > 0 && (
        <>
          <ul className="output-list">
            {job.files.map((f) => (
              <li key={f.id}>
                <span className="file-name">{f.name}</span>
                <span className="muted small">
                  {formatSize(f.size)}
                  {f.page_count ? ` · ${f.page_count} sayfa` : ""}
                </span>
                <span className="actions">
                  {f.kind === "pdf" && (
                    <>
                      <button type="button" className="link-button" onClick={() => navigate(`duzenle/${f.id}`)}>
                        Düzenle
                      </button>
                      <button type="button" className="link-button" onClick={() => navigate(`editor/${f.id}`)}>
                        İçerik ekle
                      </button>
                    </>
                  )}
                  <a className="button primary small" href={api.downloadUrl(f.id)}>
                    İndir
                  </a>
                </span>
              </li>
            ))}
          </ul>
          {job.files.length > 1 && (
            <a className="button" href={api.zipUrl(job.files.map((f) => f.id), zipName)}>
              Hepsini ZIP olarak indir
            </a>
          )}
        </>
      )}
    </section>
  );
}
