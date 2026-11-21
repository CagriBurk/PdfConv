import { useEffect, useState } from "react";
import type { EnginesResponse, FileMeta } from "../api";
import FilePicker, { FileRow, FilesCard, filesSummary } from "../components/FilePicker";
import InstallLibreOffice from "../components/InstallLibreOffice";
import JobPanel, { ActionCard } from "../components/JobPanel";
import PageHeader from "../components/PageHeader";
import PasswordDialog from "../components/PasswordDialog";
import SortableList from "../components/SortableList";
import { useFiles, useJob, useUnlockQueue } from "../hooks";
import { passwords } from "../passwords";
import { idsFrom, navigate, type Route } from "../router";
import { ACCEPT, commonConvertTargets, convertFamily, convertTargets, lowerExt, PAPERS, sameFormat } from "../tools";

const KINDS: FileMeta["kind"][] = ["image", "office", "html", "text", "pdf"];
const UNIVERSAL_ACCEPT = [ACCEPT.convert, ACCEPT.pdf, ".html,.htm,.txt"].join(",");

/** Hedef biçimin ekrandaki adı. */
export const TARGET_LABEL: Record<string, string> = {
  ".pdf": "PDF",
  ".jpg": "JPG",
  ".png": "PNG",
  ".webp": "WEBP",
  ".tiff": "TIFF",
  ".docx": "Word (.docx)",
  ".odt": "OpenDocument metin (.odt)",
  ".rtf": "RTF",
  ".txt": "Düz metin (.txt)",
  ".xlsx": "Excel (.xlsx)",
  ".ods": "OpenDocument tablo (.ods)",
  ".csv": "CSV",
  ".pptx": "PowerPoint (.pptx)",
  ".odp": "OpenDocument sunum (.odp)",
};

const BG_PRESETS = [
  { color: "#ffffff", label: "Beyaz" },
  { color: "#000000", label: "Siyah" },
  { color: "#f3f4f6", label: "Açık gri" },
];

// Bilgi kaybettiren hedefler için kısa uyarı.
const TARGET_HINT: Record<string, string> = {
  ".csv": "CSV'ye yalnız ilk çalışma sayfasının değerleri yazılır; biçim ve formüller kaybolur.",
  ".txt": "Düz metne yalnız yazı aktarılır; biçim, tablo düzeni ve resimler kaybolur.",
};

const FAMILY_NOUN: Record<string, string> = { image: "resim", word: "metin belgesi", sheet: "tablo", slides: "sunu" };

// Saydam alan taşıyabilen resimler: JPG'e giderken arka plan rengiyle doldurulur.
const MAY_HAVE_ALPHA = [".png", ".webp", ".gif", ".tif", ".tiff", ".heic", ".heif"];
const LOSSY = [".jpg", ".webp"];
const PDF_TARGETS = [".png", ".jpg", ".docx", ".xlsx"];

/** Ortak hedef çıkmadığında neden çıkmadığını söyler (yoksa null). */
export function noTargetReason(names: string[]): string | null {
  if (!names.length || commonConvertTargets(names).length) return null;
  const unsupported = names.filter((n) => !convertTargets(n).length);
  if (unsupported.length) return `Bu dosyalar dönüştürülemez: ${unsupported.join(", ")}. Listeden çıkar.`;
  // Kalan tek durum: farklı aileler (her ailede en az iki hedef olduğundan aile içinde hep ortak var).
  const nouns = [...new Set(names.map(convertFamily))].map((f) => FAMILY_NOUN[f ?? ""]).join(", ");
  return `Seçili dosyalar aynı biçime çevrilemez (${nouns}). Aynı türden dosyaları birlikte dönüştür.`;
}

/** Karışık seçimde zaten hedef biçimde olan dosyalar için not (yoksa null). */
export function alreadyNote(names: string[], target: string): string | null {
  const n = names.filter((x) => sameFormat(x) === target).length;
  if (!target || !n || n === names.length) return null;
  return `Zaten ${TARGET_LABEL[target] ?? target} olan ${n} dosya olduğu gibi alınır.`;
}

