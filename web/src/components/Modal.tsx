import { X } from "lucide-react";
import { useEffect, useId, useRef, type ReactNode } from "react";
import Icon from "./Icon";

interface Props {
  title: string;
  onClose: () => void;
  children: ReactNode;
  wide?: boolean;
  /** Geri alınamaz bir şey sürüyor (ör. yeniden başlatma): Esc, Kapat ve dışına tıklama kapatmaz. */
  busy?: boolean;
}

/** Yerel <dialog>: Esc ile kapanır, odak içeride kalır. Kapanınca (Esc, Kapat, dışına tıklama ya da
 * ekranın kendisi kaldırınca) odak açılmadan önceki öğeye döner: klavye kullanıcısı yerini
 * kaybetmez.
 *
 * İlk odak: içerikte `data-autofocus` taşıyan öğe, yoksa tarayıcının seçtiği ilk öğe (Kapat).
 * React'in `autoFocus`'u burada kullanılmaz: `showModal`'dan önce çalışır, pencere açılınca odak
 * yine Kapat'a gider; üstelik açan öğe yerine o alan "açan" sanılır.
 *
 * Yalnızca odak kaybolduysa döner. Esc'te tarayıcı pencereyi hemen kapatıp odağı kendisi geri
 * verir, `close` olayı (ve bu bileşenin kaldırılması) ise sonraki görevde gelir. Arada kullanıcı
 * oklarla başka öğeye geçtiyse odak ondan geri alınmamalı. */
export default function Modal({ title, onClose, children, wide, busy = false }: Props) {
  const ref = useRef<HTMLDialogElement>(null);
  const mouseDownBackdrop = useRef(false);
  const titleId = useId();
  useEffect(() => {
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const d = ref.current;
    if (d && !d.open) {
      d.showModal();
      d.querySelector<HTMLElement>("[data-autofocus]")?.focus();
    }
    return () => {
      const active = document.activeElement;
      const lost = !active || active === document.body || !active.isConnected || !!d?.contains(active);
      if (lost && opener?.isConnected) opener.focus({ preventScroll: true });
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className={`modal${wide ? " wide" : ""}`}
      aria-labelledby={titleId}
      aria-busy={busy || undefined}
      onCancel={(e) => {
        if (busy) e.preventDefault();
      }}
      onClose={onClose}
      onMouseDown={(e) => {
        mouseDownBackdrop.current = e.target === ref.current;
      }}
      onClick={(e) => {
        if (mouseDownBackdrop.current && e.target === ref.current && !busy) {
          onClose();
        }
      }}
    >
      <div className="modal-head">
        <h2 id={titleId}>{title}</h2>
        <button type="button" className="icon-button" aria-label="Kapat" onClick={onClose} disabled={busy}>
          <Icon icon={X} />
        </button>
      </div>
      <div className="modal-body">{children}</div>
    </dialog>
  );
}
