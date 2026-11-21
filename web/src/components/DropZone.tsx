import { Upload } from "lucide-react";
import { useId, useRef, useState, type ReactNode } from "react";
import Icon from "./Icon";

interface Props {
  onFiles: (files: File[]) => void;
  accept?: string;
  multiple?: boolean;
  title?: ReactNode;
  hint?: ReactNode;
  compact?: boolean;
  /** Ana sayfanın büyük bırakma alanı: çizim ve "Dosya seç" düğmesi görünümü. */
  hero?: boolean;
  disabled?: boolean;
}

/** Ana sayfa bırakma alanının çizimi (iki sayfa ve yükleme oku; üzerine gelince canlanır). */
function DropArt() {
  return (
    <svg className="dropzone-art" width="104" height="80" viewBox="0 0 104 80" aria-hidden="true">
      <g className="art-sheet-back">
        <rect className="art-sheet" x="24" y="12" width="44" height="56" rx="7" strokeWidth="1.5" transform="rotate(-9 46 40)" />
      </g>
      <g className="art-sheet-front">
        <rect className="art-sheet" x="34" y="8" width="44" height="56" rx="7" strokeWidth="1.5" />
        <path className="art-lines" d="M43 24h22M43 32h26M43 40h18" strokeWidth="3" strokeLinecap="round" />
      </g>
      <g className="art-badge-group">
        <circle className="art-badge" cx="74" cy="56" r="15" />
        <path className="art-arrow" d="M74 63V49M68 55l6-6 6 6" fill="none" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
      </g>
    </svg>
  );
}

/** Sürükle-bırak ya da tıklayıp seç. Klavyeyle de açılır (Enter/Boşluk). */
export default function DropZone({ onFiles, accept, multiple = true, title, hint, compact, hero, disabled }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const depth = useRef(0);
  const id = useId();

  const take = (list: FileList | null) => {
    if (!list || disabled) return;
    const files = Array.from(list);
    if (files.length) onFiles(multiple ? files : files.slice(0, 1));
  };

  return (
    <div
      className={`dropzone${over ? " over" : ""}${compact ? " compact" : ""}${hero ? " hero" : ""}${disabled ? " disabled" : ""}`}
      role="button"
      tabIndex={disabled ? -1 : 0}
      aria-disabled={disabled}
      aria-labelledby={`${id}-t`}
      aria-describedby={hint ? `${id}-h` : undefined}
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
      {hero && <DropArt />}
      <div>
        <p id={`${id}-t`} className="dropzone-title">
          {title ?? "Dosyaları buraya bırak ya da tıklayıp seç"}
        </p>
        {hint && (
          <p id={`${id}-h`} className="muted">
            {hint}
          </p>
        )}
      </div>
      {/* Bütün alan zaten düğme: bu yalnızca görünüm (iç içe düğme olmasın). */}
      {hero && (
        <span className="dropzone-cta" aria-hidden="true">
          <Icon icon={Upload} size={18} strokeWidth={2.2} />
          Dosya seç
        </span>
      )}
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
