import { useEffect, useState } from "react";
import { api, type FileMeta, type FontInfo } from "../api";
import FilePicker, { FileRow } from "../components/FilePicker";
import JobPanel from "../components/JobPanel";
import PagePreview from "../components/PagePreview";
import PageHeader from "../components/PageHeader";
import { FONT_CSS, loadBundledFonts } from "../fonts";
import { useFiles, useJob } from "../hooks";
import { passwords } from "../passwords";
import { idsFrom, type Route } from "../router";
import { ACCEPT } from "../tools";

type Position = "top-left" | "top-center" | "top-right" | "bottom-left" | "bottom-center" | "bottom-right";

const POSITIONS: { value: Position; label: string }[] = [
  { value: "top-left", label: "Üst sol" },
  { value: "top-center", label: "Üst orta" },
  { value: "top-right", label: "Üst sağ" },
  { value: "bottom-left", label: "Alt sol" },
  { value: "bottom-center", label: "Alt orta" },
  { value: "bottom-right", label: "Alt sağ" },
];
const FORMATS = ["{n}", "Sayfa {n}", "{n} / {N}", "Sayfa {n} / {N}", "- {n} -"];

const stem = (name: string) => name.replace(/\.pdf$/i, "");

export default function PageNumbers({ route }: { route: Route }) {
  const initial = useFiles(idsFrom(route));
  const [file, setFile] = useState<FileMeta | null>(null);
  const [format, setFormat] = useState("Sayfa {n} / {N}");
  const [position, setPosition] = useState<Position>("bottom-center");
  const [start, setStart] = useState(1);
  const [skipFirst, setSkipFirst] = useState(false);
  const [pages, setPages] = useState("");
  const [font, setFont] = useState("noto-sans");
  const [size, setSize] = useState(11);
  const [color, setColor] = useState("#333333");
  const [margin, setMargin] = useState(28);
  const [fonts, setFonts] = useState<FontInfo[]>([]);
  const job = useJob();

  useEffect(() => {
    const pdf = initial.files.find((f) => f.kind === "pdf");
    if (pdf) setFile(pdf);
  }, [initial.files]);

  useEffect(() => {
    // Gömülü fontlar yüklenmeden çizilen önizleme yedek fonta düşerdi.
    Promise.all([api.fonts(), loadBundledFonts()])
      .then(([f]) => setFonts(f))
      .catch(() => undefined);
  }, []);

  const validFormat = format.includes("{n}");
  const total = file?.page_count ? file.page_count - (skipFirst ? 1 : 0) : 0;
  // Önizleme: numara alacak ilk sayfa (kapak atlanıyorsa ikinci sayfa).
  const previewPage = skipFirst && (file?.page_count ?? 0) > 1 ? 1 : 0;
  const label = format.replaceAll("{n}", String(start)).replaceAll("{N}", String(start + Math.max(total, 1) - 1));

  const run = () => {
    if (!file) return;
    void job.start({
      type: "apply",
      file: file.id,
      target: "new",
      name: `${stem(file.name)}_numarali`,
      ops: [{ type: "page_numbers", format, position, start, skip_first: skipFirst, pages, font, size, color, margin }],
      passwords: passwords.forFiles([file.id]),
    });
  };

  const [vertical, horizontal] = position.split("-");
  return (
    <>
      <PageHeader title="Sayfa Numarası" />
      <div className="tool-layout">
        <section>
          {file ? (
            <FileRow file={file} onRemove={() => (setFile(null), job.reset())} />
          ) : (
            <FilePicker accept={ACCEPT.pdf} kind="pdf" multiple={false} title="Numaralanacak PDF'i bırak" onAdd={([f]) => setFile(f)} />
          )}
          {file && (
            <div className="preview-wrap">
              <PagePreview file={file} page={previewPage} width={360}>
                {(s) => (
                  <span
                    className="pn-preview"
                    style={{
                      fontFamily: FONT_CSS[font],
                      fontSize: size * s,
                      color,
                      [vertical]: margin * s,
                      ...(horizontal === "center"
                        ? { left: "50%", transform: "translateX(-50%)" }
                        : { [horizontal]: margin * s }),
                    }}
                  >
                    {label}
                  </span>
                )}
              </PagePreview>
              <p className="muted small">{previewPage + 1}. sayfanın önizlemesi.</p>
            </div>
          )}
        </section>
        <aside className="options">
          <label className="field">
            Biçim
            <input className="input" list="pn-formats" value={format} onChange={(e) => setFormat(e.target.value)} />
            <datalist id="pn-formats">
              {FORMATS.map((f) => (
                <option key={f} value={f} />
              ))}
            </datalist>
            <span className="small">{"{n}"} = sayfa numarası, {"{N}"} = toplam</span>
          </label>
          {!validFormat && <p className="error-text">Biçimde {"{n}"} olmalı.</p>}
          <fieldset className="field plain">
            <legend>Konum</legend>
            <div className="position-grid">
              {POSITIONS.map((p) => (
                <button
                  key={p.value}
                  type="button"
                  className={position === p.value ? "on" : undefined}
                  aria-pressed={position === p.value}
                  onClick={() => setPosition(p.value)}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </fieldset>
          <div className="field-row">
            <label className="field">
              İlk numara
              <input className="input narrow" type="number" min={0} value={start} onChange={(e) => setStart(Math.max(0, Number(e.target.value)))} />
            </label>
            <label className="field">
              Kenar (pt)
              <input className="input narrow" type="number" min={0} max={300} value={margin} onChange={(e) => setMargin(Number(e.target.value))} />
            </label>
          </div>
          <label className="check">
            <input type="checkbox" checked={skipFirst} onChange={(e) => setSkipFirst(e.target.checked)} />
            İlk sayfayı atla (kapak): numaralama ikinci sayfadan başlar
          </label>
          <label className="field">
            Sayfalar (boş = hepsi)
            <input className="input" placeholder="1-3, 5, 8-" value={pages} onChange={(e) => setPages(e.target.value)} />
          </label>
          <div className="field-row">
            <label className="field">
              Font
              <select className="input" value={font} onChange={(e) => setFont(e.target.value)}>
                {fonts.map((f) => (
                  <option key={f.key} value={f.key}>
                    {f.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              Boyut
              <input className="input narrow" type="number" min={4} max={72} value={size} onChange={(e) => setSize(Number(e.target.value))} />
            </label>
            <label className="field">
              Renk
              <input type="color" value={color} onChange={(e) => setColor(e.target.value)} />
            </label>
          </div>
          <button type="button" className="primary block" disabled={!file || !validFormat || job.running} onClick={run}>
            Numaraları ekle
          </button>
          <JobPanel job={job.job} error={job.error ?? initial.error} />
        </aside>
      </div>
    </>
  );
}
