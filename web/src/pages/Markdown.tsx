import { useEffect, useRef, useState } from "react";
import { api, errorMessage, type EnginesResponse, type FileMeta, type MdPreview } from "../api";
import DropZone from "../components/DropZone";
import JobPanel from "../components/JobPanel";
import PageHeader from "../components/PageHeader";
import PreviewFrame from "../components/PreviewFrame";
import { useJob, useKeepAlive, useUpload } from "../hooks";
import { drafts, draftKey, formatDraftTime, type Draft } from "../drafts";
import { createSequencer } from "../mdpreview";
import { idsFrom, LEAVE_MESSAGE, useLeaveGuard, type Route } from "../router";
import { PAPERS } from "../tools";

interface Options {
  theme: string;
  paper: string;
  landscape: boolean;
  toc: boolean;
  cover: boolean;
  page_numbers: boolean;
  margin_mm: number;
  font_size_pt: number | null;
}

// "otomatik" = notun ön bilgisindeki (pdf:) değer, o da yoksa varsayılan.
type Override<T> = { [K in keyof T]: T[K] | null };
const AUTO: Override<Options> = {
  theme: null, paper: null, landscape: null, toc: null, cover: null, page_numbers: null,
  margin_mm: null, font_size_pt: null,
};

const SAMPLE = `---
title: Yeni not
---

# Başlık

Formül: $E = mc^2$ ve blok:

$$
\\int_0^1 x^2\\,dx = \\frac{1}{3}
$$

> [!tip] İpucu
> Obsidian callout'ları desteklenir.
`;

const triState = (v: boolean | null) => (v === null ? "" : v ? "1" : "0");
const fromTri = (v: string) => (v === "" ? null : v === "1");

