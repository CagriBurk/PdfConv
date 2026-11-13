import { useEffect, useRef, useState } from "react";
import SignaturePad from "signature_pad";
import { api, errorMessage, type FileMeta } from "../api";
import Modal from "../components/Modal";

type Tab = "kayitli" | "ciz" | "yukle";

const INKS = [
  { value: "#111111", label: "Siyah" },
  { value: "#1d3fa8", label: "Mavi" },
];

interface Props {
  onPick: (sig: FileMeta) => void;
  onClose: () => void;
}

/** İmzalarım: kayıtlı imzalar, tuvale çizme ya da resim yükleme. Yeni imza kalıcı saklanır. */
export default function SignatureDialog({ onPick, onClose }: Props) {
  const [list, setList] = useState<FileMeta[] | null>(null);
  const [tab, setTab] = useState<Tab>("kayitli");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [ink, setInk] = useState(INKS[0].value);
  const [empty, setEmpty] = useState(true);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const padRef = useRef<SignaturePad | null>(null);

  useEffect(() => {
    api
      .signatures()
      .then((l) => {
        setList(l);
        if (!l.length) setTab("ciz");
      })
      .catch((e) => setError(errorMessage(e)));
  }, []);

  useEffect(() => {
    if (tab !== "ciz" || !canvasRef.current) return;
    const canvas = canvasRef.current;
    const ratio = window.devicePixelRatio || 1;
    const width = canvas.offsetWidth || 440;
    const height = canvas.offsetHeight || 160;
    canvas.width = width * ratio;
    canvas.height = height * ratio;
    canvas.getContext("2d")?.scale(ratio, ratio);
    const pad = new SignaturePad(canvas, { penColor: ink, minWidth: 0.8, maxWidth: 2.6 });
    pad.addEventListener("endStroke", () => setEmpty(pad.isEmpty()));
    padRef.current = pad;
    setEmpty(true);
    return () => {
      pad.off();
      padRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  useEffect(() => {
    if (padRef.current) padRef.current.penColor = ink;
  }, [ink]);

  const save = async (blob: Blob, name: string) => {
    setBusy(true);
    setError(null);
    try {
      const sig = await api.addSignature(blob, name);
      onPick(sig);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const saveDrawing = async () => {
    const pad = padRef.current;
    if (!pad || pad.isEmpty()) return;
    const blob = await (await fetch(pad.toDataURL("image/png"))).blob();
    await save(blob, "imza.png");
  };

  const remove = async (sig: FileMeta) => {
    if (!window.confirm(`“${sig.name}” silinsin mi?`)) return;
    try {
      await api.remove(sig.id);
      setList((l) => l?.filter((s) => s.id !== sig.id) ?? null);
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  return (
    <Modal title="İmza ekle" onClose={onClose} wide>
      <div className="tabs" role="tablist">
        {(
          [
            ["kayitli", `İmzalarım${list ? ` (${list.length})` : ""}`],
            ["ciz", "Çiz"],
            ["yukle", "Resimden yükle"],
          ] as [Tab, string][]
        ).map(([value, label]) => (
          <button
            key={value}
            type="button"
            role="tab"
            aria-selected={tab === value}
            className={tab === value ? "on" : undefined}
            onClick={() => setTab(value)}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "kayitli" &&
        (list?.length ? (
          <ul className="signature-grid">
            {list.map((s) => (
              <li key={s.id}>
                <button type="button" className="signature-tile" onClick={() => onPick(s)} title="Bu imzayı ekle">
                  <img src={api.rawUrl(s.id)} alt={s.name} />
                </button>
                <button type="button" className="link-button danger small" onClick={() => void remove(s)}>
                  Sil
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">{list ? "Henüz kayıtlı imza yok. Çiz ya da resimden yükle." : "Yükleniyor…"}</p>
        ))}

      {tab === "ciz" && (
        <>
          <canvas ref={canvasRef} className="signature-pad" aria-label="İmza çizim alanı" />
          <div className="modal-actions spread">
            <span className="tool-cluster">
              {INKS.map((i) => (
                <label key={i.value} className="check">
                  <input type="radio" name="ink" checked={ink === i.value} onChange={() => setInk(i.value)} />
                  {i.label}
                </label>
              ))}
              <button type="button" onClick={() => (padRef.current?.clear(), setEmpty(true))}>
                Temizle
              </button>
            </span>
            <button type="button" className="primary" disabled={empty || busy} onClick={() => void saveDrawing()}>
              Kaydet ve ekle
            </button>
          </div>
        </>
      )}

      {tab === "yukle" && (
        <>
          <p className="muted small">
            Beyaz kâğıda atılmış imzanın fotoğrafı ya da taraması. Kâğıt otomatik saydamlaştırılır, kenar boşlukları
            kırpılır.
          </p>
          <input
            type="file"
            accept=".png,.jpg,.jpeg,.webp,.heic,.heif,.bmp"
            disabled={busy}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void save(f, f.name);
              e.target.value = "";
            }}
          />
        </>
      )}

      <p className="muted small">İmzalar bu bilgisayarda kalıcı saklanır (otomatik temizlik silmez).</p>
      {error && <p className="error-text">{error}</p>}
    </Modal>
  );
}
