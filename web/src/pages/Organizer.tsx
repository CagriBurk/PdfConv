import {
  closestCenter,
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import {
  arrayMove,
  rectSortingStrategy,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, errorMessage, type FileMeta } from "../api";
import DropZone from "../components/DropZone";
import JobPanel from "../components/JobPanel";
import Modal from "../components/Modal";
import PageHeader from "../components/PageHeader";
import PasswordDialog from "../components/PasswordDialog";
import Thumb from "../components/Thumb";
import { useJob, useUpload } from "../hooks";
import { passwords } from "../passwords";
import { forgetPdf } from "../pdf";
import { navigate } from "../router";
import { ACCEPT } from "../tools";

interface Item {
  key: string;
  file?: string;
  page: number;
  rotate: number;
  blank?: boolean;
}

const COLORS = ["#c2410c", "#2563eb", "#15803d", "#7e22ce", "#b91c1c", "#0e7490", "#a16207"];
let seq = 0;
const newKey = () => `p${++seq}`;

function pagesOf(meta: FileMeta): Item[] {
  return Array.from({ length: meta.page_count ?? 0 }, (_, page) => ({ key: newKey(), file: meta.id, page, rotate: 0 }));
}

export default function Organizer({ fileId }: { fileId?: string }) {
  const [base, setBase] = useState<FileMeta | null>(null);
  const [sources, setSources] = useState<Record<string, FileMeta>>({});
  const [items, setItems] = useState<Item[]>([]);
  const [past, setPast] = useState<Item[][]>([]);
  const [future, setFuture] = useState<Item[][]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [anchor, setAnchor] = useState<string | null>(null);
  const [locked, setLocked] = useState<FileMeta | null>(null); // şifre bekleyen dosya
  const pendingUnlock = useRef<((ok: boolean) => void) | null>(null);
  const [preview, setPreview] = useState<Item | null>(null);
  const [dragging, setDragging] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [noText, setNoText] = useState(false);
  const addInput = useRef<HTMLInputElement>(null);
  const { upload, uploading } = useUpload();
  const saveJob = useJob();
  const dirty = past.length > 0;

  // Şifreli dosyada şifre sorar; doğru girilene ya da vazgeçilene kadar bekler.
  const unlock = useCallback(
    (meta: FileMeta) =>
      new Promise<boolean>((resolve) => {
        if (!meta.encrypted || passwords.get(meta.id)) return resolve(true);
        pendingUnlock.current = resolve;
        setLocked(meta);
      }),
    [],
  );

  const withPageCount = async (meta: FileMeta): Promise<FileMeta | null> => {
    if (!(await unlock(meta))) return null;
    if (meta.page_count == null) {
      const r = await api.checkPassword(meta.id, passwords.get(meta.id) ?? "");
      return { ...meta, page_count: r.page_count };
    }
    return meta;
  };

  const load = useCallback(async (id: string) => {
    setError(null);
    try {
      const meta = await api.file(id);
      if (meta.kind !== "pdf") throw new Error(`'${meta.name}' bir PDF değil.`);
      const ready = await withPageCount(meta);
      if (!ready) return navigate("araclar");
      setBase(ready);
      setNoText(false);
      if (!ready.encrypted) {
        api
          .info(ready.id)
          .then((i) => setNoText(i.has_text === false))
          .catch(() => undefined);
      }
      setSources({ [ready.id]: ready });
      setItems(pagesOf(ready));
      setPast([]);
      setFuture([]);
      setSelected(new Set());
    } catch (e) {
      setError(errorMessage(e));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (fileId) void load(fileId);
  }, [fileId, load]);

  // Kaydedilmemiş değişiklik varken sekmeyi kapatmaya karşı uyarı.
  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const commit = useCallback(
    (next: Item[]) => {
      setPast((p) => [...p.slice(-99), items]);
      setFuture([]);
      setItems(next);
    },
    [items],
  );

  const undo = () => {
    if (!past.length) return;
    setFuture((f) => [items, ...f]);
    setItems(past[past.length - 1]);
    setPast((p) => p.slice(0, -1));
  };
  const redo = () => {
    if (!future.length) return;
    setPast((p) => [...p, items]);
    setItems(future[0]);
    setFuture((f) => f.slice(1));
  };

  const targets = () => (selected.size ? items.filter((i) => selected.has(i.key)) : []);
  const rotateSel = (deg: number) =>
    commit(items.map((i) => (selected.has(i.key) ? { ...i, rotate: (i.rotate + deg + 360) % 360 } : i)));
  const deleteSel = () => {
    const next = items.filter((i) => !selected.has(i.key));
    if (!next.length) return setError("Bütün sayfalar silinemez; en az bir sayfa kalmalı.");
    commit(next);
    setSelected(new Set());
  };
  const insertAt = () => {
    const idx = items.reduce((m, it, i) => (selected.has(it.key) ? i : m), -1);
    return idx === -1 ? items.length : idx + 1;
  };
  const addBlank = () => {
    const next = [...items];
    next.splice(insertAt(), 0, { key: newKey(), page: 0, rotate: 0, blank: true });
    commit(next);
  };
  const reverse = () => {
    if (selected.size < 2) return commit([...items].reverse());
    const sel = targets().reverse();
    let k = 0;
    commit(items.map((i) => (selected.has(i.key) ? sel[k++] : i)));
  };
  const selectWhere = (pred: (index: number) => boolean) =>
    setSelected(new Set(items.filter((_, i) => pred(i)).map((i) => i.key)));

  const addPdfs = async (files: File[]) => {
    const metas = await upload(files);
    const added: Item[] = [];
    const newSources = { ...sources };
    for (const m of metas) {
      if (m.kind !== "pdf") {
        setError(`'${m.name}' bir PDF değil, eklenmedi.`);
        continue;
      }
      const ready = await withPageCount(m);
      if (!ready) continue;
      newSources[ready.id] = ready;
      added.push(...pagesOf(ready));
    }
    if (!added.length) return;
    setSources(newSources);
    const next = [...items];
    next.splice(insertAt(), 0, ...added);
    commit(next);
    setSelected(new Set(added.map((a) => a.key)));
  };

  const onItemClick = (e: React.MouseEvent, key: string) => {
    if (e.shiftKey && anchor) {
      const a = items.findIndex((i) => i.key === anchor);
      const b = items.findIndex((i) => i.key === key);
      const [lo, hi] = a < b ? [a, b] : [b, a];
      setSelected(new Set(items.slice(lo, hi + 1).map((i) => i.key)));
      return;
    }
    if (e.ctrlKey || e.metaKey) {
      const next = new Set(selected);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      setSelected(next);
    } else {
      setSelected(new Set([key]));
    }
    setAnchor(key);
  };

  // Klavye kısayolları (yazı alanında değilken).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (t.closest("input, textarea, select, dialog")) return;
      const mod = e.ctrlKey || e.metaKey;
      if (mod && e.key.toLowerCase() === "z" && !e.shiftKey) (e.preventDefault(), undo());
      else if (mod && (e.key.toLowerCase() === "y" || (e.shiftKey && e.key.toLowerCase() === "z")))
        (e.preventDefault(), redo());
      else if (mod && e.key.toLowerCase() === "a") (e.preventDefault(), selectWhere(() => true));
      else if (!selected.size) return;
      else if (e.key === "Delete" || e.key === "Backspace") (e.preventDefault(), deleteSel());
      else if (e.key.toLowerCase() === "r") (e.preventDefault(), rotateSel(e.shiftKey ? -90 : 90));
      else if (e.key === "Escape") setSelected(new Set());
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  // --- sürükle-bırak (seçili sayfalar blok hâlinde taşınır) ---
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );
  const keys = useMemo(() => items.map((i) => i.key), [items]);
  const onDragStart = ({ active }: DragStartEvent) => {
    const id = String(active.id);
    setDragging(id);
    if (!selected.has(id)) setSelected(new Set([id]));
  };
  const onDragEnd = ({ active, over }: DragEndEvent) => {
    setDragging(null);
    if (!over || active.id === over.id) return;
    const from = keys.indexOf(String(active.id));
    const to = keys.indexOf(String(over.id));
    if (selected.size < 2 || !selected.has(String(active.id))) return commit(arrayMove(items, from, to));
    if (selected.has(String(over.id))) return;
    const moving = items.filter((i) => selected.has(i.key));
    const rest = items.filter((i) => !selected.has(i.key));
    let idx = rest.findIndex((i) => i.key === over.id);
    if (to > from) idx += 1;
    rest.splice(idx, 0, ...moving);
    commit(rest);
  };

  const colorOf = useMemo(() => {
    const ids = Object.keys(sources);
    return (id?: string) => (id ? COLORS[ids.indexOf(id) % COLORS.length] : "transparent");
  }, [sources]);
  const multiSource = Object.keys(sources).length > 1;

  const save = async (target: "version" | "new") => {
    if (!base) return;
    const job = await saveJob.start({
      type: "compose",
      target,
      base_file: target === "version" ? base.id : undefined,
      items: items.map((i) =>
        i.blank ? { blank: true } : { file: i.file, page: i.page, rotate: i.rotate },
      ),
      passwords: passwords.forFiles(Object.keys(sources)),
    });
    if (!job) return;
  };

  // Kaydetme bitince: yeni sürümü / yeni dosyayı yükle.
  useEffect(() => {
    const j = saveJob.job;
    if (j?.status !== "bitti" || !j.outputs[0]) return;
    const out = j.outputs[0];
    if (base && out === base.id) {
      forgetPdf(base.id);
      void load(base.id);
    } else {
      navigate(`duzenle/${out}`);
    }
    saveJob.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [saveJob.job?.status]);

  const undoVersion = async () => {
    if (!base) return;
    try {
      await api.undo(base.id);
      forgetPdf(base.id);
      await load(base.id);
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  if (!fileId) {
    return (
      <>
        <PageHeader title="Sayfa Düzenle" />
        <DropZone
          multiple={false}
          accept={ACCEPT.pdf}
          disabled={uploading}
          title={uploading ? "Yükleniyor…" : "Düzenlenecek PDF'i bırak"}
          onFiles={async (files) => {
            const [m] = await upload(files);
            if (m) navigate(`duzenle/${m.id}`);
          }}
        />
      </>
    );
  }

  const label = (item: Item, index: number) => {
    if (item.blank) return `${index + 1} · boş`;
    const src = item.file ? sources[item.file] : undefined;
    return multiSource && src ? `${index + 1} · ${src.name.replace(/\.pdf$/i, "")} s.${item.page + 1}` : `${index + 1}`;
  };

  return (
    <>
      <PageHeader title={base?.name ?? "Sayfa Düzenle"}>
        {base && (
          <span className="muted small">
            {items.length} sayfa · sürüm {base.version}
            {base.version > 1 && (
              <button type="button" className="link-button" onClick={undoVersion} disabled={dirty}>
                Önceki sürüme dön
              </button>
            )}
            <button type="button" className="link-button" onClick={() => navigate(`editor/${base.id}`)} disabled={dirty}>
              İçerik ekle
            </button>
          </span>
        )}
      </PageHeader>

      <div className="toolbar" role="toolbar" aria-label="Sayfa işlemleri">
        <div className="tool-cluster">
          <button type="button" onClick={() => rotateSel(-90)} disabled={!selected.size} title="Sola döndür (Shift+R)">
            ⟲ Sola
          </button>
          <button type="button" onClick={() => rotateSel(90)} disabled={!selected.size} title="Sağa döndür (R)">
            ⟳ Sağa
          </button>
          <button type="button" onClick={deleteSel} disabled={!selected.size} title="Sil (Delete)">
            Sil
          </button>
          <button type="button" onClick={addBlank} title="Seçimden sonra (yoksa sona) boş sayfa">
            Boş sayfa
          </button>
          <button type="button" onClick={reverse} title="Seçili sayfaların (yoksa tümünün) sırasını ters çevir">
            Ters çevir
          </button>
          <button type="button" onClick={() => addInput.current?.click()} disabled={uploading}>
            {uploading ? "Yükleniyor…" : "+ PDF ekle"}
          </button>
          <input
            ref={addInput}
            type="file"
            accept={ACCEPT.pdf}
            multiple
            hidden
            onChange={(e) => {
              void addPdfs(Array.from(e.target.files ?? []));
              e.target.value = "";
            }}
          />
        </div>
        <div className="tool-cluster">
          <select
            aria-label="Seçim"
            value=""
            onChange={(e) => {
              const v = e.target.value;
              if (v === "all") selectWhere(() => true);
              if (v === "none") setSelected(new Set());
              if (v === "odd") selectWhere((i) => i % 2 === 0);
              if (v === "even") selectWhere((i) => i % 2 === 1);
              e.target.value = "";
            }}
          >
            <option value="">Seç…</option>
            <option value="all">Tümü (Ctrl+A)</option>
            <option value="none">Hiçbiri (Esc)</option>
            <option value="odd">Tek sayfalar</option>
            <option value="even">Çift sayfalar</option>
          </select>
          <button type="button" onClick={undo} disabled={!past.length} title="Geri al (Ctrl+Z)">
            Geri
          </button>
          <button type="button" onClick={redo} disabled={!future.length} title="İleri al (Ctrl+Y)">
            İleri
          </button>
        </div>
        <div className="tool-cluster end">
          {base && !dirty && (
            <a className="button" href={api.downloadUrl(base.id)}>
              İndir
            </a>
          )}
          <button type="button" onClick={() => save("new")} disabled={!dirty || saveJob.running}>
            Yeni dosya olarak kaydet
          </button>
          <button type="button" className="primary" onClick={() => save("version")} disabled={!dirty || saveJob.running}>
            {saveJob.running ? "Kaydediliyor…" : "Kaydet"}
          </button>
        </div>
      </div>

      {error && (
        <div className="banner error" role="alert">
          {error}
          <button type="button" className="link-button" onClick={() => setError(null)}>
            Kapat
          </button>
        </div>
      )}
      {noText && base && (
        <div className="banner warn">
          Bu PDF'te seçilebilir metin yok; taranmış görünüyor.{" "}
          <button type="button" className="link-button" onClick={() => navigate("ocr", { dosya: base.id })}>
            OCR ile aranabilir yap
          </button>
        </div>
      )}
      <JobPanel job={saveJob.job?.status === "hata" ? saveJob.job : null} error={saveJob.error} />
      {selected.size > 0 && (
        <p className="muted small selection-line">
          {selected.size} sayfa seçili · sürükleyerek taşı, R ile döndür, Delete ile sil
        </p>
      )}

      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragStart={onDragStart} onDragEnd={onDragEnd}>
        <SortableContext items={keys} strategy={rectSortingStrategy}>
          <ul
            className="page-grid"
            onClick={(e) => e.target === e.currentTarget && setSelected(new Set())}
            onDragOver={(e) => e.dataTransfer.types.includes("Files") && e.preventDefault()}
            onDrop={(e) => {
              if (!e.dataTransfer.files.length) return;
              e.preventDefault();
              void addPdfs(Array.from(e.dataTransfer.files));
            }}
          >
            {items.map((item, index) => {
              const src = item.file ? sources[item.file] : undefined;
              return (
                <PageTile
                  key={item.key}
                  item={item}
                  version={src?.version ?? 1}
                  selected={selected.has(item.key)}
                  hidden={dragging !== null && dragging !== item.key && selected.size > 1 && selected.has(item.key)}
                  color={multiSource ? colorOf(item.file) : "transparent"}
                  label={label(item, index)}
                  onClick={(e) => onItemClick(e, item.key)}
                  onOpen={() => setPreview(item)}
                />
              );
            })}
          </ul>
        </SortableContext>
        <DragOverlay>
          {dragging && selected.size > 1 ? <div className="drag-badge">{selected.size} sayfa</div> : null}
        </DragOverlay>
      </DndContext>
      <p className="muted small hint-line">
        Başka PDF'leri bu alana sürükleyerek sayfalarını ekleyebilirsin. Çift tıklayınca sayfa büyür.
      </p>

      {preview && !preview.blank && preview.file && (
        <Modal title={label(preview, items.indexOf(preview))} onClose={() => setPreview(null)} wide>
          <div className="preview-page">
            <Thumb fileId={preview.file} version={sources[preview.file]?.version ?? 1} page={preview.page} rotate={preview.rotate} width={720} />
          </div>
        </Modal>
      )}
      {locked && (
        <PasswordDialog
          file={locked}
          onDone={(ok) => {
            setLocked(null);
            pendingUnlock.current?.(ok);
            pendingUnlock.current = null;
          }}
        />
      )}
    </>
  );
}

interface TileProps {
  item: Item;
  version: number;
  selected: boolean;
  hidden: boolean;
  color: string;
  label: string;
  onClick: (e: React.MouseEvent) => void;
  onOpen: () => void;
}

function PageTile({ item, version, selected, hidden, color, label, onClick, onOpen }: TileProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: item.key });
  return (
    <li
      ref={setNodeRef}
      className={`page-tile${selected ? " selected" : ""}${isDragging ? " dragging" : ""}${hidden ? " ghost" : ""}`}
      style={{ transform: CSS.Transform.toString(transform), transition, borderColor: selected ? undefined : color }}
      onClick={onClick}
      onDoubleClick={onOpen}
      aria-selected={selected}
      aria-label={`Sayfa ${label}`}
      {...attributes}
      {...listeners}
    >
      {item.blank || !item.file ? (
        <div className="thumb-box">
          <span className="blank-page" style={{ transform: `rotate(${item.rotate}deg)` }}>
            Boş sayfa
          </span>
        </div>
      ) : (
        <Thumb fileId={item.file} version={version} page={item.page} rotate={item.rotate} />
      )}
      <span className="page-label">{label}</span>
    </li>
  );
}
