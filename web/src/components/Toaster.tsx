import { CircleAlert, CircleCheck, Info, X } from "lucide-react";
import { dismiss, useToasts, type ToastKind } from "../toast";
import Icon from "./Icon";

const KIND_ICON = { ok: CircleCheck, info: Info, error: CircleAlert } satisfies Record<ToastKind, unknown>;

/** Bildirimlerin gösterildiği köşe. Ekran okuyucu: hatalar `alert`, diğerleri `status`. */
export default function Toaster() {
  const toasts = useToasts();
  return (
    <div className="toaster" aria-live="polite">
      {toasts.map((t) => (
        <div key={t.id} className={`toast ${t.kind}`} role={t.kind === "error" ? "alert" : "status"}>
          <Icon icon={KIND_ICON[t.kind]} className="toast-icon" />
          <span className="toast-text">
            {t.text}
            {t.count > 1 && <span className="toast-count"> ×{t.count}</span>}
          </span>
          <button type="button" className="icon-button" aria-label="Bildirimi kapat" onClick={() => dismiss(t.id)}>
            <Icon icon={X} size={17} />
          </button>
        </div>
      ))}
    </div>
  );
}
