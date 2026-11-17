import { ChevronDown } from "lucide-react";
import { useEffect, useRef, useState, type FocusEvent, type KeyboardEvent } from "react";
import { GROUPS, TOOLS, GROUP_TONE } from "../tools";
import Icon from "./Icon";

const PANEL_ID = "tum-araclar";

/** Üst çubukta "Araçlar" bağlantısının yanındaki açılır panel: bütün araçlar gruplarıyla.
 * Açılır gezinme düğmesi kalıbı: odak düğmede kalır, panel sekme sırasında hemen ardından gelir;
 * ok tuşları panelde gezinir, Escape / dışarı tıklama / odağın çıkması kapatır. */
export default function ToolMenu({ section }: { section: string }) {
  const [open, setOpen] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);

  // Başka yoldan (palet, geri düğmesi) ekran değişince de kapansın.
  useEffect(() => setOpen(false), [section]);

  useEffect(() => {
    if (!open) return;
    const inside = (n: EventTarget | null) =>
      n instanceof Node && (!!panel.current?.contains(n) || !!button.current?.contains(n));
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

  const links = () => Array.from(panel.current?.querySelectorAll<HTMLAnchorElement>("a") ?? []);

  const onPanelKeyDown = (e: KeyboardEvent) => {
    const all = links();
    const i = all.indexOf(document.activeElement as HTMLAnchorElement);
    const to =
      e.key === "ArrowDown" || e.key === "ArrowRight"
        ? (i + 1) % all.length
        : e.key === "ArrowUp" || e.key === "ArrowLeft"
          ? (i - 1 + all.length) % all.length
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
    if (next instanceof Node && (panel.current?.contains(next) || button.current?.contains(next))) return;
    // Odak sayfa dışına (pencere) gitmediyse ve başka bir öğeye geçtiyse kapan.
    if (next) setOpen(false);
  };

  return (
    <>
      <button
        ref={button}
        type="button"
        className="nav-pill nav-caret"
        aria-label="Tüm araçlar menüsü"
        aria-expanded={open}
        aria-controls={PANEL_ID}
        onClick={() => setOpen((o) => !o)}
        onBlur={onBlur}
        onKeyDown={(e) => {
          if (e.key !== "ArrowDown") return;
          e.preventDefault();
          setOpen(true);
          // Panel bir sonraki çizimde var olur.
          requestAnimationFrame(() => (links().find((a) => a.getAttribute("aria-current")) ?? links()[0])?.focus());
        }}
      >
        <Icon icon={ChevronDown} size={16} className={open ? "flip" : undefined} />
      </button>
      {/* Yalnızca görünüm; dışarı tıklamayı belge dinleyicisi yakalar. Üst çubuğu örtmez. */}
      {open && <div className="tool-menu-scrim" aria-hidden="true" />}
      {open && (
        <div ref={panel} id={PANEL_ID} className="tool-menu" onKeyDown={onPanelKeyDown} onBlur={onBlur}>
          <div className="tool-menu-inner">
            {GROUPS.map((group) => {
              const tone = GROUP_TONE[group];
              const headId = `${PANEL_ID}-${tone}`;
              return (
                <div key={group}>
                  <p id={headId} className="tool-menu-head">
                    <span className={`dot ${tone}`} aria-hidden="true" />
                    {group}
                  </p>
                  <ul aria-labelledby={headId}>
                    {TOOLS.filter((t) => t.group === group).map((t) => {
                      const current = t.route === section;
                      return (
                        <li key={t.id}>
                          <a
                            className={`tool-menu-row${current ? " on" : ""}`}
                            href={`#/${t.route}`}
                            aria-current={current ? "page" : undefined}
                            onClick={() => {
                              setOpen(false);
                              // Aynı ekransa ekran değişmez; odak boşa düşmesin.
                              if (current) button.current?.focus();
                            }}
                          >
                            <span className={`tile sm ${t.tone}`}>
                              <Icon icon={t.icon} size={16} />
                            </span>
                            {t.title}
                          </a>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </>
  );
}
