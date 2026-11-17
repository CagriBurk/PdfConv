import {
  Archive,
  Ban,
  Check,
  CircleX,
  Download,
  FolderOpen,
  Hourglass,
  Inbox,
  LayoutGrid,
  LoaderCircle,
  Pin,
  PinOff,
  TextCursorInput,
  Trash2,
  Upload,
  Wrench,
  type LucideIcon,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, errorMessage, formatSize, type FileMeta, type Job } from "../api";
import Icon from "../components/Icon";
import { splitName } from "../filename";
import { jobLabel } from "../labels";
import { navigate } from "../router";
import { toast } from "../toast";
import { toolForRoute } from "../tools";

const STATUS: Record<Job["status"], { label: string; tone: string; icon: LucideIcon }> = {
  bekliyor: { label: "Sırada", tone: "", icon: Hourglass },
  calisiyor: { label: "Çalışıyor", tone: "accent", icon: LoaderCircle },
  bitti: { label: "Tamam", tone: "ok", icon: Check },
  hata: { label: "Hata", tone: "bad", icon: CircleX },
  iptal: { label: "İptal", tone: "", icon: Ban },
};

// İş türü → aracın rotası (ikon ve grup tonu oradan). Motor kurulumu bir araç değil.
const JOB_TOOL: Record<string, string> = {
  compose: "duzenle",
  merge: "birlestir",
  split: "bol",
  layout: "yazdirma",
  md_to_pdf: "md",
  office_to_pdf: "office",
  images_to_pdf: "resimden",
  pdf_to_images: "resme",
  pdf_to_word: "word",
  pdf_to_excel: "excel",
  apply: "editor",
  compress: "sikistir",
  ocr: "ocr",
  encrypt: "guvenlik",
  decrypt: "guvenlik",
  clean_metadata: "guvenlik",
  repair: "guvenlik",
};

function JobTile({ type }: { type: string }) {
  const tool = toolForRoute(JOB_TOOL[type]);
  return (
    <span className={`tile${tool ? ` ${tool.tone}` : ""}`}>
      <Icon icon={tool?.icon ?? Wrench} size={19} strokeWidth={1.9} />
    </span>
  );
}

