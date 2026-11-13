import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { EnginesResponse } from "../api";
import { idsFrom, navigate, type Route } from "../router";
import { TOOLS, type Tool } from "../tools";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  route: Route;
  engines: EnginesResponse | null;
}

interface PaletteItem {
  id: string;
  kind: "tool" | "nav";
  title: string;
  subtitle: string;
  group: string;
  route: string;
  tool?: Tool;
  searchText: string;
  lacking: string[];
  handoff: boolean;
}

const PDF_ROUTES = new Set([
  "duzenle",
  "editor",
  "birlestir",
  "bol",
  "yazdirma",
  "filigran",
  "sayfa-no",
  "sikistir",
  "ocr",
  "guvenlik",
  "resme",
  "word",
  "excel",
]);

const NON_PDF_ROUTES = new Set(["md", "office", "resimden"]);

const QUICK_ACTIONS = [
  { id: "nav-home", title: "Ana Sayfa", subtitle: "Tüm araçlar ve dosya bırakma alanı", route: "araclar", group: "Gezinme" },
  { id: "nav-files", title: "Dosyalar", subtitle: "Yüklenen ve oluşturulan dosyalar", route: "isler", group: "Gezinme" },
  { id: "nav-jobs", title: "İşler", subtitle: "Çalışan ve tamamlanan arka plan işleri", route: "isler", group: "Gezinme" },
  { id: "nav-settings", title: "Ayarlar", subtitle: "Kayıt kasası, saklama süresi, telefon modu, motorlar", route: "ayarlar", group: "Gezinme" },
];

/** Arama eşleştirmesinde Türkçe harf ve büyük/küçük harf duyarlılığını kaldırır. */
function normalizeTr(str: string): string {
  return str
    .replace(/İ/g, "i")
    .replace(/I/g, "ı")
    .toLocaleLowerCase("tr")
    .replace(/ç/g, "c")
    .replace(/ğ/g, "g")
    .replace(/ı/g, "i")
    .replace(/ö/g, "o")
    .replace(/ş/g, "s")
    .replace(/ü/g, "u")
    .trim();
}

function extractActiveFiles(route: Route): { section: string; ids: string[] } {
  const [section = "araclar", pathId] = route.path;
  if (pathId) return { section, ids: [pathId] };
  return { section, ids: idsFrom(route) };
}

function canHandoffToTool(section: string, ids: string[], targetRoute: string): boolean {
  if (!ids.length) return false;
  if (NON_PDF_ROUTES.has(section)) return section === targetRoute;
  if (PDF_ROUTES.has(targetRoute)) return true;
  return section === targetRoute;
}

