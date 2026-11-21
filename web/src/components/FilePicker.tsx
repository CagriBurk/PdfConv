import { GripVertical, LoaderCircle, Upload, X } from "lucide-react";
import { useId, useState, type ReactNode } from "react";
import { formatSize, type FileMeta } from "../api";
import { useUpload } from "../hooks";
import { passwords } from "../passwords";
import DropZone from "./DropZone";
import Icon from "./Icon";
import PasswordDialog from "./PasswordDialog";

interface Props {
  accept: string;
  kind: FileMeta["kind"] | FileMeta["kind"][];
  multiple?: boolean;
  title: string;
  onAdd: (files: FileMeta[]) => void;
  compact?: boolean;
}

/**
 * Yükleme + tür kontrolü + (PDF ise) şifre sorma. Doğru türdeki ve açılabilen dosyaları verir.
 */
export default function FilePicker({ accept, kind, multiple = true, title, onAdd, compact }: Props) {
  const { upload, uploading, progress, error, setError } = useUpload();
  const [queue, setQueue] = useState<FileMeta[]>([]);
  const [ready, setReady] = useState<FileMeta[]>([]);

  const finish = (accepted: FileMeta[]) => {
    if (accepted.length) onAdd(accepted);
    setReady([]);
  };

  const next = (rest: FileMeta[], accepted: FileMeta[]) => {
    const idx = rest.findIndex((f) => f.encrypted && !passwords.get(f.id));
    if (idx === -1) return finish([...accepted, ...rest]);
    setReady([...accepted, ...rest.slice(0, idx)]);
    setQueue(rest.slice(idx));
  };

  const onFiles = async (files: File[]) => {
    const metas = await upload(files);
    const kinds = Array.isArray(kind) ? kind : [kind];
    const good = metas.filter((m) => kinds.includes(m.kind));
    const bad = metas.filter((m) => !kinds.includes(m.kind));
    if (bad.length) setError(`Bu araç için uygun olmayan dosyalar atlandı: ${bad.map((b) => b.name).join(", ")}`);
    next(good, []);
  };

  return (
    <>
      <DropZone
        onFiles={onFiles}
        accept={accept}
        multiple={multiple}
        compact={compact}
        disabled={uploading}
        title={
          <>
            <span className="drop-icon">
              <Icon icon={uploading ? LoaderCircle : Upload} className={uploading ? "spin" : undefined} />
            </span>
            {uploading ? `Yükleniyor… %${Math.round((progress ?? 0) * 100)}` : title}
          </>
        }
        hint={compact ? undefined : "ya da tıklayıp seç"}
      />
      {error && <p className="error-text">{error}</p>}
      {queue[0] && (
        <PasswordDialog
          file={queue[0]}
          onDone={(ok) => {
            const [head, ...rest] = queue;
            setQueue([]);
            next(rest, ok ? [...ready, head] : ready);
          }}
        />
      )}
    </>
  );
}

/** Dosya türü rozetindeki kısa ad: uzantı, yoksa tür. */
export function fileType(name: string, kind: FileMeta["kind"]): string {
  const dot = name.lastIndexOf(".");
  const ext = dot > 0 ? name.slice(dot + 1) : kind;
  return ext.slice(0, 4).toLocaleUpperCase("tr");
}

/** Dosya türü rozetinin renk sınıfı: göz tek bakışta PDF / Word / Excel / Sunu / Resim / MD ayırır. */
export function fileTypeTone(name: string, kind: FileMeta["kind"]): string {
  const dot = name.lastIndexOf(".");
  const ext = dot > 0 ? name.slice(dot).toLowerCase() : "";
  if (kind === "pdf" || ext === ".pdf") return "ft-pdf";
  if (kind === "image") return "ft-img";
  if (kind === "markdown") return "ft-md";
  if ([".xlsx", ".xls", ".xlsm", ".ods", ".csv"].includes(ext)) return "ft-sheet";
  if ([".pptx", ".ppt", ".pptm", ".odp"].includes(ext)) return "ft-slide";
  if (kind === "office" || [".docx", ".doc", ".docm", ".odt", ".rtf", ".wpd"].includes(ext)) return "ft-doc";
  return "ft-other";
}

/** Özet kartı için: "2 PDF · 26.8 MB" (boşsa "—"). */
export function filesSummary(files: FileMeta[], noun = "dosya"): string {
  if (!files.length) return "—";
  return `${files.length} ${noun} · ${formatSize(files.reduce((n, f) => n + f.size, 0))}`;
}

/** Tek dosyalı araçların özeti: "12 sayfa · 2.3 MB" (yoksa "—"). */
export function fileSummary(file: FileMeta | null): string {
  if (!file) return "—";
  return file.page_count ? `${file.page_count} sayfa · ${formatSize(file.size)}` : formatSize(file.size);
}

/** Araç ekranının dosya kartı: başlık, sayı rozeti, isteğe bağlı açıklama. */
export function FilesCard({
  title = "Dosyalar",
  count = 0,
  hint,
  children,
}: {
  title?: string;
  count?: number;
  hint?: ReactNode;
  children: ReactNode;
}) {
  const id = useId();
  return (
    <section className="card tool-files" aria-labelledby={id}>
      <div className="card-head">
        <h2 id={id}>{title}</h2>
        {count > 0 && <span className="chip small">{count}</span>}
      </div>
      {hint && <p className="muted small card-hint">{hint}</p>}
      {children}
    </section>
  );
}

export function FileRow({ file, onRemove, draggable }: { file: FileMeta; onRemove?: () => void; draggable?: boolean }) {
  return (
    <div className={`file-row${draggable ? " draggable" : ""}`}>
      {draggable && (
        <span className="drag-handle" aria-hidden="true">
          <Icon icon={GripVertical} />
        </span>
      )}
      <span className={`ftype ${fileTypeTone(file.name, file.kind)}`} aria-hidden="true">
        {fileType(file.name, file.kind)}
      </span>
      <span className="file-text">
        <span className="file-name" title={file.name}>
          {file.name}
        </span>
        <span className="file-meta">
          {formatSize(file.size)}
          {file.page_count ? ` · ${file.page_count} sayfa` : ""}
          {file.encrypted ? " · şifreli" : ""}
        </span>
      </span>
      {onRemove && (
        <button
          type="button"
          className="icon-button"
          aria-label={`${file.name} listeden çıkar`}
          onPointerDown={(e) => e.stopPropagation()}
          onClick={onRemove}
        >
          <Icon icon={X} />
        </button>
      )}
    </div>
  );
}
