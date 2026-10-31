import { useEffect, useState } from "react";
import { api, type FileMeta, type FontInfo } from "../api";
import FilePicker, { FileRow } from "../components/FilePicker";
import JobPanel from "../components/JobPanel";
import PagePreview from "../components/PagePreview";
import PageHeader from "../components/PageHeader";
import { FONT_CSS } from "../fonts";
import { useFiles, useJob } from "../hooks";
import { passwords } from "../passwords";
import { idsFrom, type Route } from "../router";
import { ACCEPT } from "../tools";

const stem = (name: string) => name.replace(/\.pdf$/i, "");

export default function Watermark({ route }: { route: Route }) {
  const initial = useFiles(idsFrom(route));
  const [file, setFile] = useState<FileMeta | null>(null);
  const [mode, setMode] = useState<"text" | "image">("text");
  const [text, setText] = useState("TASLAK");
  const [image, setImage] = useState<FileMeta | null>(null);
  const [font, setFont] = useState("segoe");
  const [bold, setBold] = useState(true);
  const [size, setSize] = useState(72);
  const [color, setColor] = useState("#888888");
  const [opacity, setOpacity] = useState(0.2);
  const [angle, setAngle] = useState(45);
  const [layer, setLayer] = useState<"front" | "back">("front");
  const [scale, setScale] = useState(0.5);
  const [pages, setPages] = useState("");
  const [fonts, setFonts] = useState<FontInfo[]>([]);
  const job = useJob();

  useEffect(() => {
    const pdf = initial.files.find((f) => f.kind === "pdf");
    if (pdf) setFile(pdf);
  }, [initial.files]);

  useEffect(() => {
    api.fonts().then(setFonts).catch(() => undefined);
  }, []);

  const ready = file && (mode === "text" ? text.trim() : image);

  const start = () => {
    if (!file) return;
    const common = { type: "watermark", opacity, angle, layer, pages };
    const op =
      mode === "text" ? { ...common, text, font, bold, size, color } : { ...common, asset: image?.id, scale };
    void job.start({
      type: "apply",
      file: file.id,
      target: "new",
      name: `${stem(file.name)}_filigranli`,
      ops: [op],
      passwords: passwords.forFiles([file.id]),
    });
  };

  return (
    <>
      <PageHeader title="Filigran" />
      <div className="tool-layout">
        <section>
          {file ? (
            <FileRow file={file} onRemove={() => (setFile(null), job.reset())} />
          ) : (
            <FilePicker accept={ACCEPT.pdf} kind="pdf" multiple={false} title="Filigran eklenecek PDF'i bırak" onAdd={([f]) => setFile(f)} />
          )}
          {file && (
            <div className="preview-wrap">
              <PagePreview file={file} width={360}>
                {(s) =>
                  mode === "text" ? (
                    <span
                      className="wm-preview"
                      style={{
                        fontFamily: FONT_CSS[font],
                        fontWeight: bold ? 700 : 400,
                        fontSize: size * s,
                        color,
                        opacity,
                        transform: `translate(-50%, -50%) rotate(${-angle}deg)`,
                      }}
                    >
                      {text}
                    </span>
                  ) : image ? (
                    <img
                      className="wm-preview"
                      src={api.rawUrl(image.id)}
                      alt=""
                      style={{ width: `${scale * 100}%`, opacity, transform: `translate(-50%, -50%) rotate(${-angle}deg)` }}
                    />
                  ) : null
                }
              </PagePreview>
              <p className="muted small">İlk sayfanın yaklaşık önizlemesi.</p>
            </div>
          )}
        </section>
        <aside className="options">
          <div className="segmented" role="group" aria-label="Filigran türü">
            <button type="button" className={mode === "text" ? "on" : undefined} onClick={() => setMode("text")}>
              Yazı
            </button>
            <button type="button" className={mode === "image" ? "on" : undefined} onClick={() => setMode("image")}>
              Resim
            </button>
          </div>
          {mode === "text" ? (
            <>
              <label className="field">
                Yazı
                <input className="input" value={text} maxLength={200} onChange={(e) => setText(e.target.value)} />
              </label>
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
              <div className="field-row">
                <label className="field">
                  Boyut
                  <input className="input narrow" type="number" min={6} max={400} value={size} onChange={(e) => setSize(Number(e.target.value))} />
                </label>
                <label className="field">
                  Renk
                  <input type="color" value={color} onChange={(e) => setColor(e.target.value)} />
                </label>
                <label className="check">
                  <input type="checkbox" checked={bold} onChange={(e) => setBold(e.target.checked)} />
                  Kalın
                </label>
              </div>
            </>
          ) : (
            <>
              {image ? (
                <FileRow file={image} onRemove={() => setImage(null)} />
              ) : (
                <FilePicker accept={ACCEPT.images} kind="image" multiple={false} compact title="Filigran resmini bırak (PNG önerilir)" onAdd={([f]) => setImage(f)} />
              )}
              <label className="field">
                Genişlik: sayfanın %{Math.round(scale * 100)}
                <input type="range" min={0.1} max={1} step={0.05} value={scale} onChange={(e) => setScale(Number(e.target.value))} />
              </label>
            </>
          )}
          <label className="field">
            Opaklık %{Math.round(opacity * 100)}
            <input type="range" min={0.05} max={1} step={0.05} value={opacity} onChange={(e) => setOpacity(Number(e.target.value))} />
          </label>
          <label className="field">
            Açı (derece)
            <input className="input narrow" type="number" min={-180} max={180} value={angle} onChange={(e) => setAngle(Number(e.target.value))} />
          </label>
          <fieldset className="field plain">
            <legend>Konum</legend>
            <label className="check">
              <input type="radio" name="layer" checked={layer === "front"} onChange={() => setLayer("front")} />
              İçeriğin önünde
            </label>
            <label className="check">
              <input type="radio" name="layer" checked={layer === "back"} onChange={() => setLayer("back")} />
              Arkasında (taranmış sayfalarda görünmeyebilir)
            </label>
          </fieldset>
          <label className="field">
            Sayfalar (boş = hepsi)
            <input className="input" placeholder="1-3, 5, 8-" value={pages} onChange={(e) => setPages(e.target.value)} />
          </label>
          <button type="button" className="primary block" disabled={!ready || job.running} onClick={start}>
            Filigran ekle
          </button>
          <JobPanel job={job.job} error={job.error ?? initial.error} />
        </aside>
      </div>
    </>
  );
}