function CommandPaletteDialog({
  onClose,
  route,
  engines,
}: {
  onClose: () => void;
  route: Route;
  engines: EnginesResponse | null;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const mouseDownBackdrop = useRef(false);
  const listId = useId();
  const [query, setQuery] = useState("");
  const [selectedIdx, setSelectedIdx] = useState(0);

  useEffect(() => {
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const d = dialogRef.current;
    if (d && !d.open) d.showModal();
    inputRef.current?.focus();
    return () => {
      const active = document.activeElement;
      const lost = !active || active === document.body || !active.isConnected || !!d?.contains(active);
      if (lost && opener?.isConnected) opener.focus({ preventScroll: true });
    };
  }, []);

  const { section, ids } = useMemo(() => extractActiveFiles(route), [route]);

  const allItems = useMemo<PaletteItem[]>(() => {
    const missingFor = (keys: string[] = []) =>
      engines ? engines.engines.filter((e) => keys.includes(e.key) && !e.ok).map((e) => e.name) : [];

    const toolItems: PaletteItem[] = TOOLS.map((t) => ({
      id: `tool-${t.id}`,
      kind: "tool",
      title: t.title,
      subtitle: t.description,
      group: t.group,
      route: t.route,
      tool: t,
      searchText: normalizeTr(`${t.title} ${t.description} ${t.group} ${t.route}`),
      lacking: missingFor(t.needs),
      handoff: canHandoffToTool(section, ids, t.route),
    }));

    const navItems: PaletteItem[] = QUICK_ACTIONS.map((a) => ({
      id: a.id,
      kind: "nav",
      title: a.title,
      subtitle: a.subtitle,
      group: a.group,
      route: a.route,
      searchText: normalizeTr(`${a.title} ${a.subtitle} ${a.group} ${a.route}`),
      lacking: [],
      handoff: false,
    }));

    return [...toolItems, ...navItems];
  }, [engines, ids, section]);

  const items = useMemo(() => {
    const q = normalizeTr(query);
    if (!q) return allItems;
    const tokens = q.split(/\s+/).filter(Boolean);
    return allItems.filter((item) => tokens.every((tok) => item.searchText.includes(tok)));
  }, [allItems, query]);

  const activeIndex = items.length ? Math.min(selectedIdx, items.length - 1) : -1;

  useEffect(() => {
    if (activeIndex < 0) return;
    const el = listRef.current?.children[activeIndex] as HTMLElement | undefined;
    el?.scrollIntoView({ block: "nearest" });
  }, [activeIndex]);

  const activate = (item: PaletteItem) => {
    onClose();
    if (item.kind === "tool" && item.handoff && ids.length > 0) {
      if (item.route === "duzenle" || item.route === "editor") {
        navigate(`${item.route}/${ids[0]}`);
      } else {
        navigate(item.route, { dosya: ids });
      }
      return;
    }
    navigate(item.route);
  };

  const onInputKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!items.length) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIdx((i) => (i + 1) % items.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIdx((i) => (i - 1 + items.length) % items.length);
    } else if (e.key === "Home") {
      e.preventDefault();
      setSelectedIdx(0);
    } else if (e.key === "End") {
      e.preventDefault();
      setSelectedIdx(items.length - 1);
    } else if (e.key === "Enter" && activeIndex >= 0) {
      e.preventDefault();
      activate(items[activeIndex]);
    }
  };

  const hasPdfHandoff = ids.length > 0 && !NON_PDF_ROUTES.has(section);

  return (
    <dialog
      ref={dialogRef}
      className="cmd-palette"
      aria-label="Komut paleti"
      onClose={onClose}
      onMouseDown={(e) => {
        mouseDownBackdrop.current = e.target === dialogRef.current;
      }}
      onClick={(e) => {
        if (mouseDownBackdrop.current && e.target === dialogRef.current) onClose();
      }}
    >
      <div className="cmd-palette-head">
        <input
          ref={inputRef}
          type="search"
          className="cmd-palette-input"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setSelectedIdx(0);
          }}
          onKeyDown={onInputKeyDown}
          placeholder="Araç veya ekran ara… (ör. yazdır, kırp, şifre, dosyalar)"
          aria-label="Araç veya komut ara"
          role="combobox"
          aria-expanded={true}
          aria-controls={listId}
          aria-activedescendant={activeIndex >= 0 ? items[activeIndex].id : undefined}
        />
        <button type="button" className="icon-button" aria-label="Kapat" onClick={onClose}>
          ×
        </button>
      </div>
      {hasPdfHandoff && (
        <div className="cmd-palette-context">
          Aktif PDF dosyası seçilen araca otomatik aktarılır.
        </div>
      )}
      <ul ref={listRef} id={listId} className="cmd-palette-list" role="listbox" aria-label="Sonuçlar">
        {items.length === 0 ? (
          <li className="cmd-palette-empty muted">Eşleşen araç veya ekran bulunamadı.</li>
        ) : (
          items.map((item, idx) => {
            const selected = idx === activeIndex;
            return (
              <li
                key={item.id}
                id={item.id}
                role="option"
                aria-selected={selected}
                className={`cmd-palette-item${selected ? " active" : ""}`}
                onMouseMove={() => {
                  if (selectedIdx !== idx) setSelectedIdx(idx);
                }}
                onClick={() => activate(item)}
              >
                <div className="cmd-palette-item-main">
                  <strong>{item.title}</strong>
                  <span className="muted small">{item.subtitle}</span>
                </div>
                <div className="cmd-palette-item-meta">
                  {item.handoff && <span className="cmd-badge">Aktif dosya</span>}
                  {item.lacking.length > 0 && <span className="cmd-badge warn">Eksik: {item.lacking.join(", ")}</span>}
                  <span className="cmd-group">{item.group}</span>
                </div>
              </li>
            );
          })
        )}
      </ul>
      <div className="cmd-palette-foot muted small">
        <span><kbd>↑</kbd><kbd>↓</kbd> gezin</span>
        <span><kbd>Enter</kbd> aç</span>
        <span><kbd>Esc</kbd> kapat</span>
      </div>
    </dialog>
  );
}

/** Küresel Ctrl+K / Cmd+K komut paleti: tüm araçlar ve ana ekranlar arasında hızlı geçiş. */
export default function CommandPalette({ open, onOpenChange, route, engines }: Props) {
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        e.stopPropagation();
        onOpenChange(!open);
      }
    };
    window.addEventListener("keydown", onKeyDown, { capture: true });
    return () => window.removeEventListener("keydown", onKeyDown, { capture: true });
  }, [open, onOpenChange]);

  if (!open) return null;
  return <CommandPaletteDialog onClose={() => onOpenChange(false)} route={route} engines={engines} />;
}
