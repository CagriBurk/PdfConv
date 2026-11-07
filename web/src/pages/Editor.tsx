import type { PDFDocumentProxy } from "pdfjs-dist/legacy/build/pdf.mjs";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, errorMessage, type FileMeta, type FontInfo } from "../api";
import FilePicker from "../components/FilePicker";
import JobPanel from "../components/JobPanel";
import PageHeader from "../components/PageHeader";
import PasswordDialog from "../components/PasswordDialog";
import Thumb from "../components/Thumb";
import {
  canRotate,
  isBox,
  KIND_LABELS,
  measureText,
  newId,
  toOps,
  TOOL_LABELS,
  type Align,
  type EditorObj,
  type TextObj,
  type Tool,
} from "../editor/model";
import { loadBundledFonts } from "../fonts";
import PageCanvas from "../editor/PageCanvas";
import SignatureDialog from "../editor/SignatureDialog";
import { useJob, useKeepAlive, useUpload } from "../hooks";
import { passwords } from "../passwords";
import { forgetPdf, openPdf } from "../pdf";
import { navigate, useLeaveGuard } from "../router";
import { ACCEPT } from "../tools";

const TOOL_GROUPS: Tool[][] = [
  ["select"],
  ["text", "image", "signature"],
  ["highlight", "rect", "ellipse", "line", "arrow"],
  ["redact", "whiteout"],
];
// Bu araçlar art arda kullanılır; nesne çizildikten sonra seçili kalır.
const STICKY: Tool[] = ["highlight", "redact", "whiteout"];
const ZOOMS = [0.5, 0.75, 1, 1.25, 1.5, 2, 3];

function loadImageSize(url: string): Promise<{ w: number; h: number }> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve({ w: img.naturalWidth, h: img.naturalHeight });
    img.onerror = () => reject(new Error("Resim açılamadı."));
    img.src = url;
  });
}

