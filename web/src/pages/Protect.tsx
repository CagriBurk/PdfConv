import { useEffect, useState } from "react";
import type { FileMeta } from "../api";
import FilePicker, { FileRow, FilesCard, fileSummary } from "../components/FilePicker";
import JobPanel, { ActionCard } from "../components/JobPanel";
import PageHeader from "../components/PageHeader";
import PasswordDialog from "../components/PasswordDialog";
import { useFiles, useJob, useUnlockQueue } from "../hooks";
import { passwords } from "../passwords";
import { idsFrom, type Route } from "../router";
import { ACCEPT } from "../tools";

type Action = "encrypt" | "decrypt" | "clean_metadata" | "repair";

const ACTIONS: { value: Action; slug: string; label: string; hint: string }[] = [
  { value: "encrypt", slug: "sifrele", label: "Şifrele", hint: "AES-256 açılış şifresi ve izinler." },
  { value: "decrypt", slug: "sifre-kaldir", label: "Şifre kaldır", hint: "Şifresini bildiğin dosyadan şifreyi kaldırır." },
  { value: "clean_metadata", slug: "temizle", label: "Meta veri temizle", hint: "Yazar, program, XMP, gömülü dosyalar, JavaScript." },
  { value: "repair", slug: "onar", label: "Onar", hint: "Açılmayan ya da hatalı PDF'i yeniden yazar." },
];

const NOTES: Record<Action, string> = {
  encrypt:
    "Şifreler kaydedilmez; unutursan dosya açılamaz. İzin kısıtlarına her okuyucu uymaz, asıl koruma açılış şifresidir.",
  decrypt:
    "Şifreli dosyayı bırakınca şifresi sorulur. Şifre kırma yoktur; yalnızca açılış şifresi olmayan, kısıtlanmış dosyalarda kısıtlar kaldırılabilir — kendi dosyaların için.",
  clean_metadata: "Görünen içerik değişmez. Sonuçta neyin silindiği listelenir.",
  repair: "Önce qpdf'in onarımı, olmazsa MuPDF'in kurtarması denenir.",
};

export default function Protect({ route }: { route: Route }) {
  const initial = useFiles(idsFrom(route));
  const fromRoute = ACTIONS.find((a) => a.slug === route.query.get("islem"))?.value;
  const [action, setAction] = useState<Action>(fromRoute ?? "encrypt");
  const [file, setFile] = useState<FileMeta | null>(null);
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [owner, setOwner] = useState("");
  const [allow, setAllow] = useState({ print: true, copy: true, modify: true });
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

  const restricted = !(allow.print && allow.copy && allow.modify);
  const ownerClash = restricted && owner !== "" && owner === pw;
  const pwError =
    action === "encrypt" &&
    pw &&
    (pw.length < 4
      ? "En az 4 karakter."
      : pw2 && pw !== pw2
        ? "Şifreler aynı değil."
        : ownerClash
          ? "Sahip şifresi açılış şifresinden farklı olmalı; aynı olursa izin kısıtları uygulanmaz."
          : null);
  const ready = file && (action !== "encrypt" || (pw.length >= 4 && pw === pw2 && !ownerClash));

  const run = () => {
    if (!file) return;
    const base = { type: action, file: file.id, passwords: passwords.forFiles([file.id]) };
    void job.start(
      action === "encrypt"
        ? {
            ...base,
            user_password: pw,
            owner_password: owner || undefined,
            allow_print: allow.print,
            allow_copy: allow.copy,
            allow_modify: allow.modify,
          }
        : base,
    );
  };

  // Onar, açılamayan dosyalar içindir: şifre/bozukluk kontrolünü sunucu yapar.
  const picker = (
    <FilePicker
      accept={ACCEPT.pdf}
      kind="pdf"
      multiple={false}
      title="PDF'i bırak"
      onAdd={([f]) => (setFile(f), job.reset())}
    />
  );

  const label = ACTIONS.find((a) => a.value === action)?.label ?? "";

  return (
    <>
      <PageHeader title="Güvenlik ve bakım" />
      <div className="tool-layout">
        <div className="tool-main">
          <FilesCard title="Dosya">{file ? <FileRow file={file} onRemove={() => (setFile(null), job.reset())} /> : picker}</FilesCard>
          <section className="card">
            <fieldset className="radio-cards">
              <legend>İşlem</legend>
              {ACTIONS.map((a) => (
                <label key={a.value} className={`radio-card${action === a.value ? " on" : ""}`}>
                  <input
                    type="radio"
                    name="action"
                    checked={action === a.value}
                    onChange={() => (setAction(a.value), job.reset())}
                  />
                  <span className="radio-card-head">
                    <strong>{a.label}</strong>
                    <span className="radio-dot" aria-hidden="true" />
                  </span>
                  <span className="muted small">{a.hint}</span>
                </label>
              ))}
            </fieldset>
          </section>
          {action === "encrypt" && (
            <section className="card">
              <h2>Seçenekler</h2>
              <div className="fields">
                <label className="field">
                  Açılış şifresi
                  <input className="input" type="password" autoComplete="new-password" value={pw} onChange={(e) => setPw(e.target.value)} />
                </label>
                <label className="field">
                  Şifre (tekrar)
                  <input className="input" type="password" autoComplete="new-password" value={pw2} onChange={(e) => setPw2(e.target.value)} />
                </label>
              </div>
              {pwError && <p className="error-text">{pwError}</p>}
              <fieldset className="field plain checks">
                <legend>İzinler</legend>
                {(
                  [
                    ["print", "Yazdırma"],
                    ["copy", "Metin kopyalama"],
                    ["modify", "Düzenleme"],
                  ] as const
                ).map(([k, label]) => (
                  <label key={k} className="check">
                    <input type="checkbox" checked={allow[k]} onChange={(e) => setAllow({ ...allow, [k]: e.target.checked })} />
                    {label}
                  </label>
                ))}
              </fieldset>
              <label className="field">
                Sahip şifresi (isteğe bağlı)
                <input className="input" type="password" autoComplete="new-password" placeholder={restricted ? "boşsa rastgele üretilir" : "boşsa açılış şifresiyle aynı"} value={owner} onChange={(e) => setOwner(e.target.value)} />
              </label>
            </section>
          )}
        </div>
        <aside className="tool-side">
          <ActionCard
            rows={[
              ["Dosya", fileSummary(file)],
              ["İşlem", label],
            ]}
            note={NOTES[action]}
            label={label}
            disabled={!ready || job.running}
            busy={job.running}
            onRun={run}
          />
          <JobPanel job={job.job} error={job.error ?? initial.error} />
        </aside>
      </div>
      {unlock.locked && <PasswordDialog file={unlock.locked} onDone={unlock.onDone} />}
    </>
  );
}
