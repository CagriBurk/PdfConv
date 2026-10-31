import { useState } from "react";
import { api, errorMessage, type FileMeta } from "../api";
import { passwords } from "../passwords";
import Modal from "./Modal";

interface Props {
  file: FileMeta;
  onDone: (ok: boolean) => void;
}

export default function PasswordDialog({ file, onDone }: Props) {
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.checkPassword(file.id, value);
      passwords.set(file.id, value);
      onDone(true);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal title="Şifreli PDF" onClose={() => onDone(false)}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <p>
          <strong>{file.name}</strong> şifreli. Açmak için şifresini gir. Şifre yalnızca bu sekmede
          tutulur, kaydedilmez.
        </p>
        <input
          type="password"
          autoFocus
          value={value}
          onChange={(e) => setValue(e.target.value)}
          aria-label="Şifre"
          className="input"
        />
        {error && <p className="error-text">{error}</p>}
        <div className="modal-actions">
          <button type="button" onClick={() => onDone(false)}>
            Vazgeç
          </button>
          <button type="submit" className="primary" disabled={busy || !value}>
            Aç
          </button>
        </div>
      </form>
    </Modal>
  );
}