export default function Editor({ fileId }: { fileId?: string }) {
  const [meta, setMeta] = useState<FileMeta | null>(null);
  const [doc, setDoc] = useState<PDFDocumentProxy | null>(null);
  const [locked, setLocked] = useState<FileMeta | null>(null);
  const [pageIndex, setPageIndex] = useState(0);
  const [pageSize, setPageSize] = useState<{ w: number; h: number }>({ w: 595, h: 842 });
  const [objects, setObjects] = useState<EditorObj[]>([]);
  const [past, setPast] = useState<EditorObj[][]>([]);
  const [future, setFuture] = useState<EditorObj[][]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [tool, setTool] = useState<Tool>("select");
  const [zoom, setZoom] = useState(1);
  const [fit, setFit] = useState(1);
  const [fonts, setFonts] = useState<FontInfo[]>([]);
  const [signing, setSigning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mainRef = useRef<HTMLDivElement>(null);
  const imageInput = useRef<HTMLInputElement>(null);
  const textRef = useRef<HTMLTextAreaElement>(null);
  const { upload, uploading } = useUpload({ toastErrors: true });
  const job = useJob();
  const dirty = objects.length > 0;
  const pageCount = meta?.page_count ?? doc?.numPages ?? 0;
  const selected = objects.find((o) => o.id === selectedId) ?? null;

  const open = useCallback(async (m: FileMeta) => {
    try {
      setDoc(await openPdf(m, passwords.get(m.id)));
      setMeta(m);
    } catch (e) {
      setError(errorMessage(e));
    }
  }, []);

  const load = useCallback(
    async (id: string) => {
      setError(null);
      try {
        const m = await api.file(id);
        if (m.kind !== "pdf") throw new Error(`'${m.name}' bir PDF değil.`);
        if (m.encrypted && !passwords.get(m.id)) return setLocked(m);
        await open(m);
      } catch (e) {
        setError(errorMessage(e));
      }
    },
    [open],
  );

  useEffect(() => {
    if (fileId) void load(fileId);
  }, [fileId, load]);

  useEffect(() => {
    // Gömülü fontlar yüklenmeden çizilen önizleme yedek fonta düşerdi.
    Promise.all([api.fonts(), loadBundledFonts()])
      .then(([f]) => setFonts(f))
      .catch(() => undefined);
  }, []);

  // Sayfa genişliğine sığdır; pencere boyu değişince yeniden hesapla.
  useEffect(() => {
    const el = mainRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setFit(Math.min(1.6, Math.max(0.3, (el.clientWidth - 32) / pageSize.w))));
    ro.observe(el);
    return () => ro.disconnect();
  }, [pageSize.w, doc]);

  // Uygulanmamış nesneler: başka ekrana geçerken ve sekmeyi kapatırken sorulur.
  useLeaveGuard(dirty);
  useKeepAlive([meta?.id]); // açıkken otomatik temizlik silmesin

  const commit = useCallback(
    (next: EditorObj[]) => {
      setPast((p) => [...p.slice(-99), objects]);
      setFuture([]);
      setObjects(next);
    },
    [objects],
  );
  const update = (o: EditorObj) => commit(objects.map((x) => (x.id === o.id ? o : x)));
  const add = (o: EditorObj) => {
    commit([...objects, o]);
    setSelectedId(o.id);
    if (!STICKY.includes(tool)) setTool("select");
    if (o.kind === "text") setTimeout(() => textRef.current?.select(), 0);
  };
  const remove = (id: string) => {
    commit(objects.filter((o) => o.id !== id));
    setSelectedId(null);
  };
  const undo = () => {
    if (!past.length) return;
    setFuture((f) => [objects, ...f]);
    setObjects(past[past.length - 1]);
    setPast((p) => p.slice(0, -1));
  };
  const redo = () => {
    if (!future.length) return;
    setPast((p) => [...p, objects]);
    setObjects(future[0]);
    setFuture((f) => f.slice(1));
  };

  const placeImage = async (asset: string, signature: boolean) => {
    try {
      const { w, h } = await loadImageSize(api.rawUrl(asset));
      const width = Math.min(signature ? 160 : 240, pageSize.w * 0.6);
      const height = (width * h) / w;
      add({
        id: newId(),
        page: pageIndex,
        kind: "image",
        asset,
        signature,
        opacity: 1,
        rotation: 0,
        w: width,
        h: height,
        x: (pageSize.w - width) / 2,
        y: signature ? pageSize.h * 0.75 - height / 2 : (pageSize.h - height) / 2,
      });
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  const chooseTool = (t: Tool) => {
    setSelectedId(null);
    if (t === "image") imageInput.current?.click();
    else if (t === "signature") setSigning(true);
    else setTool(t);
  };

  // Klavye: Delete sil, Esc bırak, Ctrl+Z / Ctrl+Y, oklar 1 nokta (Shift: 10) kaydırır.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement;
      if (el.closest("input, textarea, select, dialog")) return;
      const mod = e.ctrlKey || e.metaKey;
      if (mod && e.key.toLowerCase() === "z") return e.preventDefault(), e.shiftKey ? redo() : undo();
      if (mod && e.key.toLowerCase() === "y") return e.preventDefault(), redo();
      if (e.key === "Escape") return setSelectedId(null), setTool("select");
      if (!selected) return;
      if (e.key === "Delete" || e.key === "Backspace") return e.preventDefault(), remove(selected.id);
      const step = e.shiftKey ? 10 : 1;
      const d = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] }[e.key];
      if (!d) return;
      e.preventDefault();
      if (isBox(selected)) update({ ...selected, x: selected.x + d[0], y: selected.y + d[1] });
      else {
        const [a, b, c, f] = selected.points;
        update({ ...selected, points: [a + d[0], b + d[1], c + d[0], f + d[1]] });
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const apply = (target: "version" | "new") => {
    if (!meta || !objects.length) return;
    void job.start({
      type: "apply",
      file: meta.id,
      target,
      ops: toOps(objects),
      passwords: passwords.forFiles([meta.id]),
    });
  };

  // Uygulama bitince yeni sürümü aç (ya da yeni dosyaya geç).
  useEffect(() => {
    const j = job.job;
    if (j?.status !== "bitti" || !j.outputs[0] || !meta) return;
    const out = j.outputs[0];
    setObjects([]);
    setPast([]);
    setFuture([]);
    setSelectedId(null);
    if (out === meta.id) {
      forgetPdf(meta.id);
      void load(meta.id);
    } else {
      navigate(`editor/${out}`, undefined, { force: true }); // değişiklikler yeni dosyada
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job.job?.status]);

  const undoVersion = async () => {
    if (!meta) return;
    try {
      await api.undo(meta.id);
      forgetPdf(meta.id);
      job.reset();
      await load(meta.id);
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  if (!fileId) {
    return (
      <>
        <PageHeader title="İçerik Ekle" />
        <FilePicker
          accept={ACCEPT.pdf}
          kind="pdf"
          multiple={false}
          title="Düzenlenecek PDF'i bırak"
          onAdd={([f]) => navigate(`editor/${f.id}`)}
        />
      </>
    );
  }

  const counts = objects.reduce<Record<number, number>>((acc, o) => ((acc[o.page] = (acc[o.page] ?? 0) + 1), acc), {});
  const scale = fit * zoom;
  const showJob = job.job && (job.job.status !== "bitti" || job.job.warnings.length > 0);

  return (
    <>
      <PageHeader title="İçerik Ekle">
        {meta && (
          <span className="muted small">
            {meta.name} · {meta.version}. sürüm
            {meta.version > 1 && (
              <button type="button" className="link-button" onClick={() => void undoVersion()} disabled={dirty}>
                Önceki sürüme dön
              </button>
            )}
            <button type="button" className="link-button" onClick={() => navigate(`duzenle/${meta.id}`)} disabled={dirty}>
              Sayfa düzenleyicide aç
            </button>
          </span>
        )}
      </PageHeader>

      <div className="toolbar" role="toolbar" aria-label="Editör araçları">
        {TOOL_GROUPS.map((group, i) => (
          <div key={i} className="tool-cluster">
            {group.map((t) => (
              <button
                key={t}
                type="button"
                className={`tool-button${tool === t ? " on" : ""}${t === "redact" ? " danger" : ""}`}
                aria-pressed={tool === t}
                onClick={() => chooseTool(t)}
                disabled={!doc || (t === "image" && uploading)}
              >
                {TOOL_LABELS[t]}
              </button>
            ))}
          </div>
        ))}
        <div className="tool-cluster">
          <button type="button" onClick={undo} disabled={!past.length} title="Geri al (Ctrl+Z)">
            Geri
          </button>
          <button type="button" onClick={redo} disabled={!future.length} title="İleri (Ctrl+Y)">
            İleri
          </button>
          <select
            className="input narrow"
            value={zoom}
            onChange={(e) => setZoom(Number(e.target.value))}
            aria-label="Yakınlaştırma"
          >
            {ZOOMS.map((z) => (
              <option key={z} value={z}>
                %{Math.round(z * 100)}
              </option>
            ))}
          </select>
        </div>
        <div className="tool-cluster end">
          {meta && (
            <a className="button" href={api.downloadUrl(meta.id)}>
              İndir
            </a>
          )}
          <button type="button" onClick={() => apply("new")} disabled={!dirty || job.running}>
            Yeni dosya olarak
          </button>
          <button type="button" className="primary" onClick={() => apply("version")} disabled={!dirty || job.running}>
            {job.running ? "Uygulanıyor…" : `Uygula${dirty ? ` (${objects.length})` : ""}`}
          </button>
        </div>
      </div>

      {tool === "redact" && (
        <p className="banner warn">
          <strong>Karartma</strong>: işaretlediğin alandaki yazı, resim pikselleri ve çizimler "Uygula" ile dosyadan
          kalıcı olarak silinir. Şekillerle siyah kutu çizmek karartma değildir; alttaki yazı kopyalanabilir kalır.
        </p>
      )}
      {tool === "whiteout" && (
        <p className="banner warn">
          <strong>Beyazla kapat</strong>: alandaki yazı silinir ve üstü boyanır (resim ve çizgiler yalnızca örtülür).
          Düzeltilmiş metni Yazı aracıyla üstüne ekle. Bu, mevcut yazıyı yerinde düzenleme değildir.
        </p>
      )}
      {error && (
        <div className="banner error" role="alert">
          {error}{" "}
          <button type="button" className="link-button" onClick={() => setError(null)}>
            Kapat
          </button>
        </div>
      )}
      {showJob && <JobPanel job={job.job} error={job.error} />}
      {job.error && !job.job && <JobPanel job={null} error={job.error} />}

      <div className="editor-layout">
        <aside className="editor-pages" aria-label="Sayfalar">
          {meta &&
            Array.from({ length: pageCount }, (_, i) => (
              <button
                key={`${meta.version}-${i}`}
                type="button"
                className={`editor-thumb${i === pageIndex ? " on" : ""}`}
                onClick={() => setPageIndex(i)}
                aria-current={i === pageIndex}
              >
                <Thumb file={meta} page={i} rotate={0} width={110} />
                <span className="page-label">
                  {i + 1}
                  {counts[i] ? <span className="badge">{counts[i]}</span> : null}
                </span>
              </button>
            ))}
        </aside>

        <section className="editor-main" ref={mainRef}>
          {doc && (
            <>
              <div className="page-nav">
                <button type="button" onClick={() => setPageIndex((p) => Math.max(0, p - 1))} disabled={pageIndex === 0}>
                  ←
                </button>
                <span>
                  {pageIndex + 1} / {pageCount}
                </span>
                <button
                  type="button"
                  onClick={() => setPageIndex((p) => Math.min(pageCount - 1, p + 1))}
                  disabled={pageIndex >= pageCount - 1}
                >
                  →
                </button>
              </div>
              <PageCanvas
                doc={doc}
                pageIndex={pageIndex}
                scale={scale}
                objects={objects}
                selectedId={selectedId}
                tool={tool}
                onSelect={setSelectedId}
                onChange={update}
                onCreate={add}
                onEditText={() => textRef.current?.focus()}
                onPageSize={(w, h) => setPageSize((s) => (s.w === w && s.h === h ? s : { w, h }))}
              />
            </>
          )}
        </section>

        <aside className="editor-props options">
          {selected ? (
            <Properties
              obj={selected}
              fonts={fonts}
              textRef={textRef}
              onChange={update}
              onRemove={() => remove(selected.id)}
            />
          ) : (
            <div className="muted small">
              <p>
                Bir araç seç ve sayfaya tıkla ya da sürükleyerek alan çiz. Nesneyi seçip taşı, köşelerinden
                boyutlandır; özellikleri burada değişir.
              </p>
              <p>Delete: sil · Esc: bırak · oklar: kaydır (Shift ile 10) · Ctrl+Z / Ctrl+Y</p>
              {dirty && <p>{objects.length} değişiklik henüz uygulanmadı.</p>}
            </div>
          )}
        </aside>
      </div>

      <input
        ref={imageInput}
        type="file"
        accept={ACCEPT.images}
        hidden
        onChange={async (e) => {
          const files = Array.from(e.target.files ?? []);
          e.target.value = "";
          const [m] = await upload(files);
          if (m?.kind === "image") await placeImage(m.id, false);
          else if (m) setError(`'${m.name}' bir resim değil.`);
        }}
      />
      {signing && (
        <SignatureDialog
          onClose={() => setSigning(false)}
          onPick={(sig) => {
            setSigning(false);
            void placeImage(sig.id, true);
          }}
        />
      )}
      {locked && (
        <PasswordDialog
          file={locked}
          onDone={(ok) => {
            setLocked(null);
            if (ok) void open(locked);
            else navigate("araclar");
          }}
        />
      )}
    </>
  );
}

interface PropsPanel {
  obj: EditorObj;
  fonts: FontInfo[];
  textRef: React.RefObject<HTMLTextAreaElement | null>;
  onChange: (o: EditorObj) => void;
  onRemove: () => void;
}

function Properties({ obj, fonts, textRef, onChange, onRemove }: PropsPanel) {
  const setText = (patch: Partial<TextObj>) => {
    const next = { ...(obj as TextObj), ...patch };
    onChange({ ...next, h: measureText(next) });
  };
  const opacity = "opacity" in obj && (
    <label className="field">
      Opaklık %{Math.round(obj.opacity * 100)}
      <input
        type="range"
        min={0.05}
        max={1}
        step={0.05}
        value={obj.opacity}
        onChange={(e) => onChange({ ...obj, opacity: Number(e.target.value) })}
      />
    </label>
  );
  const fontInfo = obj.kind === "text" ? fonts.find((f) => f.key === obj.font) : undefined;

  return (
    <div className="props">
      <h3>{obj.kind === "image" && obj.signature ? "İmza" : KIND_LABELS[obj.kind]}</h3>
      {obj.kind === "text" && (
        <>
          <label className="field">
            Metin
            <textarea
              ref={textRef}
              className="input"
              rows={4}
              value={obj.text}
              onChange={(e) => setText({ text: e.target.value })}
            />
          </label>
          <label className="field">
            Font
            <select className="input" value={obj.font} onChange={(e) => setText({ font: e.target.value })}>
              {(fonts.length ? fonts : [{ key: obj.font, name: obj.font, bold: true }]).map((f) => (
                <option key={f.key} value={f.key}>
                  {f.name}
                </option>
              ))}
            </select>
          </label>
          <div className="field-row">
            <label className="field">
              Boyut
              <input
                className="input narrow"
                type="number"
                min={4}
                max={400}
                value={obj.size}
                onChange={(e) => Number(e.target.value) >= 4 && setText({ size: Number(e.target.value) })}
              />
            </label>
            <label className="field">
              Renk
              <input type="color" value={obj.color} onChange={(e) => setText({ color: e.target.value })} />
            </label>
            <label className="check">
              <input
                type="checkbox"
                checked={obj.bold}
                disabled={fontInfo ? !fontInfo.bold : false}
                onChange={(e) => setText({ bold: e.target.checked })}
              />
              Kalın
            </label>
          </div>
          <div className="segmented" role="group" aria-label="Hizalama">
            {(
              [
                ["left", "Sol"],
                ["center", "Orta"],
                ["right", "Sağ"],
                ["justify", "İki yana"],
              ] as [Align, string][]
            ).map(([a, label]) => (
              <button key={a} type="button" className={obj.align === a ? "on" : undefined} onClick={() => setText({ align: a })}>
                {label}
              </button>
            ))}
          </div>
          {opacity}
        </>
      )}
      {obj.kind === "image" && opacity}
      {(obj.kind === "highlight" || obj.kind === "redact" || obj.kind === "whiteout") && (
        <label className="field">
          Renk
          <input type="color" value={obj.color} onChange={(e) => onChange({ ...obj, color: e.target.value })} />
        </label>
      )}
      {obj.kind === "highlight" && <p className="muted small">Altındaki yazı satırları vurgulanır; yazı yoksa kutunun kendisi.</p>}
      {obj.kind === "redact" && (
        <p className="muted small">Uygulandığında bu alandaki içerik dosyadan kalıcı olarak silinir.</p>
      )}
      {(obj.kind === "rect" || obj.kind === "ellipse") && (
        <>
          <div className="field-row">
            <label className="field">
              Çizgi
              <input
                type="color"
                value={obj.stroke ?? "#d00000"}
                disabled={!obj.stroke}
                onChange={(e) => onChange({ ...obj, stroke: e.target.value })}
              />
            </label>
            <label className="check">
              <input
                type="checkbox"
                checked={!obj.stroke}
                disabled={!obj.fill}
                onChange={(e) => onChange({ ...obj, stroke: e.target.checked ? null : "#d00000" })}
              />
              Yok
            </label>
          </div>
          <div className="field-row">
            <label className="field">
              Dolgu
              <input
                type="color"
                value={obj.fill ?? "#ffffff"}
                disabled={!obj.fill}
                onChange={(e) => onChange({ ...obj, fill: e.target.value })}
              />
            </label>
            <label className="check">
              <input
                type="checkbox"
                checked={!obj.fill}
                disabled={!obj.stroke}
                onChange={(e) => onChange({ ...obj, fill: e.target.checked ? null : "#ffe066" })}
              />
              Yok
            </label>
          </div>
        </>
      )}
      {(obj.kind === "rect" || obj.kind === "ellipse" || obj.kind === "line" || obj.kind === "arrow") && (
        <>
          {(obj.kind === "line" || obj.kind === "arrow") && (
            <label className="field">
              Renk
              <input type="color" value={obj.stroke} onChange={(e) => onChange({ ...obj, stroke: e.target.value })} />
            </label>
          )}
          <label className="field">
            Kalınlık
            <input
              className="input narrow"
              type="number"
              min={0.5}
              max={50}
              step={0.5}
              value={obj.width}
              onChange={(e) => Number(e.target.value) > 0 && onChange({ ...obj, width: Number(e.target.value) })}
            />
          </label>
          {opacity}
        </>
      )}
      {canRotate(obj) && isBox(obj) && (
        <label className="field">
          Açı (saat yönünde)
          <input
            className="input narrow"
            type="number"
            step={1}
            value={obj.rotation}
            onChange={(e) => onChange({ ...obj, rotation: Number(e.target.value) || 0 })}
          />
        </label>
      )}
      <button type="button" className="danger block" onClick={onRemove}>
        Sil
      </button>
    </div>
  );
}
