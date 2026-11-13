import { useEffect, useRef, useState } from "react";
import type { FileMeta } from "../api";
import FilePicker, { FileRow } from "../components/FilePicker";
import JobPanel from "../components/JobPanel";
import PageHeader from "../components/PageHeader";
import PasswordDialog from "../components/PasswordDialog";
import { useFiles, useJob, useUnlockQueue } from "../hooks";
import { passwords } from "../passwords";
import { idsFrom, type Route } from "../router";
import { toast } from "../toast";
import { ACCEPT, PAPERS } from "../tools";

type LayoutMode = "nup" | "crop" | "poster" | "resize";
type Orientation = "otomatik" | "dikey" | "yatay";
type PerSheet = 1 | 2 | 4 | 6 | 9 | 16;
type CropMode = "auto" | "manual";

const MODES: { value: LayoutMode; label: string; hint: string }[] = [
  {
    value: "nup",
    label: "Çoklu Sayfa (N-up)",
    hint: "Birden fazla sayfayı ya da ders slaytını tek kağıda sığdır; istersen sağda not çizgileri aç.",
  },
  {
    value: "crop",
    label: "Kenar Kırpma",
    hint: "Boş kenarlıkları otomatik kırp veya üst, sağ, alt ve sol kenarlardan milimetre cinsinden kes.",
  },
  {
    value: "poster",
    label: "Poster Bölme",
    hint: "Büyük bir sayfayı sütun ve satırlara bölerek birden çok kağıda dağıt.",
  },
  {
    value: "resize",
    label: "Sayfa Boyutu",
    hint: "Tüm sayfaları seçilen kağıt boyutuna orantılı şekilde ortalayarak yeniden boyutlandır.",
  },
];

const PER_SHEET_OPTIONS: PerSheet[] = [1, 2, 4, 6, 9, 16];

function clampNum(raw: string, min: number, max: number, fallback: number, integer = false): number {
  const n = Number(raw);
  if (!Number.isFinite(n)) return fallback;
  const clamped = Math.min(max, Math.max(min, n));
  return integer ? Math.round(clamped) : clamped;
}