/** Evrensel hedef listesi: resim → resim/PDF, Office/HTML/TXT → aynı aile/PDF, tek PDF → resim/Word/Excel. */
export function universalTargets(files: Pick<FileMeta, "name" | "kind">[]): string[] {
  if (!files.length) return [];
  const all = (...kinds: FileMeta["kind"][]) => files.every((f) => kinds.includes(f.kind));
  const names = files.map((f) => f.name);
  if (all("pdf")) return files.length === 1 ? PDF_TARGETS : [];
  if (all("image")) return [...commonConvertTargets(names), ".pdf"];
  if (all("office", "html", "text")) {
    const common = all("office") ? commonConvertTargets(names) : [];
    return [...common, ".pdf"];
  }
  return [];
}

function universalNoTargetReason(files: FileMeta[]): string | null {
  if (!files.length || universalTargets(files).length) return null;
  if (files.every((f) => f.kind === "pdf") && files.length > 1) {
    return "PDF dönüştürme tek dosya içindir. Birden çok PDF'i birleştirmek için Birleştir aracını kullanabilirsin.";
  }
  return noTargetReason(files.map((f) => f.name)) ?? "Seçili dosyalar farklı türlerde; aynı türden dosyaları birlikte dönüştür.";
}

interface Props {
  route: Route;
  engines: EnginesResponse | null;
  onEnginesChanged: () => void;
}