export default function Markdown({ route, engines }: { route: Route; engines: EnginesResponse | null }) {
  const [mdFile, setMdFile] = useState<FileMeta | null>(null);
  const [attachments, setAttachments] = useState<FileMeta[]>([]);
  const [text, setText] = useState<string | null>(null);
  // Kaydedilmiş sayılan metin: dosyadan okunan, son PDF'i üretilen ya da indirilen hâli.
  const [saved, setSaved] = useState<string | null>(null);
  const [encodingNote, setEncodingNote] = useState<string | null>(null);
  const [draftOffer, setDraftOffer] = useState<Draft | null>(null);
  const [opts, setOpts] = useState<Override<Options>>(AUTO);
  const [preview, setPreview] = useState<MdPreview | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [showEditor, setShowEditor] = useState(true);
  const { upload, uploading, error: uploadError, setError } = useUpload();
  const job = useJob();
  const timer = useRef<number>(undefined);
  const previewSeq = useRef(createSequencer());
  const builtText = useRef<string | null>(null);
  const browserMissing = engines?.engines.find((e) => e.key === "browser")?.ok === false;
  const dirty = text !== null && saved !== null && text !== saved;
  const key = draftKey(mdFile?.id);

  // Kaydedilmemiş not: başka ekrana geçerken / sekmeyi kapatırken sorulur.
  useLeaveGuard(dirty);
  useKeepAlive([mdFile?.id, ...attachments.map((a) => a.id)]);

  /** Not açıldı: metin ve (varsa) bu not için kalmış taslak. */
  const opened = (meta: FileMeta | null, body: string, note: string | null) => {
    setMdFile(meta);
    setText(body);
    setSaved(body);
    setEncodingNote(note);
    const d = drafts.get(draftKey(meta?.id));
    setDraftOffer(d && d.text !== body ? d : null);
  };

  // Yeni not ekranında: önceki oturumdan kalmış adsız taslak var mı?
  useEffect(() => {
    if (!idsFrom(route)[0]) setDraftOffer(drafts.get(draftKey(null)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Taslak: her değişiklikte (biraz bekleyerek) yerel depoya; kaydedilmiş hâle dönünce silinir.
  useEffect(() => {
    if (text === null) return;
    if (!dirty) {
      if (!draftOffer) drafts.remove(key);
      return;
    }
    const t = window.setTimeout(
      () => drafts.set(key, { text, at: Date.now(), name: mdFile?.name ?? `${preview?.title ?? "belge"}.md` }),
      600,
    );
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text, dirty, key]);

  // PDF üretildi: o anki metin kaydedilmiş sayılır.
  useEffect(() => {
    if (job.job?.status === "bitti" && builtText.current !== null) setSaved(builtText.current);
  }, [job.job?.status]);

  // URL'den gelen dosyalar (ana sayfadan yönlendirme ya da sayfa yenileme).
  const mainId = idsFrom(route)[0];
  const extraIds = idsFrom(route, "ek").join(",");
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        if (mainId) {
          const meta = await api.file(mainId);
          const body = await api.text(mainId);
          if (!alive) return;
          opened(meta, body.text, body.note);
        }
        if (extraIds) {
          const ek = await Promise.all(extraIds.split(",").map((id) => api.file(id)));
          if (alive) setAttachments(ek);
        }
      } catch (e) {
        setError(errorMessage(e));
      }
    })();
    return () => {
      alive = false;
    };
  }, [mainId, extraIds, setError]);

  const options = Object.fromEntries(Object.entries(opts).filter(([, v]) => v !== null));
  const optionsKey = JSON.stringify(options);
  const attachmentIds = attachments.map((a) => a.id);
  const attachmentKey = attachmentIds.join(",");

  // Yazdıkça önizleme (yarım saniye bekleyerek). Yanıtlar sırasız gelebilir (büyük not, yavaş
  // istek): yalnızca en son isteğin yanıtı gösterilir.
  useEffect(() => {
    if (text === null) return;
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(async () => {
      const n = previewSeq.current.next();
      try {
        const result = await api.mdPreview(text, attachmentIds, options);
        if (!previewSeq.current.isLatest(n)) return;
        setPreview(result);
        setPreviewError(null);
      } catch (e) {
        if (previewSeq.current.isLatest(n)) setPreviewError(errorMessage(e));
      }
    }, 450);
    return () => window.clearTimeout(timer.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text, optionsKey, attachmentKey]);

  const onFiles = async (files: File[]) => {
    const metas = await upload(files);
    const md = metas.find((m) => m.kind === "markdown" || m.kind === "text");
    const rest = metas.filter((m) => m !== md);
    if (md) {
      if (dirty && !window.confirm(LEAVE_MESSAGE)) return;
      try {
        const body = await api.text(md.id);
        opened(md, body.text, body.note);
      } catch (e) {
        setError(errorMessage(e));
        return;
      }
      job.reset();
    }
    if (rest.length) setAttachments((a) => [...a, ...rest.filter((r) => !a.some((x) => x.name === r.name))]);
  };

  const set = <K extends keyof Options>(key: K, value: Options[K] | null) => setOpts((o) => ({ ...o, [key]: value }));
  const noteName = mdFile?.name ?? `${preview?.title ?? "belge"}.md`;

  /** Düzenlenmiş notu .md olarak indirir (UTF-8); indirilen hâl kaydedilmiş sayılır. */
  const downloadNote = () => {
    if (text === null) return;
    const blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${noteName.replace(/\.(md|markdown|txt)$/i, "")}.md`;
    a.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 10_000);
    setSaved(text);
  };
  const effective = preview?.options;

  return (
    <>
      <PageHeader title="Markdown → PDF">
        {mdFile && <span className="muted small">{mdFile.name}</span>}
      </PageHeader>
      {browserMissing && (
        <div className="banner error">Edge/Chrome bulunamadı; PDF oluşturulamaz. Ayarlar sayfasına bak.</div>
      )}
      {draftOffer && (
        <div className="banner warn" role="status">
          {formatDraftTime(draftOffer.at)} tarihli kaydedilmemiş bir taslak var ({draftOffer.name}).{" "}
          <button
            type="button"
            className="link-button"
            onClick={() => {
              // Yeni not ekranından açılırsa "kaydedilmiş" hâl örnek nottur: taslak kirli sayılır.
              if (text === null) setSaved(SAMPLE);
              setText(draftOffer.text);
              setDraftOffer(null);
            }}
          >
            Taslağı aç
          </button>{" "}
          <button
            type="button"
            className="link-button"
            onClick={() => {
              drafts.remove(key);
              setDraftOffer(null);
            }}
          >
            Sil
          </button>
        </div>
      )}
      {encodingNote && <div className="banner warn">{encodingNote} İndirirken UTF-8 kullanılır.</div>}

      {text === null ? (
        <>
          <DropZone
            onFiles={onFiles}
            accept=".md,.markdown,.txt,.png,.jpg,.jpeg,.gif,.webp,.svg"
            disabled={uploading}
            title={uploading ? "Yükleniyor…" : "Markdown notunu (ve kullandığı resimleri) bırak"}
            hint="Notta ![[resim.png]] varsa resmi de birlikte bırak; ya da Ayarlar'da Obsidian kasası yolunu tanımla."
          />
          <p className="center">
            <button type="button" className="link-button" onClick={() => opened(null, SAMPLE, null)}>
              ya da boş bir notla başla
            </button>
          </p>
          {uploadError && <p className="error-text">{uploadError}</p>}
        </>
      ) : (
        <div className="md-layout">
          <section className="md-left">
            <div className="md-options">
              <label className="field">
                Tema
                <select value={opts.theme ?? ""} onChange={(e) => set("theme", e.target.value || null)}>
                  <option value="">Otomatik ({effective?.theme ?? "ders"})</option>
                  <option value="ders">Ders notu</option>
                  <option value="rapor">Rapor</option>
                  <option value="sade">Sade</option>
                </select>
              </label>
              <label className="field">
                Kağıt
                <select value={opts.paper ?? ""} onChange={(e) => set("paper", e.target.value || null)}>
                  <option value="">Otomatik ({effective?.paper ?? "A4"})</option>
                  {PAPERS.map((p) => (
                    <option key={p} value={p}>
                      {p}
                    </option>
                  ))}
                </select>
              </label>
              {(
                [
                  ["landscape", "Yön", "Yatay", "Dikey"],
                  ["toc", "İçindekiler", "Var", "Yok"],
                  ["cover", "Kapak", "Var", "Yok"],
                  ["page_numbers", "Sayfa no", "Var", "Yok"],
                ] as const
              ).map(([key, label, on, off]) => (
                <label className="field" key={key}>
                  {label}
                  <select value={triState(opts[key])} onChange={(e) => set(key, fromTri(e.target.value))}>
                    <option value="">Otomatik</option>
                    <option value="1">{on}</option>
                    <option value="0">{off}</option>
                  </select>
                </label>
              ))}
              <label className="field">
                Kenar (mm)
                <input
                  className="input narrow"
                  type="number"
                  min={0}
                  max={60}
                  placeholder="18"
                  value={opts.margin_mm ?? ""}
                  onChange={(e) => set("margin_mm", e.target.value === "" ? null : Number(e.target.value))}
                />
              </label>
              <label className="field">
                Yazı (pt)
                <input
                  className="input narrow"
                  type="number"
                  min={6}
                  max={24}
                  step={0.5}
                  placeholder="tema"
                  value={opts.font_size_pt ?? ""}
                  onChange={(e) => set("font_size_pt", e.target.value === "" ? null : Number(e.target.value))}
                />
              </label>
            </div>

            <div className="md-actions">
              <button type="button" className="link-button" onClick={() => setShowEditor((s) => !s)}>
                {showEditor ? "Düzenleyiciyi gizle" : "Düzenleyiciyi göster"}
              </button>
              <DropZone
                compact
                onFiles={onFiles}
                accept=".md,.markdown,.txt,.png,.jpg,.jpeg,.gif,.webp,.svg"
                disabled={uploading}
                title={uploading ? "Yükleniyor…" : "+ resim / başka not"}
              />
            </div>
            {attachments.length > 0 && (
              <ul className="chips" aria-label="Ekler">
                {attachments.map((a) => (
                  <li key={a.id}>
                    {a.name}
                    <button
                      type="button"
                      className="icon-button"
                      aria-label={`${a.name} çıkar`}
                      onClick={() => setAttachments((all) => all.filter((x) => x.id !== a.id))}
                    >
                      ×
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {showEditor && (
              <textarea
                className="md-editor"
                spellCheck={false}
                value={text}
                onChange={(e) => setText(e.target.value)}
                aria-label="Markdown metni"
              />
            )}
            <button
              type="button"
              className="primary block"
              disabled={job.running || browserMissing}
              onClick={() => {
                builtText.current = text;
                void job.start({
                  type: "md_to_pdf",
                  file: mdFile?.id,
                  text,
                  name: noteName,
                  attachments: attachmentIds,
                  options,
                });
              }}
            >
              {job.running ? "PDF oluşturuluyor…" : "PDF oluştur"}
            </button>
            <p className="md-save-line small">
              {dirty ? (
                <span className="warn-line">Kaydedilmemiş değişiklik var (taslak bu tarayıcıda tutuluyor).</span>
              ) : (
                <span className="muted">Değişiklik yok.</span>
              )}{" "}
              <button type="button" className="link-button" onClick={downloadNote}>
                Notu indir (.md)
              </button>
            </p>
            <JobPanel job={job.job} error={job.error} />
          </section>

          <section className="md-preview" aria-label="Önizleme">
            {previewError && <div className="banner error">{previewError}</div>}
            {preview && preview.warnings.length > 0 && (
              <details className="warnings">
                <summary>{preview.warnings.length} uyarı</summary>
                <ul>
                  {preview.warnings.map((w) => (
                    <li key={w}>{w}</li>
                  ))}
                </ul>
              </details>
            )}
            {/* Önizleme HTML'i içerik güvenlik politikası taşır: yalnızca sunucunun nonce verdiği
                KaTeX betikleri çalışır, notun içindeki betikler ve ağ istekleri engellenir. */}
            <PreviewFrame html={preview?.html ?? ""} />
          </section>
        </div>
      )}
    </>
  );
}
