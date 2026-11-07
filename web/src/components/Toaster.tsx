import { dismiss, useToasts } from "../toast";

/** Bildirimlerin gösterildiği köşe. Ekran okuyucu: hatalar `alert`, diğerleri `status`. */
export default function Toaster() {
  const toasts = useToasts();
  return (
    <div className="toaster" aria-live="polite">
      {toasts.map((t) => (
        <div key={t.id} className={`toast ${t.kind}`} role={t.kind === "error" ? "alert" : "status"}>
          <span className="toast-text">
            {t.text}
            {t.count > 1 && <span className="toast-count"> ×{t.count}</span>}
          </span>
          <button type="button" className="icon-button" aria-label="Bildirimi kapat" onClick={() => dismiss(t.id)}>
            ×
          </button>
        </div>
      ))}
    </div>
  );
}
