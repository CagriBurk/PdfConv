import { useEffect, useState } from "react";
import { api, type EngineStatus, type EnginesResponse, type LanInfo } from "../api";

interface Props {
  data: EnginesResponse | null;
  refreshing: boolean;
  onRefresh: () => void;
}

function statusLabel(e: EngineStatus): { text: string; cls: string } {
  if (e.ok) return { text: "Hazır", cls: "ok" };
  if (e.available) return { text: "Eksik parça", cls: "warn" };
  return { text: "Kurulu değil", cls: "bad" };
}

function PhoneMode() {
  const [info, setInfo] = useState<LanInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api
      .lan()
      .then(setInfo)
      .catch((e: Error) => setError(e.message));
  }, []);

  if (error) return <p className="muted small">{error}</p>;
  if (!info) return null;
  if (!info.enabled) {
    return (
      <p className="muted small">
        Kapalı. Telefondan kullanmak için sunucuyu <code>baslat.bat --lan</code> ile başlat; burada bir QR kod
        çıkar. Telefon ve bilgisayar aynı Wi-Fi'de olmalı.
      </p>
    );
  }
  if (!info.urls?.length) return <p className="warn-line">Yerel ağ adresi bulunamadı. Wi-Fi'ye bağlı mısın?</p>;
  return (
    <div className="phone-mode">
      {info.qr_svg && (
        <img
          className="qr"
          alt="Telefonla bağlanmak için QR kod"
          src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(info.qr_svg)}`}
        />
      )}
      <div>
        <p>Telefonun kamerasıyla QR kodu okut ya da adresi yaz:</p>
        {info.urls.map((u) => (
          <p key={u} className="mono small break">
            {u}
          </p>
        ))}
        <p className="warn-line">
          Bu adresi bilen herkes dosyalarına erişebilir. Başkasıyla paylaşma; işin bitince sunucuyu kapat.
        </p>
      </div>
    </div>
  );
}

export default function Settings({ data, refreshing, onRefresh }: Props) {
  return (
    <>
      <h2>Telefon modu</h2>
      <PhoneMode />

      <div className="section-head">
        <h2>Motorlar</h2>
        <button type="button" onClick={onRefresh} disabled={refreshing}>
          {refreshing ? "Taranıyor…" : "Yeniden tara"}
        </button>
      </div>

      {!data ? (
        <p className="muted">Yükleniyor…</p>
      ) : (
        <div className="engine-list">
          {data.engines.map((e) => {
            const s = statusLabel(e);
            return (
              <article key={e.key} className="engine">
                <div className="engine-main">
                  <span className={`pill ${s.cls}`}>{s.text}</span>
                  <h3>{e.name}</h3>
                  <span className="mono muted">{e.version ?? "—"}</span>
                </div>
                <p className="muted">{e.needed_for}</p>
                {e.path && <p className="mono small">{e.path}</p>}
                {e.problems.map((p) => (
                  <p key={p} className="warn-line">
                    {p}
                  </p>
                ))}
                {!e.available && e.install_hint && (
                  <p className="small">
                    Kurulum: <code>{e.install_hint}</code>
                  </p>
                )}
              </article>
            );
          })}
        </div>
      )}

      {data && (
        <>
          <h2>Kütüphaneler</h2>
          <dl className="kv">
            {Object.entries(data.libraries).map(([k, v]) => (
              <div key={k}>
                <dt>{k}</dt>
                <dd className="mono">{v ?? "yok"}</dd>
              </div>
            ))}
          </dl>

          <h2>Klasörler</h2>
          <dl className="kv">
            <div>
              <dt>Veri klasörü</dt>
              <dd className="mono">{data.data_dir}</dd>
            </div>
            <div>
              <dt>Ayar dosyası</dt>
              <dd className="mono">{data.config_file ?? "yok (varsayılanlar kullanılıyor)"}</dd>
            </div>
            <div>
              <dt>Obsidian kasası</dt>
              <dd className="mono">
                {data.vault_path ?? "tanımlı değil (config.toml → vault_path; ![[resim]] aramak için)"}
              </dd>
            </div>
            <div>
              <dt>Günlük dosyası</dt>
              <dd className="mono">{data.log_file}</dd>
            </div>
            <div>
              <dt>Otomatik silme</dt>
              <dd>{data.retention_hours} saatten eski, sabitlenmemiş dosyalar</dd>
            </div>
          </dl>
        </>
      )}
    </>
  );
}