/** Dosya türü rozetindeki kısa ad: uzantı (en çok 4 harf). */
function typeLabel(f: FileMeta): string {
  const ext = f.name.includes(".") ? f.name.split(".").pop()! : f.kind;
  return ext.slice(0, 4).toLocaleUpperCase("tr");
}

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
      setLocal(s.desktop);
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
    <div className="jobs">
      <header className="screen-head">
        <h1>İşler ve dosyalar</h1>
        <p>Son işlerin ve dosyaların: indir, yeniden adlandır, saklamak istediklerini sabitle.</p>
      </header>
      {error && (
        <div className="banner error" role="alert">
          {error}
        </div>
      )}

      <section className="card" aria-labelledby="son-isler">
        <div className="section-head">
          <h2 id="son-isler">Son işler</h2>
        </div>
        {jobs.length === 0 ? (
          <div className="empty-state">
            <span className="tile lg">
              <Icon icon={Inbox} size={25} strokeWidth={1.9} />
            </span>
            <p className="empty-title">Henüz iş yok.</p>
            <p className="muted small">
              Bir araçla dosya işlediğinde burada görünür; bitenlerin çıktısını buradan da indirirsin.
            </p>
          </div>
        ) : (
          <ul className="job-list">
            {jobs.map((j) => {
              const st = STATUS[j.status];
              return (
                <li key={j.id} className={`status-${j.status}`}>
                  <JobTile type={j.type} />
                  <div className="job-text">
                    <p className="job-title">{jobLabel(j.type, j.request)}</p>
                    <p className="job-meta">
                      {time(j.created)}
                      {j.warnings.length > 0 && <span className="warn-line">{j.warnings.length} uyarı</span>}
                    </p>
                    {j.error && <p className="error-text small">{j.error}</p>}
                    <span className="job-files">
                      {j.files.slice(0, 4).map((f) => (
                        <a key={f.id} href={api.downloadUrl(f.id)} className="job-file" title={f.name}>
                          <Icon icon={Download} size={15} />
                          <span>{f.name}</span>
                        </a>
                      ))}
                      {j.files.length > 4 && (
                        <a href={api.zipUrl(j.files.map((f) => f.id))} className="job-file">
                          <Icon icon={Archive} size={15} />
                          <span>+{j.files.length - 4} dosya (ZIP)</span>
                        </a>
                      )}
                    </span>
                  </div>
                  <span className={`chip small job-state${st.tone ? ` ${st.tone}` : ""}`}>
                    <Icon icon={st.icon} size={14} className={j.status === "calisiyor" ? "spin" : undefined} />
                    {st.label}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section className="card" aria-labelledby="dosyalar">
        <div className="section-head">
          <h2 id="dosyalar">Dosyalar</h2>
        </div>
        <p className="files-note">
          {retentionText &&
            `${retentionText} uzun süre açılmamış dosyalar otomatik silinir; saklamak istediklerini sabitle (süre Ayarlar'dan değişir). `}
          Dosyalar yalnızca bu bilgisayarda durur.
        </p>
        {files.length === 0 ? (
          <div className="empty-state">
            <span className="tile lg">
              <Icon icon={FolderOpen} size={25} strokeWidth={1.9} />
            </span>
            <p className="empty-title">Dosya yok.</p>
            <p className="muted small">Ana sayfaya bir dosya bırak; yüklediklerin ve araçların ürettikleri burada listelenir.</p>
            <a className="button" href="#/araclar">
              <Icon icon={Upload} size={17} />
              Dosya bırak
            </a>
          </div>
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
                      <div className="file-cell">
                        <span className="ftype" aria-hidden="true">
                          {typeLabel(f)}
                        </span>
                        {renaming === f.id ? (
                          <RenameField
                            file={f}
                            onDone={(renamed) => {
                              setRenaming(null);
                              if (renamed) void load();
                            }}
                          />
                        ) : (
                          <span className="file-cell-text">
                            <span className="file-cell-name">
                              {f.pinned && (
                                <span className="pin-mark" title="Sabitlendi">
                                  <Icon icon={Pin} size={14} label="Sabitlendi" />
                                </span>
                              )}
                              {f.name}
                            </span>
                            {f.page_count ? <span className="file-cell-meta">{f.page_count} sayfa</span> : null}
                          </span>
                        )}
                      </div>
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
                        <button
                          type="button"
                          className="icon-button"
                          aria-label="Düzenle"
                          title="Düzenleyicide aç"
                          onClick={() => navigate(`duzenle/${f.id}`)}
                        >
                          <Icon icon={LayoutGrid} />
                        </button>
                      )}
                      <a className="icon-button" href={api.downloadUrl(f.id)} aria-label={`${f.name} indir`} title="İndir">
                        <Icon icon={Download} />
                      </a>
                      <button
                        type="button"
                        className="icon-button"
                        aria-label={`${f.name} yeniden adlandır`}
                        title="Yeniden adlandır"
                        onClick={() => setRenaming(f.id)}
                      >
                        <Icon icon={TextCursorInput} />
                      </button>
                      {local && (
                        <button
                          type="button"
                          className="icon-button"
                          aria-label="Klasörde göster"
                          title="Dosyanın bir kopyasını gerçek adıyla Gezgin'de gösterir"
                          onClick={() => void act(() => api.reveal(f.id))}
                        >
                          <Icon icon={FolderOpen} />
                        </button>
                      )}
                      <button
                        type="button"
                        className={`icon-button${f.pinned ? " pinned" : ""}`}
                        aria-label={f.pinned ? "Sabitlemeyi kaldır" : "Sabitle"}
                        title={f.pinned ? "Sabitlemeyi kaldır" : "Sabitle"}
                        onClick={() => act(() => api.pin(f.id, !f.pinned))}
                      >
                        <Icon icon={f.pinned ? PinOff : Pin} />
                      </button>
                      <button
                        type="button"
                        className="icon-button file-delete"
                        aria-label="Sil"
                        title="Sil"
                        onClick={() =>
                          window.confirm(`'${f.name}' silinsin mi?`) && act(() => api.remove(f.id), `'${f.name}' silindi.`)
                        }
                      >
                        <Icon icon={Trash2} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
