import { useEffect, useState } from "react";
import type { EnginesResponse, FileMeta } from "../api";
import FilePicker, { FileRow, FilesCard, filesSummary } from "../components/FilePicker";
import JobPanel, { ActionCard } from "../components/JobPanel";
import InstallLibreOffice from "../components/InstallLibreOffice";
import PageHeader from "../components/PageHeader";
import { useFiles, useJob } from "../hooks";
import { idsFrom, type Route } from "../router";
import { ACCEPT, commonConvertTargets, convertFamily, convertTargets, lowerExt, sameFormat } from "../tools";

const KINDS: FileMeta["kind"][] = ["image", "office"];

/** Hedef biçimin ekrandaki adı. */
export const TARGET_LABEL: Record<string, string> = {
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

// Bilgi kaybettiren hedefler için kısa uyarı.
const TARGET_HINT: Record<string, string> = {
  ".csv": "CSV'ye yalnız ilk çalışma sayfasının değerleri yazılır; biçim ve formüller kaybolur.",
  ".txt": "Düz metne yalnız yazı aktarılır; biçim, tablo düzeni ve resimler kaybolur.",
};

const FAMILY_NOUN: Record<string, string> = { image: "resim", word: "metin belgesi", sheet: "tablo", slides: "sunu" };

// Saydam alan taşıyabilen resimler: JPG'e giderken arka plan rengiyle doldurulur.
const MAY_HAVE_ALPHA = [".png", ".webp", ".gif", ".tif", ".tiff", ".heic", ".heif"];
const LOSSY = [".jpg", ".webp"];

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

interface Props {
  route: Route;
  engines: EnginesResponse | null;
  onEnginesChanged: () => void;
}

export default function Convert({ route, engines, onEnginesChanged }: Props) {
  const initial = useFiles(idsFrom(route));
  const [files, setFiles] = useState<FileMeta[]>([]);
  const [picked, setPicked] = useState("");
  const [quality, setQuality] = useState(90);
  const [background, setBackground] = useState("#ffffff");
  const job = useJob();
  const lo = engines?.engines.find((e) => e.key === "libreoffice");
  const needsLo = files.some((f) => f.kind === "office");

  const names = files.map((f) => f.name);
  const targets = commonConvertTargets(names);
  // Seçilen hedef dosyalarla uyuşmuyorsa ilk ortak hedef geçerlidir.
  const target = targets.includes(picked) ? picked : (targets[0] ?? "");
  const reason = noTargetReason(names);
  const already = alreadyNote(names, target);
  const lossy = LOSSY.includes(target);
  const alpha = target === ".jpg" && names.some((n) => MAY_HAVE_ALPHA.includes(lowerExt(n)));

  useEffect(() => {
    if (initial.files.length) setFiles(initial.files.filter((f) => KINDS.includes(f.kind)));
  }, [initial.files]);

  const run = () =>
    void job.start({
      type: "convert",
      files: files.map((f) => f.id),
      target,
      ...(lossy && { quality }),
      ...(alpha && { background }),
    });

  return (
    <>
      <PageHeader title="Biçim Dönüştür" />
      <div className="tool-layout">
        <div className="tool-main">
          {lo && !lo.ok && needsLo && (
            <div className="banner error">
              LibreOffice bulunamadı; Word, Excel ve PowerPoint dosyaları çevrilemez. Resimler çevrilebilir.
              {engines?.windows ? (
                <InstallLibreOffice onInstalled={onEnginesChanged} />
              ) : (
                lo.install_hint && <code className="small">{lo.install_hint}</code>
              )}
            </div>
          )}
          <FilesCard count={files.length} hint={files.length > 0 && "Her dosya ayrı çevrilir; adı korunur."}>
            {files.length > 0 && (
              <ul className="file-list">
                {files.map((f) => (
                  <li key={f.id}>
                    <FileRow file={f} onRemove={() => setFiles((all) => all.filter((x) => x.id !== f.id))} />
                  </li>
                ))}
              </ul>
            )}
            <FilePicker
              accept={ACCEPT.convert}
              kind={KINDS}
              compact={files.length > 0}
              title={files.length ? "Dosya ekle" : "Resim ya da Office dosyalarını bırak (JPG, PNG, HEIC, DOCX, XLSX, CSV, PPTX…)"}
              onAdd={(added) => setFiles((f) => [...f, ...added])}
            />
          </FilesCard>
          <section className="card">
            <h2>Seçenekler</h2>
            {!files.length ? (
              <p className="muted small">Dosya seçince çevrilebileceği biçimler burada çıkar.</p>
            ) : reason ? (
              <p className="banner warn" role="status">
                {reason}
              </p>
            ) : (
              <>
                <fieldset className="field plain">
                  <legend>Hedef biçim</legend>
                  <div className="segmented" role="group" aria-label="Hedef biçim">
                    {targets.map((t) => (
                      <button key={t} type="button" className={t === target ? "on" : undefined} aria-pressed={t === target} onClick={() => setPicked(t)}>
                        {TARGET_LABEL[t] ?? t}
                      </button>
                    ))}
                  </div>
                </fieldset>
                {already && <p className="muted small">{already}</p>}
                {TARGET_HINT[target] && <p className="muted small">{TARGET_HINT[target]}</p>}
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
                      <label className="field">
                        Arka plan rengi
                        <input type="color" value={background} onChange={(e) => setBackground(e.target.value)} />
                        <span className="small">JPG saydamlık taşımaz; saydam yerler bu renkle dolar.</span>
                      </label>
                    )}
                  </div>
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
            ]}
            note={
              needsLo
                ? "Office belgeleri LibreOffice ile çevrilir; karmaşık sayfalarda küçük düzen farkları olabilir. Uyumsuz ya da bozuk bir dosya diğerlerini durdurmaz; hata olarak bildirilir."
                : "Uyumsuz ya da bozuk bir dosya diğerlerini durdurmaz; hata olarak bildirilir."
            }
            label={job.running ? "Dönüştürülüyor…" : files.length > 1 ? `${files.length} dosyayı dönüştür` : "Dönüştür"}
            disabled={!files.length || !target || job.running}
            busy={job.running}
            onRun={run}
          />
          <JobPanel job={job.job} error={job.error ?? initial.error} zipName="donusturulenler" />
        </aside>
      </div>
    </>
  );
}
