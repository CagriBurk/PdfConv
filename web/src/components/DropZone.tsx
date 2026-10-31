import { useRef, useState, type ReactNode } from "react";

interface Props {
  onFiles: (files: File[]) => void;
  accept?: string;
  multiple?: boolean;
  title?: ReactNode;
  hint?: ReactNode;
  compact?: boolean;
  disabled?: boolean;
}

/** Sürükle-bırak ya da tıklayıp seç. Klavyeyle de açılır (Enter/Boşluk). */
export default function DropZone({ onFiles, accept, multiple = true, title, hint, compact, disabled }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const depth = useRef(0);

  const take = (list: FileList | null) => {
    if (!list || disabled) return;
    const files = Array.from(list);
    if (files.length) onFiles(multiple ? files : files.slice(0, 1));
  };

  return (
    <div
      className={`dropzone${over ? " over" : ""}${compact ? " compact" : ""}${disabled ? " disabled" : ""}`}
      role="button"
      tabIndex={disabled ? -1 : 0}
      aria-disabled={disabled}
      onClick={() => !disabled && input.current?.click()}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          input.current?.click();
        }
      }}
      onDragEnter={(e) => {
        e.preventDefault();
        depth.current++;
        setOver(true);
      }}
      onDragOver={(e) => e.preventDefault()}
      onDragLeave={() => {
        depth.current = Math.max(0, depth.current - 1);
        if (depth.current === 0) setOver(false);
      }}
      onDrop={(e) => {
        e.preventDefault();
        depth.current = 0;
        setOver(false);
        take(e.dataTransfer.files);
      }}
    >
      <p className="dropzone-title">{title ?? "Dosyaları buraya bırak ya da tıklayıp seç"}</p>
      {hint && <p className="muted">{hint}</p>}
      <input
        ref={input}
        type="file"
        hidden
        accept={accept}
        multiple={multiple}
        onChange={(e) => {
          take(e.target.files);
          e.target.value = "";
        }}
      />
    </div>
  );
}
