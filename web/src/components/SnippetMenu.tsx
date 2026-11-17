import { Bookmark, BookmarkPlus, ChevronDown, LayoutTemplate, Pencil, Replace, Trash2 } from "lucide-react";
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type FocusEvent,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import { api, errorMessage, type UserSnippet } from "../api";
import { firstLine, presetBody, SNIPPET_GROUPS, SNIPPETS, suggestName } from "../snippets";
import { toast } from "../toast";
import Icon from "./Icon";
import Modal from "./Modal";

const PANEL_ID = "sablon-menusu";
const NAME_MAX = 60;

export interface SnippetSource {
  text: string;
  /** Düzenleyicide seçim var mı (yoksa `text` notun tamamı). */
  selection: boolean;
}

export interface InsertableSnippet {
  label: string;
  body: string;
  bodyWithFrontMatter?: string;
  user: boolean;
}

interface Props {
  /** Kaydetmek / üzerine yazmak için: seçili metin, seçim yoksa notun tamamı. */
  getSource: () => SnippetSource;
  onInsert: (snippet: InsertableSnippet) => void;
}

type Dialog =
  | { kind: "save"; source: SnippetSource }
  | { kind: "rename"; item: UserSnippet }
  | { kind: "overwrite"; item: UserSnippet; source: SnippetSource }
  | { kind: "delete"; item: UserSnippet };

/** "Şablon ekle" düğmesi + açılır panel: kullanıcının kendi şablonları (kaydet, yeniden adlandır,
 * üzerine yaz, sil) ve gruplu hazır şablonlar. Üst çubuktaki araç menüsünün kalıbı: odak düğmede
 * kalır, panel sekme sırasında hemen ardından gelir; ok tuşları satırlarda gezinir, Escape /
 * dışarı tıklama / odağın çıkması kapatır. */
