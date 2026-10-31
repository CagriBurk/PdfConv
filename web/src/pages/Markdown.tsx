import { useEffect, useRef, useState } from "react";
import { api, errorMessage, type EnginesResponse, type FileMeta, type MdPreview } from "../api";
import DropZone from "../components/DropZone";
import JobPanel from "../components/JobPanel";
import PageHeader from "../components/PageHeader";
import { useJob, useUpload } from "../hooks";
import { idsFrom, type Route } from "../router";

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

/** Dosyayı metin olarak okur; satır sonlarını \n'e çevirir (Windows dosyaları \r\n içerir). */
const fetchText = (url: string) => fetch(url).then((r) => r.text()).then((t) => t.replace(/\r\n?/g, "\n"));

const triState = (v: boolean | null) => (v === null ? "" : v ? "1" : "0");
const fromTri = (v: string) => (v === "" ? null : v === "1");

export default function Markdown({ route, engines }: { route: Route; engines: EnginesResponse | null }) {
  const [mdFile, setMdFile] = useState<FileMeta | null>(null);
  const [attachments, setAttachments] = useState<FileMeta[]>([]);
  const [text, setText] = useState<string | null>(null);
  const [opts, setOpts] = useState<Override<Options>>(AUTO);
  const [preview, setPreview] = useState<MdPreview | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [showEditor, setShowEditor] = useState(true);
  const { upload, uploading, error: uploadError, setError } = useUpload();
  const job = useJob();
  const timer = useRef<number>(undefined);
  const browserMissing = engines?.engines.find((e) => e.key === "browser")?.ok === false;

  // URL'den gelen dosyalar (ana sayfadan yönlendirme ya da sayfa yenileme).
  const mainId = idsFrom(route)[0];
  const extraIds = idsFrom(route, "ek").join(",");
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        if (mainId) {
          const meta = await api.file(mainId);
          const body = await fetchText(api.rawUrl(mainId));
          if (!alive) return;
          setMdFile(meta);
          setText(body);
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

  // Yazdıkça önizleme (yarım saniye bekleyerek).
  useEffect(() => {
    if (text === null) return;
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(async () => {
      try {
        setPreview(await api.mdPreview(text, attachmentIds, options));
        setPreviewError(null);
      } catch (e) {
        setPreviewError(errorMessage(e));
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
      setMdFile(md);
      setText(await fetchText(api.rawUrl(md.id)));
      job.reset();
    }
    if (rest.length) setAttachments((a) => [...a, ...rest.filter((r) => !a.some((x) => x.name === r.name))]);
  };

  const set = <K extends keyof Options>(key: K, value: Options[K] | null) => setOpts((o) => ({ ...o, [key]: value }));
  const effective = preview?.options;

  return (
    <>
      <PageHeader title="Markdown → PDF">
        {mdFile && <span className="muted small">{mdFile.name}</span>}
      </PageHeader>
      {browserMissing && (
        <div className="banner error">Edge/Chrome bulunamadı; PDF oluşturulamaz. Ayarlar sayfasına bak.</div>
      )}

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
            <button type="button" className="link-button" onClick={() => setText(SAMPLE)}>
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
                  {["A4", "A5", "A3", "Letter", "Legal"].map((p) => (
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
              onClick={() =>
                job.start({
                  type: "md_to_pdf",
                  file: mdFile?.id,
                  text,
                  name: mdFile?.name ?? `${preview?.title ?? "belge"}.md`,
                  attachments: attachmentIds,
                  options,
                })
              }
            >
              {job.running ? "PDF oluşturuluyor…" : "PDF oluştur"}
            </button>
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
            <iframe title="Önizleme" sandbox="allow-scripts allow-same-origin" srcDoc={preview?.html ?? ""} />
          </section>
        </div>
      )}
    </>
  );
}