export default function LayoutTool({ route }: { route: Route }) {
  const initial = useFiles(idsFrom(route));
  const [file, setFile] = useState<FileMeta | null>(null);
  const [mode, setMode] = useState<LayoutMode>("nup");
  const [spec, setSpec] = useState("");
  const [paper, setPaper] = useState("A4");
  const [orientation, setOrientation] = useState<Orientation>("otomatik");
  const [perSheet, setPerSheet] = useState<PerSheet>(2);
  const [notesSide, setNotesSide] = useState(false);
  const [marginMm, setMarginMm] = useState(6);
  const [gapMm, setGapMm] = useState(4);
  const [border, setBorder] = useState(true);
  const [cropMode, setCropMode] = useState<CropMode>("auto");
  const [cropTopMm, setCropTopMm] = useState(0);
  const [cropRightMm, setCropRightMm] = useState(0);
  const [cropBottomMm, setCropBottomMm] = useState(0);
  const [cropLeftMm, setCropLeftMm] = useState(0);
  const [posterCols, setPosterCols] = useState(2);
  const [posterRows, setPosterRows] = useState(2);
  const [overlapMm, setOverlapMm] = useState(5);
  const job = useJob();
  const notifiedId = useRef<string | null>(null);

  const unlock = useUnlockQueue({
    onUnlock: ([accepted]) => {
      if (accepted) setFile(accepted);
    },
    onCancel: (cancelled) => {
      setFile((curr) => (curr?.id === cancelled.id ? null : curr));
    },
  });
  const queueUnlock = unlock.queue;

  useEffect(() => {
    const pdf = initial.files.find((f) => f.kind === "pdf");
    if (pdf) queueUnlock([pdf]);
  }, [initial.files, queueUnlock]);

  useEffect(() => {
    const current = job.job;
    if (current?.status === "bitti" && notifiedId.current !== current.id) {
      notifiedId.current = current.id;
      toast.ok("Sayfa düzeni hazır.");
    }
  }, [job.job]);

  const activeMode = MODES.find((m) => m.value === mode) ?? MODES[0];

  const start = () => {
    if (!file) return;
    void job.start({
      type: "layout",
      file: file.id,
      mode,
      spec,
      paper,
      orientation,
      per_sheet: perSheet,
      notes_side: notesSide,
      margin_mm: marginMm,
      gap_mm: gapMm,
      border,
      crop_mode: cropMode,
      crop_top_mm: cropTopMm,
      crop_right_mm: cropRightMm,
      crop_bottom_mm: cropBottomMm,
      crop_left_mm: cropLeftMm,
      poster_cols: posterCols,
      poster_rows: posterRows,
      overlap_mm: overlapMm,
      passwords: passwords.forFiles([file.id]),
    });
  };

  return (
    <>
      <PageHeader title="Sayfa Düzeni ve Yazdırma" />
      <div className="tool-layout">
        <section>
          {file ? (
            <FileRow file={file} onRemove={() => (setFile(null), job.reset())} />
          ) : (
            <FilePicker
              accept={ACCEPT.pdf}
              kind="pdf"
              multiple={false}
              title="Düzenlenecek PDF'i bırak"
              onAdd={([f]) => (setFile(f), job.reset())}
            />
          )}

          <div className="tabs layout-tabs" role="tablist" aria-label="Sayfa düzeni modları">
            {MODES.map((m) => (
              <button
                key={m.value}
                type="button"
                role="tab"
                aria-selected={mode === m.value}
                className={mode === m.value ? "on" : undefined}
                onClick={() => (setMode(m.value), job.reset())}
              >
                {m.label}
              </button>
            ))}
          </div>

          <p className="muted small layout-mode-hint">{activeMode.hint}</p>

          <div className="layout-card">
            {mode === "nup" && (
              <>
                <fieldset className="field plain">
                  <legend>Kağıt başına sayfa sayısı</legend>
                  <div className="segmented" role="group" aria-label="Kağıt başına sayfa sayısı">
                    {PER_SHEET_OPTIONS.map((n) => (
                      <button
                        key={n}
                        type="button"
                        className={perSheet === n ? "on" : undefined}
                        onClick={() => setPerSheet(n)}
                      >
                        {n}
                      </button>
                    ))}
                  </div>
                </fieldset>

                <label className="check">
                  <input
                    type="checkbox"
                    checked={notesSide}
                    onChange={(e) => setNotesSide(e.target.checked)}
                  />
                  <span>
                    <strong>Ders slaytı not alanı</strong>
                    <span className="muted small layout-check-sub">
                      Slaytları sol yarıya (%55) sıralar, sağ tarafta (%45) çizgili not alanı bırakır.
                    </span>
                  </span>
                </label>

                <div className="layout-grid-2">
                  <label className="field">
                    Kenar boşluğu (mm)
                    <input
                      className="input"
                      type="number"
                      min={0}
                      max={50}
                      step={1}
                      value={marginMm}
                      onChange={(e) => setMarginMm(clampNum(e.target.value, 0, 50, 6))}
                    />
                  </label>
                  <label className="field">
                    Sayfalar arası boşluk (mm)
                    <input
                      className="input"
                      type="number"
                      min={0}
                      max={30}
                      step={1}
                      value={gapMm}
                      onChange={(e) => setGapMm(clampNum(e.target.value, 0, 30, 4))}
                    />
                  </label>
                </div>

                <label className="check">
                  <input type="checkbox" checked={border} onChange={(e) => setBorder(e.target.checked)} />
                  <span>Her sayfa hücresinin etrafına ince çerçeve çiz</span>
                </label>
              </>
            )}

            {mode === "crop" && (
              <>
                <fieldset className="field plain">
                  <legend>Kırpma yöntemi</legend>
                  <div className="segmented" role="group" aria-label="Kırpma yöntemi">
                    <button
                      type="button"
                      className={cropMode === "auto" ? "on" : undefined}
                      onClick={() => setCropMode("auto")}
                    >
                      Otomatik (içeriğe göre)
                    </button>
                    <button
                      type="button"
                      className={cropMode === "manual" ? "on" : undefined}
                      onClick={() => setCropMode("manual")}
                    >
                      Elle (mm)
                    </button>
                  </div>
                </fieldset>

                {cropMode === "auto" ? (
                  <label className="field">
                    İçerik çevresinde bırakılacak pay (mm)
                    <input
                      className="input narrow"
                      type="number"
                      min={0}
                      max={50}
                      step={1}
                      value={marginMm}
                      onChange={(e) => setMarginMm(clampNum(e.target.value, 0, 50, 6))}
                    />
                  </label>
                ) : (
                  <div className="layout-grid-2">
                    <label className="field">
                      Üstten kes (mm)
                      <input
                        className="input"
                        type="number"
                        min={0}
                        max={150}
                        step={1}
                        value={cropTopMm}
                        onChange={(e) => setCropTopMm(clampNum(e.target.value, 0, 150, 0))}
                      />
                    </label>
                    <label className="field">
                      Sağdan kes (mm)
                      <input
                        className="input"
                        type="number"
                        min={0}
                        max={150}
                        step={1}
                        value={cropRightMm}
                        onChange={(e) => setCropRightMm(clampNum(e.target.value, 0, 150, 0))}
                      />
                    </label>
                    <label className="field">
                      Alttan kes (mm)
                      <input
                        className="input"
                        type="number"
                        min={0}
                        max={150}
                        step={1}
                        value={cropBottomMm}
                        onChange={(e) => setCropBottomMm(clampNum(e.target.value, 0, 150, 0))}
                      />
                    </label>
                    <label className="field">
                      Soldan kes (mm)
                      <input
                        className="input"
                        type="number"
                        min={0}
                        max={150}
                        step={1}
                        value={cropLeftMm}
                        onChange={(e) => setCropLeftMm(clampNum(e.target.value, 0, 150, 0))}
                      />
                    </label>
                  </div>
                )}
              </>
            )}

            {mode === "poster" && (
              <>
                <div className="layout-grid-2">
                  <label className="field">
                    Sütun sayısı (yatay parça)
                    <input
                      className="input"
                      type="number"
                      min={1}
                      max={6}
                      step={1}
                      value={posterCols}
                      onChange={(e) => setPosterCols(clampNum(e.target.value, 1, 6, 2, true))}
                    />
                  </label>
                  <label className="field">
                    Satır sayısı (dikey parça)
                    <input
                      className="input"
                      type="number"
                      min={1}
                      max={6}
                      step={1}
                      value={posterRows}
                      onChange={(e) => setPosterRows(clampNum(e.target.value, 1, 6, 2, true))}
                    />
                  </label>
                </div>
                <label className="field">
                  Yapıştırma bindirme payı (mm)
                  <input
                    className="input narrow"
                    type="number"
                    min={0}
                    max={40}
                    step={1}
                    value={overlapMm}
                    onChange={(e) => setOverlapMm(clampNum(e.target.value, 0, 40, 5))}
                  />
                </label>
                <p className="muted small layout-note">
                  Her kaynak sayfa {posterCols * posterRows} parçaya ({posterCols} × {posterRows}) bölünür.
                </p>
              </>
            )}

            {mode === "resize" && (
              <label className="field">
                Kenar boşluğu (mm)
                <input
                  className="input narrow"
                  type="number"
                  min={0}
                  max={50}
                  step={1}
                  value={marginMm}
                  onChange={(e) => setMarginMm(clampNum(e.target.value, 0, 50, 6))}
                />
              </label>
            )}
          </div>
        </section>

        <aside className="options">
          <h2>Seçenekler</h2>
          {mode !== "crop" && (
            <>
              <label className="field">
                Kağıt boyutu
                <select value={paper} onChange={(e) => setPaper(e.target.value)}>
                  {PAPERS.map((p) => (
                    <option key={p} value={p}>
                      {p}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                Yön
                <select value={orientation} onChange={(e) => setOrientation(e.target.value as Orientation)}>
                  <option value="otomatik">Otomatik</option>
                  <option value="dikey">Dikey</option>
                  <option value="yatay">Yatay</option>
                </select>
              </label>
            </>
          )}
          <label className="field">
            Sayfalar (isteğe bağlı)
            <input
              className="input"
              placeholder="hepsi (ör. 1-3, 5)"
              value={spec}
              onChange={(e) => setSpec(e.target.value)}
            />
          </label>
          <button type="button" className="primary block" disabled={!file || job.running} onClick={start}>
            {job.running ? "İşleniyor…" : "Uygula"}
          </button>
          <JobPanel
            job={job.job}
            error={job.error ?? initial.error}
            zipName={file ? `${file.name.replace(/\.pdf$/i, "")}_duzen` : undefined}
          />
        </aside>
      </div>
      {unlock.locked && <PasswordDialog file={unlock.locked} onDone={unlock.onDone} />}
    </>
  );
}