export default function SnippetMenu({ getSource, onInsert }: Props) {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<UserSnippet[] | null>(null);
  const [folder, setFolder] = useState("");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [hasSelection, setHasSelection] = useState(false);
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const wrap = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    try {
      const res = await api.snippets();
      setItems(res.items);
      setFolder(res.folder);
      setLoadError(null);
    } catch (e) {
      setLoadError(errorMessage(e));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!open) return;
    const inside = (n: EventTarget | null) => n instanceof Node && !!wrap.current?.contains(n);
    const onPointerDown = (e: PointerEvent) => {
      if (!inside(e.target)) setOpen(false);
    };
    const onKeyDown = (e: globalThis.KeyboardEvent) => {
      if (e.key !== "Escape" || document.querySelector("dialog[open]")) return;
      setOpen(false);
      button.current?.focus();
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  // Panel düğmenin altında açılır ama pencereden taşmaz (dar ekranda düğme sağda kalabilir).
  useLayoutEffect(() => {
    if (!open) return;
    const place = () => {
      const w = wrap.current;
      const p = panel.current;
      if (!w || !p) return;
      const left = w.getBoundingClientRect().left;
      const max = document.documentElement.clientWidth - 16 - p.offsetWidth;
      p.style.left = `${Math.max(16, Math.min(left, max)) - left}px`;
    };
    place();
    window.addEventListener("resize", place);
    return () => window.removeEventListener("resize", place);
  }, [open]);

  const rows = () => Array.from(panel.current?.querySelectorAll<HTMLButtonElement>("[data-row]") ?? []);

  const openPanel = (focusFirst: boolean) => {
    setHasSelection(getSource().selection);
    setOpen(true);
    void load(); // klasöre elle atılan dosyalar da görünsün
    // Panel bir sonraki çizimde var olur.
    if (focusFirst) requestAnimationFrame(() => rows()[0]?.focus());
  };

  const onPanelKeyDown = (e: KeyboardEvent) => {
    const all = rows();
    const i = all.indexOf(document.activeElement as HTMLButtonElement);
    const to =
      e.key === "ArrowDown"
        ? (i + 1) % all.length
        : e.key === "ArrowUp"
          ? i <= 0
            ? all.length - 1
            : i - 1
          : e.key === "Home"
            ? 0
            : e.key === "End"
              ? all.length - 1
              : null;
    if (to === null) return;
    e.preventDefault();
    all[to]?.focus();
  };

  const onBlur = (e: FocusEvent) => {
    const next = e.relatedTarget;
    if (next instanceof Node && wrap.current?.contains(next)) return;
    // Odak pencere dışına gitmediyse ve başka bir öğeye geçtiyse kapan.
    if (next) setOpen(false);
  };

  const insert = (snippet: InsertableSnippet) => {
    setOpen(false);
    onInsert(snippet);
  };

  /** Pencere açılmadan odak düğmeye alınır: pencere kapanınca oraya döner (panel kaldırılır). */
  const openDialog = (d: Dialog) => {
    button.current?.focus();
    setOpen(false);
    setDialog(d);
  };

  const done = async (message: string) => {
    setDialog(null);
    toast.ok(message);
    await load();
  };

  const saveLabel = hasSelection ? "Seçimi şablon olarak kaydet…" : "Notu şablon olarak kaydet…";

  return (
    <div className="snippet-menu" ref={wrap}>
      <button
        ref={button}
        type="button"
        className="snippet-trigger"
        aria-expanded={open}
        aria-controls={PANEL_ID}
        onClick={() => (open ? setOpen(false) : openPanel(false))}
        onBlur={onBlur}
        onKeyDown={(e) => {
          if (e.key !== "ArrowDown") return;
          e.preventDefault();
          if (open) rows()[0]?.focus();
          else openPanel(true);
        }}
      >
        <Icon icon={LayoutTemplate} size={17} />
        Şablon ekle
        <Icon icon={ChevronDown} size={16} className={open ? "flip" : undefined} />
      </button>
      {open && (
        <div ref={panel} id={PANEL_ID} className="snippet-panel" onKeyDown={onPanelKeyDown} onBlur={onBlur}>
          <section aria-labelledby={`${PANEL_ID}-benim`}>
            <p id={`${PANEL_ID}-benim`} className="snippet-head">
              Benim şablonlarım
            </p>
            {loadError ? (
              <p className="snippet-note error-text">Şablonların okunamadı: {loadError}</p>
            ) : items === null ? (
              <p className="snippet-note muted">Yükleniyor…</p>
            ) : items.length === 0 ? (
              <p className="snippet-note muted">
                Sık kullandığın bir metni düzenleyicide seç ve aşağıdan kaydet; burada tek tıkla eklenir.
              </p>
            ) : (
              <ul>
                {items.map((s) => (
                  <li key={s.name} className="snippet-user">
                    <button
                      type="button"
                      className="snippet-row"
                      data-row
                      onClick={() => insert({ label: s.name, body: s.body, user: true })}
                    >
                      <Icon icon={Bookmark} size={17} />
                      <span className="snippet-text">
                        <span className="snippet-name">{s.name}</span>
                        <span className="snippet-hint">{firstLine(s.body)}</span>
                      </span>
                    </button>
                    <button
                      type="button"
                      className="icon-button"
                      aria-label={`${s.name}: yeniden adlandır`}
                      title="Yeniden adlandır"
                      onClick={() => openDialog({ kind: "rename", item: s })}
                    >
                      <Icon icon={Pencil} size={16} />
                    </button>
                    <button
                      type="button"
                      className="icon-button"
                      aria-label={`${s.name}: üzerine yaz`}
                      title="Üzerine yaz: içeriği seçili metinle (seçim yoksa notun tamamıyla) değiştir"
                      onClick={() => openDialog({ kind: "overwrite", item: s, source: getSource() })}
                    >
                      <Icon icon={Replace} size={16} />
                    </button>
                    <button
                      type="button"
                      className="icon-button"
                      aria-label={`${s.name}: sil`}
                      title="Sil"
                      onClick={() => openDialog({ kind: "delete", item: s })}
                    >
                      <Icon icon={Trash2} size={16} />
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <button
              type="button"
              className="snippet-row snippet-save"
              data-row
              onClick={() => openDialog({ kind: "save", source: getSource() })}
            >
              <Icon icon={BookmarkPlus} size={17} />
              <span className="snippet-name">{saveLabel}</span>
            </button>
          </section>
          {SNIPPET_GROUPS.map((group, gi) => (
            <section key={group} aria-labelledby={`${PANEL_ID}-${gi}`}>
              <p id={`${PANEL_ID}-${gi}`} className="snippet-head">
                {group}
              </p>
              <ul>
                {SNIPPETS.filter((p) => p.group === group).map((p) => (
                  <li key={p.id}>
                    <button
                      type="button"
                      className="snippet-row"
                      data-row
                      onClick={() =>
                        insert({
                          label: p.label,
                          body: presetBody(p),
                          bodyWithFrontMatter: p.bodyWithFrontMatter,
                          user: false,
                        })
                      }
                    >
                      <Icon icon={p.icon} size={17} />
                      <span className="snippet-text">
                        <span className="snippet-name">{p.label}</span>
                        <span className="snippet-hint">{p.hint}</span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}

      {dialog?.kind === "save" && (
        <NameDialog
          title="Şablon olarak kaydet"
          initial={suggestName(dialog.source.text)}
          submitLabel="Kaydet"
          onClose={() => setDialog(null)}
          onSubmit={async (name) => {
            const saved = await api.addSnippet(name, dialog.source.text);
            await done(`"${saved.name}" şablonu kaydedildi: Şablon ekle → Benim şablonlarım.`);
          }}
        >
          <SourcePreview source={dialog.source} />
          {folder && (
            <p className="snippet-folder small muted">
              Şablonlar bu bilgisayarda .md dosyası olarak saklanır; klasöre elle de dosya atabilirsin:{" "}
              <span className="mono break">{folder}</span>
            </p>
          )}
        </NameDialog>
      )}
      {dialog?.kind === "rename" && (
        <NameDialog
          title="Şablonu yeniden adlandır"
          initial={dialog.item.name}
          submitLabel="Yeniden adlandır"
          onClose={() => setDialog(null)}
          onSubmit={async (name) => {
            const saved = await api.updateSnippet(dialog.item.name, { new_name: name });
            await done(`Şablonun yeni adı: "${saved.name}".`);
          }}
        />
      )}
      {dialog?.kind === "overwrite" && (
        <ConfirmDialog
          title="Şablonun üzerine yaz"
          confirmLabel="Üzerine yaz"
          onClose={() => setDialog(null)}
          onConfirm={async () => {
            await api.updateSnippet(dialog.item.name, { body: dialog.source.text });
            await done(`"${dialog.item.name}" şablonunun içeriği güncellendi.`);
          }}
        >
          <p>
            <strong className="break">{dialog.item.name}</strong> şablonunun içeriği{" "}
            {dialog.source.selection ? "seçili metinle" : "notun tamamıyla"} değiştirilecek. Eski içerik geri
            alınamaz.
          </p>
          <SourcePreview source={dialog.source} />
        </ConfirmDialog>
      )}
      {dialog?.kind === "delete" && (
        <ConfirmDialog
          title="Şablonu sil"
          confirmLabel="Sil"
          onClose={() => setDialog(null)}
          onConfirm={async () => {
            await api.removeSnippet(dialog.item.name);
            await done(`"${dialog.item.name}" şablonu silindi.`);
          }}
        >
          <p>
            <strong className="break">{dialog.item.name}</strong> şablonu silinsin mi? Dosyası şablon
            klasöründen kaldırılır; geri alınamaz.
          </p>
        </ConfirmDialog>
      )}
    </div>
  );
}

/** Kaydedilecek metnin ilk satırları (düz metin; HTML olarak yorumlanmaz). */
function SourcePreview({ source }: { source: SnippetSource }) {
  const lines = source.text.replace(/\n+$/, "").split("\n");
  const shown = lines.slice(0, 8).join("\n");
  return (
    <figure className="snippet-source">
      <figcaption className="small muted">
        {source.selection ? "Seçili metin" : "Notun tamamı"} · {lines.length} satır
      </figcaption>
      <pre>{lines.length > 8 ? `${shown}\n…` : shown}</pre>
    </figure>
  );
}

function NameDialog({
  title,
  initial,
  submitLabel,
  onSubmit,
  onClose,
  children,
}: {
  title: string;
  initial: string;
  submitLabel: string;
  onSubmit: (name: string) => Promise<void>;
  onClose: () => void;
  children?: ReactNode;
}) {
  const [value, setValue] = useState(initial);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => input.current?.select(), []);

  return (
    <Modal title={title} onClose={onClose}>
      <form
        className="snippet-form"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError(null);
          try {
            await onSubmit(value);
          } catch (err) {
            setError(errorMessage(err));
            setBusy(false);
          }
        }}
      >
        {children}
        <label className="field">
          Şablon adı
          <input
            ref={input}
            className="input"
            autoFocus
            maxLength={NAME_MAX}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            aria-describedby={error ? `${PANEL_ID}-hata` : undefined}
            aria-invalid={error ? true : undefined}
          />
        </label>
        {error && (
          <p id={`${PANEL_ID}-hata`} className="error-text" role="alert">
            {error}
          </p>
        )}
        <div className="modal-actions">
          <button type="button" onClick={onClose}>
            Vazgeç
          </button>
          <button type="submit" className="primary" disabled={busy || !value.trim()}>
            {submitLabel}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function ConfirmDialog({
  title,
  confirmLabel,
  onConfirm,
  onClose,
  children,
}: {
  title: string;
  confirmLabel: string;
  onConfirm: () => Promise<void>;
  onClose: () => void;
  children: ReactNode;
}) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <Modal title={title} onClose={onClose}>
      <div className="snippet-form">
        {children}
        {error && (
          <p className="error-text" role="alert">
            {error}
          </p>
        )}
        <div className="modal-actions">
          <button type="button" autoFocus onClick={onClose}>
            Vazgeç
          </button>
          <button
            type="button"
            className="danger"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              setError(null);
              try {
                await onConfirm();
              } catch (err) {
                setError(errorMessage(err));
                setBusy(false);
              }
            }}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </Modal>
  );
}
