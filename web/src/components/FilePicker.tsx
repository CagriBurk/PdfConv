import { useState } from "react";
import { formatSize, type FileMeta } from "../api";
import { useUpload } from "../hooks";
import { passwords } from "../passwords";
import DropZone from "./DropZone";
import PasswordDialog from "./PasswordDialog";

interface Props {
  accept: string;
  kind: FileMeta["kind"];
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
    const good = metas.filter((m) => m.kind === kind);
    const bad = metas.filter((m) => m.kind !== kind);
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
        title={uploading ? `Yükleniyor… %${Math.round((progress ?? 0) * 100)}` : title}
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

export function FileRow({ file, onRemove, draggable }: { file: FileMeta; onRemove?: () => void; draggable?: boolean }) {
  return (
    <div className="file-row">
      {draggable && (
        <span className="drag-handle" aria-hidden="true">
          ⋮⋮
        </span>
      )}
      <span className="file-name">{file.name}</span>
      <span className="muted small">
        {formatSize(file.size)}
        {file.page_count ? ` · ${file.page_count} sayfa` : ""}
        {file.encrypted ? " · şifreli" : ""}
      </span>
      {onRemove && (
        <button
          type="button"
          className="icon-button"
          aria-label={`${file.name} listeden çıkar`}
          onPointerDown={(e) => e.stopPropagation()}
          onClick={onRemove}
        >
          ×
        </button>
      )}
    </div>
  );
}