export default function Convert({ route, engines, onEnginesChanged }: Props) {
  const initial = useFiles(idsFrom(route));
  const [files, setFiles] = useState<FileMeta[]>([]);
  const [picked, setPicked] = useState(() => route.query.get("hedef") ?? "");
  // Resim → resim
  const [quality, setQuality] = useState(90);
  const [background, setBackground] = useState("#ffffff");
  // Resim → PDF
  const [pageSize, setPageSize] = useState("A4");
  const [orientation, setOrientation] = useState("otomatik");
  const [margin, setMargin] = useState(0);
  // Office → PDF
  const [mergePdf, setMergePdf] = useState(false);
  const [pdfa, setPdfa] = useState(false);
  const [outName, setOutName] = useState("");
  // PDF → Resim / Word / Excel
  const [dpi, setDpi] = useState(150);
  const [spec, setSpec] = useState("");
  const [excelLayout, setExcelLayout] = useState("tek");
  const [excelNumbers, setExcelNumbers] = useState(true);

  const job = useJob();
  const lo = engines?.engines.find((e) => e.key === "libreoffice");

  const unlock = useUnlockQueue({
    onUnlock: (accepted) => setFiles((curr) => [...curr, ...accepted]),
    onCancel: (cancelled) => setFiles((curr) => curr.filter((f) => f.id !== cancelled.id)),
  });
  const queueUnlock = unlock.queue;

  useEffect(() => {
    const qTarget = route.query.get("hedef");
    if (qTarget) setPicked(qTarget);
  }, [route.query]);

  useEffect(() => {
    if (!initial.files.length) return;
    const valid = initial.files.filter((f) => KINDS.includes(f.kind));
    const pdfs = valid.filter((f) => f.kind === "pdf");
    const nonPdfs = valid.filter((f) => f.kind !== "pdf");
    setFiles(nonPdfs);
    if (pdfs.length) queueUnlock(pdfs);
  }, [initial.files, queueUnlock]);

  const names = files.map((f) => f.name);
  const allImages = files.length > 0 && files.every((f) => f.kind === "image");
  const allOfficeLike = files.length > 0 && files.every((f) => f.kind === "office" || f.kind === "html" || f.kind === "text");
  const singlePdf = files.length === 1 && files[0].kind === "pdf" ? files[0] : null;
  const multiPdf = files.length > 1 && files.every((f) => f.kind === "pdf");

  const targets = universalTargets(files);
  const target = targets.includes(picked) ? picked : (targets[0] ?? "");
  const reason = universalNoTargetReason(files);
  const already = target === ".pdf" || singlePdf ? null : alreadyNote(names, target);

  const isImgToImg = allImages && target !== ".pdf";
  const isImgToPdf = allImages && target === ".pdf";
  const isOfficeToPdf = allOfficeLike && target === ".pdf";
  const isPdfToImg = !!singlePdf && (target === ".png" || target === ".jpg");
  const isPdfToWord = !!singlePdf && target === ".docx";
  const isPdfToExcel = !!singlePdf && target === ".xlsx";

  const needsLo = files.some((f) => f.kind === "office");
  const lossy = isImgToImg && LOSSY.includes(target);
  const alpha = isImgToImg && target === ".jpg" && names.some((n) => MAY_HAVE_ALPHA.includes(lowerExt(n)));
  const sortable = (isImgToPdf && files.length > 1) || (isOfficeToPdf && mergePdf && files.length > 1);

  const run = () => {
    if (!files.length || !target) return;
    if (isImgToPdf) {
      void job.start({
        type: "images_to_pdf",
        files: files.map((f) => f.id),
        page_size: pageSize,
        orientation,
        margin_mm: margin,
        name: outName || undefined,
      });
      return;
    }
    if (isOfficeToPdf) {
      void job.start({
        type: "office_to_pdf",
        files: files.map((f) => f.id),
        merge: mergePdf,
        pdfa,
        name: outName || undefined,
      });
      return;
    }
    if (singlePdf && isPdfToImg) {
      void job.start({
        type: "pdf_to_images",
        file: singlePdf.id,
        dpi,
        fmt: target.slice(1),
        spec,
        passwords: passwords.forFiles([singlePdf.id]),
      });
      return;
    }
    if (singlePdf && isPdfToWord) {
      void job.start({
        type: "pdf_to_word",
        file: singlePdf.id,
        spec,
        passwords: passwords.forFiles([singlePdf.id]),
      });
      return;
    }
    if (singlePdf && isPdfToExcel) {
      void job.start({
        type: "pdf_to_excel",
        file: singlePdf.id,
        layout: excelLayout,
        numbers: excelNumbers,
        spec,
        passwords: passwords.forFiles([singlePdf.id]),
      });
      return;
    }
    void job.start({
      type: "convert",
      files: files.map((f) => f.id),
      target,
      ...(lossy && { quality }),
      ...(alpha && { background }),
    });
  };

  const sideNote = needsLo
    ? "Office belgeleri LibreOffice ile çevrilir; karmaşık sayfalarda küçük düzen farkları olabilir. Uyumsuz ya da bozuk bir dosya diğerlerini durdurmaz; hata olarak bildirilir."
    : singlePdf && (isPdfToWord || isPdfToExcel)
      ? "Taranmış (fotoğraf gibi) PDF'lerde metin yoktur; önce OCR ile metni tanıman gerekir."
      : isImgToPdf
        ? "Her resim bir sayfa olarak tek PDF'te birleştirilir. Sırayı listeden sürükleyerek değiştirebilirsin."
        : "Uyumsuz ya da bozuk bir dosya diğerlerini durdurmaz; hata olarak bildirilir.";

  const filesHint = !files.length
    ? undefined
    : sortable
      ? "Sırayı değiştirmek için dosyaları sürükle."
      : isImgToPdf
        ? "Her resim bir sayfa olur."
        : isOfficeToPdf && mergePdf
          ? "Tüm belgeler tek PDF'te birleştirilir."
          : singlePdf
            ? "Seçilen hedef biçime göre dönüştürülür."
            : "Her dosya ayrı çevrilir; adı korunur.";

  return (
    <>
      <PageHeader title="Biçim Dönüştür" />
      <div className="tool-layout">
        <div className="tool-main">
          {lo && !lo.ok && needsLo && (
            <div className="banner error">
              LibreOffice bulunamadı; Word, Excel ve PowerPoint dosyaları çevrilemez. Resimler ve PDF'ler çevrilebilir.
              {engines?.windows ? (
                <InstallLibreOffice onInstalled={onEnginesChanged} />
              ) : (
                lo.install_hint && <code className="small">{lo.install_hint}</code>
              )}
            </div>
          )}
          <FilesCard count={files.length} hint={filesHint}>
            {files.length > 0 &&
              (sortable ? (
                <SortableList
                  items={files}
                  getKey={(f) => f.id}
                  onChange={setFiles}
                  render={(f) => (
                    <FileRow draggable file={f} onRemove={() => (setFiles((all) => all.filter((x) => x.id !== f.id)), job.reset())} />
                  )}
                />
              ) : (
                <ul className="file-list">
                  {files.map((f) => (
                    <li key={f.id}>
                      <FileRow file={f} onRemove={() => (setFiles((all) => all.filter((x) => x.id !== f.id)), job.reset())} />
                    </li>
                  ))}
                </ul>
              ))}
            <FilePicker
              accept={UNIVERSAL_ACCEPT}
              kind={KINDS}
              compact={files.length > 0}
              title={files.length ? "Dosya ekle" : "PDF, resim ya da Office dosyalarını bırak (PDF, JPG, PNG, HEIC, DOCX, XLSX, PPTX…)"}
              onAdd={(added) => (setFiles((f) => [...f, ...added]), job.reset())}
            />
          </FilesCard>

          <section className="card">
            <h2>Seçenekler</h2>
            {!files.length ? (
              <p className="muted small">Dosya seçince çevrilebileceği tüm biçimler (PDF dahil) burada çıkar.</p>
            ) : reason ? (
              <div className="banner warn" role="status">
                <p style={{ margin: 0 }}>{reason}</p>
                {multiPdf && (
                  <p style={{ margin: "10px 0 0" }}>
                    <button type="button" className="small" onClick={() => navigate("birlestir", { dosya: files.map((f) => f.id) })}>
                      Birleştir aracında aç
                    </button>
                  </p>
                )}
              </div>
            ) : (
              <>
                <fieldset className="field plain">
                  <legend>Hedef biçim</legend>
                  <div className="segmented seg-track convert-targets" role="group" aria-label="Hedef biçim">
                    {targets.map((t) => (
                      <button
                        key={t}
                        type="button"
                        className={t === target ? "on" : undefined}
                        aria-pressed={t === target}
                        onClick={() => (setPicked(t), job.reset())}
                      >
                        {TARGET_LABEL[t] ?? t}
                      </button>
                    ))}
                  </div>
                </fieldset>
                {already && <p className="muted small">{already}</p>}
                {TARGET_HINT[target] && <p className="muted small">{TARGET_HINT[target]}</p>}

                {/* Resim → Resim seçenekleri */}
                {(lossy || alpha) && (
                  <div className="fields">
                    {lossy && (
                      <label className="field">
                        Kalite: {quality}
                        <input type="range" min={10} max={100} step={5} value={quality} onChange={(e) => setQuality(Number(e.target.value))} />
                        <span className="small">Düşük kalite daha küçük dosya verir.</span>
                      </label>
                    )}
                    {alpha && (
                      <div className="field">
                        <label htmlFor="conv-bg">Arka plan rengi</label>
                        <div className="color-control">
                          <input id="conv-bg" type="color" value={background} onChange={(e) => setBackground(e.target.value)} />
                          <span className="mono muted">{background.toUpperCase()}</span>
                          <span className="color-presets">
                            {BG_PRESETS.map((p) => (
                              <button
                                key={p.color}
                                type="button"
                                className={`small${background.toLowerCase() === p.color ? " on" : ""}`}
                                onClick={() => setBackground(p.color)}
                              >
                                {p.label}
                              </button>
                            ))}
                          </span>
                        </div>
                        <span className="small">JPG saydamlık taşımaz; saydam yerler bu renkle dolar.</span>
                      </div>
                    )}
                  </div>
                )}

                {/* Resim → PDF seçenekleri */}
                {isImgToPdf && (
                  <div className="fields">
                    <label className="field">
                      Sayfa boyutu
                      <select value={pageSize} onChange={(e) => setPageSize(e.target.value)}>
                        {PAPERS.map((p) => (
                          <option key={p} value={p}>
                            {p}
                          </option>
                        ))}
                        <option value="resim">Resmin kendi boyutu</option>
                      </select>
                    </label>
                    {pageSize !== "resim" && (
                      <label className="field">
                        Yön
                        <select value={orientation} onChange={(e) => setOrientation(e.target.value)}>
                          <option value="otomatik">Otomatik (resme göre)</option>
                          <option value="dikey">Dikey</option>
                          <option value="yatay">Yatay</option>
                        </select>
                      </label>
                    )}
                    {pageSize !== "resim" && (
                      <label className="field">
                        Kenar boşluğu: {margin} mm
                        <input type="range" min={0} max={30} value={margin} onChange={(e) => setMargin(Number(e.target.value))} />
                      </label>
                    )}
                    <label className="field">
                      Çıktı adı
                      <input className="input" placeholder="otomatik" value={outName} onChange={(e) => setOutName(e.target.value)} />
                    </label>
                  </div>
                )}

                {/* Office / HTML / TXT → PDF seçenekleri */}
                {isOfficeToPdf && (
                  <>
                    <label className="check">
                      <input type="checkbox" checked={mergePdf} onChange={(e) => setMergePdf(e.target.checked)} />
                      Hepsini tek PDF'te birleştir (her dosya için yer imi)
                    </label>
                    {mergePdf && (
                      <label className="field">
                        Çıktı adı
                        <input className="input" placeholder="otomatik" value={outName} onChange={(e) => setOutName(e.target.value)} />
                      </label>
                    )}
                    {needsLo && (
                      <label className="check">
                        <input type="checkbox" checked={pdfa} onChange={(e) => setPdfa(e.target.checked)} />
                        Arşiv için PDF/A (Office dosyaları)
                      </label>
                    )}
                  </>
                )}

                {/* PDF → PNG / JPG seçenekleri */}
                {isPdfToImg && (
                  <div className="fields">
                    <label className="field">
                      Çözünürlük
                      <select value={dpi} onChange={(e) => setDpi(Number(e.target.value))}>
                        <option value={72}>72 DPI (ekran, küçük)</option>
                        <option value={150}>150 DPI (önerilen)</option>
                        <option value={200}>200 DPI</option>
                        <option value={300}>300 DPI (baskı kalitesi)</option>
                      </select>
                    </label>
                    <label className="field">
                      Sayfalar
                      <input className="input" placeholder="hepsi (ör. 1-3, 5)" value={spec} onChange={(e) => setSpec(e.target.value)} />
                    </label>
                  </div>
                )}

                {/* PDF → Word / Excel seçenekleri */}
                {(isPdfToWord || isPdfToExcel) && (
                  <div className="fields">
                    <label className="field">
                      Sayfalar
                      <input className="input" placeholder="hepsi (ör. 1-3, 5)" value={spec} onChange={(e) => setSpec(e.target.value)} />
                    </label>
                    {isPdfToExcel && (
                      <label className="field">
                        Düzen
                        <select value={excelLayout} onChange={(e) => setExcelLayout(e.target.value)}>
                          <option value="tek">Hepsi tek sayfada</option>
                          <option value="ayri">Her tablo ayrı sayfada</option>
                        </select>
                      </label>
                    )}
                  </div>
                )}
                {isPdfToExcel && (
                  <label className="check">
                    <input type="checkbox" checked={excelNumbers} onChange={(e) => setExcelNumbers(e.target.checked)} />
                    Sayıları sayıya çevir (1.234,56 → toplanabilir sayı)
                  </label>
                )}
              </>
            )}
          </section>
        </div>
        <aside className="tool-side">
          <ActionCard
            rows={[
              ["Dosya", filesSummary(files)],
              ["Hedef", target ? TARGET_LABEL[target] : "—"],
              ...(isPdfToImg ? ([["Çözünürlük", `${dpi} DPI`]] as [string, string][]) : []),
            ]}
            note={sideNote}
            label={job.running ? "Dönüştürülüyor…" : files.length > 1 ? `${files.length} dosyayı dönüştür` : "Dönüştür"}
            disabled={!files.length || !target || job.running || (lo && !lo.ok && needsLo)}
            busy={job.running}
            done={job.job?.status === "bitti"}
            onRun={run}
          />
          <JobPanel job={job.job} error={job.error ?? initial.error} zipName="donusturulenler" />
        </aside>
      </div>
      {unlock.locked && <PasswordDialog file={unlock.locked} onDone={unlock.onDone} />}
    </>
  );
}
