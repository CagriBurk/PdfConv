import { useEffect, useState } from "react";
import { api, type EnginesResponse, type FileMeta } from "../api";
import FilePicker, { FileRow } from "../components/FilePicker";
import JobPanel from "../components/JobPanel";
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

  return (
    <>
      <PageHeader title="OCR — aranabilir PDF" />
      {missing.length > 0 && (
        <div className="banner warn">
          Eksik motor: {missing.map((m) => m.name).join(", ")}. Ayarlar sayfasındaki kurulum komutuna bak.
        </div>
      )}
      <div className="tool-layout">
        <section>
          {file ? (
            <FileRow file={file} onRemove={() => (setFile(null), job.reset())} />
          ) : (
            <FilePicker accept={ACCEPT.pdf} kind="pdf" multiple={false} title="Taranmış PDF'i bırak" onAdd={([f]) => setFile(f)} />
          )}
          {hasText === true && mode === "skip" && (
            <p className="muted small">
              Bu PDF'te zaten metin var; metinli sayfalar atlanır. Hepsini yeniden tanımak için "Eski OCR'ı yenile"
              ya da "Zorla" seç.
            </p>
          )}
          {hasText === false && <p className="muted small">Bu PDF'te metin yok: taranmış görünüyor.</p>}
          <fieldset className="radio-cards">
            <legend>Hangi sayfalar?</legend>
            {MODES.map((m) => (
              <label key={m.value} className={`radio-card${mode === m.value ? " on" : ""}`}>
                <input type="radio" name="mode" checked={mode === m.value} onChange={() => setMode(m.value)} />
                <strong>{m.label}</strong>
                <span className="muted small">{m.hint}</span>
              </label>
            ))}
          </fieldset>
        </section>
        <aside className="options">
          <fieldset className="field plain">
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
          <p className="muted small">
            Eğik taranmış sayfalar düzeltilir, yan duranlar döndürülür. Sayfa başına birkaç saniye sürer; iptal
            edilebilir.
          </p>
          <button
            type="button"
            className="primary block"
            disabled={!file || !langs.length || job.running || missing.some((m) => m.key === "tesseract")}
            onClick={() =>
              file &&
              void job.start({ type: "ocr", file: file.id, mode, langs, passwords: passwords.forFiles([file.id]) })
            }
          >
            OCR başlat
          </button>
          <JobPanel job={job.job} error={job.error ?? initial.error} />
        </aside>
      </div>
      {unlock.locked && <PasswordDialog file={unlock.locked} onDone={unlock.onDone} />}
    </>
  );
}
