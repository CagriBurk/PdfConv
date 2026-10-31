import { useEffect, useRef, type ReactNode } from "react";

interface Props {
  title: string;
  onClose: () => void;
  children: ReactNode;
  wide?: boolean;
}

/** Yerel <dialog>: Esc ile kapanır, odak içeride kalır. */
export default function Modal({ title, onClose, children, wide }: Props) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (d && !d.open) d.showModal();
  }, []);
  return (
    <dialog
      ref={ref}
      className={`modal${wide ? " wide" : ""}`}
      onClose={onClose}
      onClick={(e) => e.target === ref.current && onClose()}
    >
      <div className="modal-head">
        <h2>{title}</h2>
        <button type="button" className="icon-button" aria-label="Kapat" onClick={onClose}>
          ×
        </button>
      </div>
      <div className="modal-body">{children}</div>
    </dialog>
  );
}
