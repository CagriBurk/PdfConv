import {
  Ban,
  Check,
  ChevronRight,
  CircleAlert,
  Clock,
  Download,
  FileArchive,
  LoaderCircle,
  Wrench,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useId, useState, type ReactNode } from "react";
import { api, formatSize, type Job } from "../api";
import { navigate, useRoute } from "../router";
import { toolForRoute } from "../tools";
import { fileType } from "./FilePicker";
import Icon from "./Icon";

const STATUS: Record<Job["status"], string> = {
  bekliyor: "Sırada",
  calisiyor: "Çalışıyor",
  bitti: "Tamamlandı",
  hata: "Hata",
  iptal: "İptal edildi",
};

const STATUS_ICON: Record<Job["status"], LucideIcon> = {
  bekliyor: Clock,
  calisiyor: LoaderCircle,
  bitti: Check,
  hata: CircleAlert,
  iptal: Ban,
};

interface Props {
  job: Job | null;
  error?: string | null;
  zipName?: string;
  /** Bitince başlığın altında gösterilen kısa sonuç (ör. "8 MB → 3 MB"). */
  summary?: ReactNode;
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
export default function JobPanel({ job, error, zipName, summary }: Props) {
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
        <span className="tile job-icon">
          <Icon icon={STATUS_ICON[job.status]} size={20} strokeWidth={job.status === "bitti" ? 2.6 : 2} className={job.status === "calisiyor" ? "spin" : undefined} />
        </span>
        <div className="job-panel-text">
          <strong>{STATUS[job.status]}</strong>
          {running && <span className="muted">{job.message}</span>}
          {job.status === "bitti" && summary && <span className="muted">{summary}</span>}
        </div>
        {running && elapsed >= 5 && (
          <span className="muted small job-elapsed" aria-label={`Geçen süre ${formatElapsed(elapsed)}`}>
            {formatElapsed(elapsed)}
          </span>
        )}
        {running && (
          <button type="button" onClick={() => void api.cancelJob(job.id)}>
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
          className="job-repair"
          onClick={() => navigate("guvenlik", { dosya: job.request.file as string, islem: "onar" })}
        >
          <Icon icon={Wrench} size={16} />
          Onarmayı dene
        </button>
      )}
      {job.warnings.length > 0 && (
        <details className="warnings" open={job.warnings.length <= 5}>
          <summary>
            <Icon icon={ChevronRight} size={16} className="warnings-caret" />
            {job.warnings.length} ayrıntı / uyarı
          </summary>
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
                <span className="ftype" aria-hidden="true">
                  {fileType(f.name, f.kind)}
                </span>
                <span className="file-text">
                  <span className="file-name" title={f.name}>
                    {f.name}
                  </span>
                  <span className="file-meta">
                    {formatSize(f.size)}
                    {f.page_count ? ` · ${f.page_count} sayfa` : ""}
                  </span>
                </span>
                <span className="output-actions">
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
                  <a className="button primary output-download" href={api.downloadUrl(f.id)}>
                    <Icon icon={Download} size={17} />
                    İndir
                  </a>
                </span>
              </li>
            ))}
          </ul>
          {job.files.length > 1 && (
            <a className="button block" href={api.zipUrl(job.files.map((f) => f.id), zipName)}>
              <Icon icon={FileArchive} />
              Hepsini ZIP olarak indir
            </a>
          )}
        </>
      )}
    </section>
  );
}

/** Araç ekranının sağdaki eylem kartı: seçimin özeti, kısa not ve tek ana düğme. Düğmenin
 * ikonu aracın kendisi (çalışırken döner). */
export function ActionCard({
  rows,
  note,
  label,
  disabled,
  busy,
  done,
  onRun,
}: {
  rows: [string, ReactNode][];
  note?: ReactNode;
  label: string;
  disabled?: boolean;
  busy?: boolean;
  /** İş tamamlandıysa ana vurgu İndir düğmesine geçer (ekranda çift mavi CTA oluşmasın). */
  done?: boolean;
  onRun: () => void;
}) {
  const id = useId();
  const tool = toolForRoute(useRoute().path[0]);
  return (
    <section className="options" aria-labelledby={id}>
      <h2 id={id}>Özet</h2>
      <dl className="summary">
        {rows.map(([k, v]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>
      {note && <div className="side-note">{note}</div>}
      <button type="button" className={`${done ? "" : "primary "}block action`} disabled={disabled} onClick={onRun}>
        {busy ? <Icon icon={LoaderCircle} className="spin" /> : tool && <Icon icon={tool.icon} />}
        {label}
      </button>
    </section>
  );
}
