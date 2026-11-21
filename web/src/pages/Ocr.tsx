import { useEffect, useState } from "react";
import { api, type EnginesResponse, type FileMeta } from "../api";
import FilePicker, { FileRow, FilesCard, fileSummary } from "../components/FilePicker";
import JobPanel, { ActionCard } from "../components/JobPanel";
import PageHeader from "../components/PageHeader";
import PasswordDialog from "../components/PasswordDialog";
import { useFiles, useJob, useUnlockQueue } from "../hooks";
import { passwords } from "../passwords";
import { idsFrom, type Route } from "../router";
import { ACCEPT } from "../tools";

type Mode = "skip" | "redo" | "force";

const MODES: { value: Mode; label: string; hint: string }[] = [
  { value: "skip", label: "Taranmış sayfalar", hint: "Metni olan sayfalar atlanır, bozulmaz. Önerilen." },
  { value: "redo", label: "Eski OCR'ı yenile", hint: "Önceki, kötü tanınmış metin katmanı değiştirilir." },
  { value: "force", label: "Zorla", hint: "Her sayfa resme çevrilip yeniden tanınır. Dosya büyüyebilir." },
];

export default function Ocr({ route, engines }: { route: Route; engines: EnginesResponse | null }) {
  const initial = useFiles(idsFrom(route));
  const [file, setFile] = useState<FileMeta | null>(null);
  const [hasText, setHasText] = useState<boolean | null>(null);
  const [mode, setMode] = useState<Mode>("skip");
  const [langs, setLangs] = useState<string[]>(["tur", "eng"]);
  const job = useJob();

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
    setHasText(null);
    if (!file || file.encrypted) return;
    api.info(file.id).then((i) => setHasText(i.has_text)).catch(() => undefined);
  }, [file]);

  const missing = engines?.engines.filter((e) => (e.key === "tesseract" || e.key === "ghostscript") && !e.ok) ?? [];
  const toggle = (l: string) => setLangs((ls) => (ls.includes(l) ? ls.filter((x) => x !== l) : [...ls, l]));

  const langNames = [langs.includes("tur") && "Türkçe", langs.includes("eng") && "İngilizce"].filter(Boolean).join(", ");

  return (
    <>
      <PageHeader title="OCR" />
      <div className="tool-layout">
        <div className="tool-main">
          {missing.length > 0 && (
            <div className="banner warn">
              Eksik motor: {missing.map((m) => m.name).join(", ")}. Ayarlar sayfasındaki kurulum komutuna bak.
            </div>
          )}
          <FilesCard title="Dosya">
            {file ? (
              <FileRow file={file} onRemove={() => (setFile(null), job.reset())} />
            ) : (
              <FilePicker accept={ACCEPT.pdf} kind="pdf" multiple={false} title="Taranmış PDF'i bırak" onAdd={([f]) => setFile(f)} />
            )}
            {hasText === true && mode === "skip" && (
              <p className="muted small card-hint">
                Bu PDF'te zaten metin var; metinli sayfalar atlanır. Hepsini yeniden tanımak için "Eski OCR'ı yenile"
                ya da "Zorla" seç.
              </p>
            )}
            {hasText === false && <p className="muted small card-hint">Bu PDF'te metin yok: taranmış görünüyor.</p>}
          </FilesCard>
          <section className="card">
            <fieldset className="radio-cards">
              <legend>Hangi sayfalar?</legend>
              {MODES.map((m) => (
                <label key={m.value} className={`radio-card${mode === m.value ? " on" : ""}`}>
                  <input type="radio" name="mode" checked={mode === m.value} onChange={() => setMode(m.value)} />
                  <span className="radio-card-head">
                    <strong>{m.label}</strong>
                    <span className="radio-dot" aria-hidden="true" />
                  </span>
                  <span className="muted small">{m.hint}</span>
                </label>
              ))}
            </fieldset>
          </section>
          <section className="card">
            <h2>Seçenekler</h2>
            <fieldset className="field plain checks">
              <legend>Diller</legend>
              <label className="check">
                <input type="checkbox" checked={langs.includes("tur")} onChange={() => toggle("tur")} />
                Türkçe
              </label>
              <label className="check">
                <input type="checkbox" checked={langs.includes("eng")} onChange={() => toggle("eng")} />
                İngilizce
              </label>
            </fieldset>
          </section>
        </div>
        <aside className="tool-side">
          <ActionCard
            rows={[
              ["Dosya", fileSummary(file)],
              ["Sayfalar", MODES.find((m) => m.value === mode)?.label],
              ["Diller", langNames || "—"],
            ]}
            note="Eğik taranmış sayfalar düzeltilir, yan duranlar döndürülür. Sayfa başına birkaç saniye sürer; iptal edilebilir."
            label="OCR başlat"
            disabled={!file || !langs.length || job.running || missing.some((m) => m.key === "tesseract")}
            busy={job.running}
            done={job.job?.status === "bitti"}
            onRun={() =>
              file &&
              void job.start({ type: "ocr", file: file.id, mode, langs, passwords: passwords.forFiles([file.id]) })
            }
          />
          <JobPanel job={job.job} error={job.error ?? initial.error} />
        </aside>
      </div>
      {unlock.locked && <PasswordDialog file={unlock.locked} onDone={unlock.onDone} />}
    </>
  );
}
