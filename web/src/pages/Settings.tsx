import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  api,
  errorMessage,
  type EngineStatus,
  type EnginesResponse,
  type LanInfo,
  type SettingsResponse,
  type SettingsValues,
  type UpdateInfo,
} from "../api";
import InstallLibreOffice from "../components/InstallLibreOffice";
import { restartApp } from "../restart";
import { toast } from "../toast";

interface Props {
  data: EnginesResponse | null;
  refreshing: boolean;
  onRefresh: () => void;
  settings: SettingsResponse | null;
  onSettings: (s: SettingsResponse) => void;
  onShowWelcome: () => void;
}

const THEME_LABEL: Record<string, string> = { ders: "Ders notu", rapor: "Rapor", sade: "Sade" };
const RETENTION_PRESETS = [
  [6, "6 saat"],
  [24, "1 gün"],
  [72, "3 gün"],
  [168, "1 hafta"],
  [720, "30 gün"],
] as const;

function statusLabel(e: EngineStatus): { text: string; cls: string } {
  if (e.ok) return { text: "Hazır", cls: "ok" };
  if (e.available) return { text: "Eksik parça", cls: "warn" };
  return { text: "Kurulu değil", cls: "bad" };
}

/** Ayar kaydı + (gerekiyorsa) yeniden başlatma; hata bildirim olarak gösterilir. */
function useSave(onSettings: (s: SettingsResponse) => void) {
  const [busy, setBusy] = useState(false);
  const save = async (changes: Partial<SettingsValues>, okText = "Ayarlar kaydedildi.") => {
    setBusy(true);
    try {
      const s = await api.saveSettings(changes);
      onSettings(s);
      toast.ok(okText);
      return s;
    } catch (e) {
      toast.error(errorMessage(e));
      return null;
    } finally {
      setBusy(false);
    }
  };
  return { save, busy };
}

function RestartLine({ settings }: { settings: SettingsResponse }) {
  const [restarting, setRestarting] = useState(false);
  if (!settings.restart_pending) return null;
  if (!settings.restart_available) {
    return (
      <p className="warn-line" role="status">
        Bu değişiklik sunucu yeniden başlatılınca geçerli olur: sunucuyu kapatıp <code>baslat.bat</code> ile yeniden aç.
      </p>
    );
  }
  return (
    <p className="warn-line" role="status">
      Değişikliğin geçerli olması için uygulama yeniden başlamalı (pencere açık kalır, açık işler varsa bitmesini
      bekle).{" "}
      <button
        type="button"
        className="primary small"
        disabled={restarting}
        onClick={() => {
          setRestarting(true);
          restartApp().catch((e) => {
            setRestarting(false);
            toast.error(errorMessage(e));
          });
        }}
      >
        {restarting ? "Yeniden başlatılıyor…" : "Şimdi yeniden başlat"}
      </button>
    </p>
  );
}

function GeneralSettings({ settings, onSettings }: { settings: SettingsResponse; onSettings: Props["onSettings"] }) {
  const v = settings.values;
  const [retention, setRetention] = useState(String(v.retention_hours));
  const [vault, setVault] = useState(v.vault_path);
  const [theme, setTheme] = useState(v.default_theme);
  const [paper, setPaper] = useState(v.default_paper);
  const [picking, setPicking] = useState(false);
  const { save, busy } = useSave(onSettings);
  const hours = Number(retention);
  const retentionValid = Number.isInteger(hours) && hours >= 1 && hours <= 8760;
  const dirty =
    hours !== v.retention_hours || vault.trim() !== v.vault_path || theme !== v.default_theme || paper !== v.default_paper;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!retentionValid) return;
    const s = await save({ retention_hours: hours, vault_path: vault.trim(), default_theme: theme, default_paper: paper });
    if (s) setVault(s.values.vault_path);
  };

  const pick = async () => {
    setPicking(true);
    try {
      const r = await api.pickFolder(vault || undefined);
      if (r.path) setVault(r.path);
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setPicking(false);
    }
  };

  return (
    <form className="settings-form" onSubmit={submit} aria-labelledby="genel-baslik">
      <h2 id="genel-baslik">Genel</h2>
      <div className="setting-row">
        <label htmlFor="ayar-saklama">Dosyaları sakla</label>
        <div className="setting-control">
          <input
            id="ayar-saklama"
            className="input narrow"
            type="number"
            min={1}
            max={8760}
            value={retention}
            aria-describedby="ayar-saklama-not"
            aria-invalid={!retentionValid}
            onChange={(e) => setRetention(e.target.value)}
          />{" "}
          saat
          <span className="preset-row">
            {RETENTION_PRESETS.map(([h, label]) => (
              <button key={h} type="button" className="link-button" onClick={() => setRetention(String(h))}>
                {label}
              </button>
            ))}
          </span>
          <p id="ayar-saklama-not" className="muted small">
            Bu süreden uzun açılmamış, sabitlenmemiş dosyalar ve iş kayıtları silinir. Saklamak istediklerini İşler ve
            dosyalar'da sabitle.
          </p>
          {!retentionValid && <p className="error-text small">1 ile 8760 saat (1 yıl) arasında bir tam sayı yaz.</p>}
        </div>
      </div>

      <div className="setting-row">
        <label htmlFor="ayar-kasa">Obsidian kasası</label>
        <div className="setting-control">
          <div className="input-with-button">
            <input
              id="ayar-kasa"
              className="input"
              placeholder="Tanımlı değil"
              value={vault}
              aria-describedby="ayar-kasa-not"
              onChange={(e) => setVault(e.target.value)}
            />
            {settings.local && (
              <button type="button" onClick={() => void pick()} disabled={picking}>
                {picking ? "Pencere açık…" : "Klasör seç…"}
              </button>
            )}
            {vault && (
              <button type="button" className="link-button" onClick={() => setVault("")}>
                Kaldır
              </button>
            )}
          </div>
          <p id="ayar-kasa-not" className="muted small">
            Markdown → PDF'te <code>![[resim.png]]</code> resimleri kasanın her yerinde adıyla aranır. Yalnızca bu klasörün
            altı okunur.
          </p>
        </div>
      </div>

      <div className="setting-row">
        <label htmlFor="ayar-tema">Varsayılan tema</label>
        <div className="setting-control">
          <select id="ayar-tema" value={theme} onChange={(e) => setTheme(e.target.value)}>
            {settings.themes.map((t) => (
              <option key={t} value={t}>
                {THEME_LABEL[t] ?? t}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div className="setting-row">
        <label htmlFor="ayar-kagit">Varsayılan kağıt</label>
        <div className="setting-control">
          <select id="ayar-kagit" value={paper} onChange={(e) => setPaper(e.target.value)}>
            {settings.papers.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
          <p className="muted small">Markdown → PDF'te notun ön bilgisinde ya da ekranda seçilmemişse kullanılır.</p>
        </div>
      </div>
      <div className="form-actions">
        <button type="submit" className="primary" disabled={!dirty || !retentionValid || busy || !settings.local}>
          {busy ? "Kaydediliyor…" : "Kaydet"}
        </button>
        {!settings.local && <span className="muted small">Ayarlar yalnızca bilgisayarın kendisinden değiştirilebilir.</span>}
      </div>
    </form>
  );
}

function PhoneQr() {
  const [info, setInfo] = useState<LanInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const refresh = useCallback(() => {
    api
      .lan()
      .then(setInfo)
      .catch((e: Error) => setError(e.message));
  }, []);

  // QR kod tek kullanımlık: bir cihaz eşleşince yenisi çıkar, bağlı cihaz listesi de değişir.
  useEffect(() => {
    refresh();
    const timer = window.setInterval(refresh, 3000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  if (error) return <p className="muted small">{error}</p>;
  if (!info?.enabled) return null;
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
        <p className="muted small">Kod tek kullanımlık; her cihaz için yenisi çıkar.</p>
        {!!info.devices?.length && (
          <>
            <p>Bağlı cihazlar: {info.devices.map((d) => d.ip).join(", ")}</p>
            <button
              type="button"
              className="danger"
              onClick={() =>
                api
                  .revokeDevices()
                  .then(refresh)
                  .catch((e: Error) => setError(e.message))
              }
            >
              Hepsinin bağlantısını kes
            </button>
          </>
        )}
      </div>
    </div>
  );
}

function PhoneMode({ settings, onSettings }: { settings: SettingsResponse; onSettings: Props["onSettings"] }) {
  const { save, busy } = useSave(onSettings);
  const wanted = settings.values.lan;
  const running = settings.running.lan;
  return (
    <section aria-labelledby="telefon-baslik">
      <h2 id="telefon-baslik">Telefon modu</h2>
      <label className="check">
        <input
          type="checkbox"
          checked={wanted}
          disabled={busy || !settings.local}
          onChange={(e) =>
            void save({ lan: e.target.checked }, e.target.checked ? "Telefon modu açılacak." : "Telefon modu kapanacak.")
          }
        />
        Aynı Wi-Fi'deki telefon ve tabletler bu bilgisayardaki PDF Atölyesi'ni kullanabilsin
      </label>
      <p className="muted small">
        Açıkken uygulama yerel ağdan da erişilebilir; yalnızca burada gösterilen QR kodu okutan cihazlar bağlanır. Windows
        güvenlik duvarı ilk seferde izin isteyebilir ("Özel ağlar" yeterli). Bağlantı yerel ağda şifresizdir (HTTP):
        yalnızca güvendiğin Wi-Fi'de aç, işin bitince kapat.
      </p>
      <RestartLine settings={settings} />
      {running && <PhoneQr />}
    </section>
  );
}

function VersionInfo({ data }: { data: EnginesResponse }) {
  const [info, setInfo] = useState<UpdateInfo | null>(null);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const check = async () => {
    setChecking(true);
    setError(null);
    try {
      setInfo(await api.checkUpdate());
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setChecking(false);
    }
  };
  return (
    <>
      <div className="section-head">
        <h2>Sürüm</h2>
        <button type="button" onClick={() => void check()} disabled={checking}>
          {checking ? "Denetleniyor…" : "Güncellemeleri denetle"}
        </button>
      </div>
      <p>
        PDF Atölyesi <strong>{data.version}</strong>
        {data.installed ? " (masaüstü kurulumu)" : " (geliştirme)"}
      </p>
      <p className="muted small">
        Denetim yalnızca bu düğmeye basınca yapılır: GitHub'a tek bir istek gider, hiçbir dosya gönderilmez.
      </p>
      {error && <p className="error-text">{error}</p>}
      {info && (
        <p className={info.newer ? "warn-line" : "muted"}>
          {info.message}{" "}
          {info.newer && (
            <>
              <a href={info.url} target="_blank" rel="noreferrer">
                Sürüm sayfası
              </a>
              : yeni paketi indir, içindeki <strong>Kur</strong>'a çift tıkla (belgelerin ve ayarların korunur).
            </>
          )}
        </p>
      )}
    </>
  );
}

export function EngineList({ data, onRefresh }: { data: EnginesResponse; onRefresh: () => void }) {
  return (
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
            {e.problems.map((p) => (
              <p key={p} className="warn-line">
                {p}
              </p>
            ))}
            {!e.available && e.key === "libreoffice" && <InstallLibreOffice onInstalled={onRefresh} />}
            {!e.available && e.install_hint && (
              <p className="small">
                Elle kurulum: <code>{e.install_hint}</code>
              </p>
            )}
          </article>
        );
      })}
    </div>
  );
}

function PortSetting({ settings, onSettings }: { settings: SettingsResponse; onSettings: Props["onSettings"] }) {
  const [port, setPort] = useState(String(settings.values.port));
  const { save, busy } = useSave(onSettings);
  const n = Number(port);
  const valid = Number.isInteger(n) && n >= 1024 && n <= 65535;
  return (
    <form
      className="setting-row"
      onSubmit={(e) => {
        e.preventDefault();
        if (valid) void save({ port: n });
      }}
    >
      <label htmlFor="ayar-port">Port</label>
      <div className="setting-control">
        <input
          id="ayar-port"
          className="input narrow"
          type="number"
          min={1024}
          max={65535}
          value={port}
          aria-invalid={!valid}
          onChange={(e) => setPort(e.target.value)}
        />{" "}
        <button type="submit" disabled={!valid || n === settings.values.port || busy || !settings.local}>
          Kaydet
        </button>
        <p className="muted small">
          Şu an {settings.running.port} portunda çalışıyor. Masaüstü uygulaması port doluysa kendiliğinden boş bir port
          seçer; değiştirmen genellikle gerekmez.
        </p>
      </div>
    </form>
  );
}

export default function Settings({ data, refreshing, onRefresh, settings, onSettings, onShowWelcome }: Props) {
  return (
    <>
      {data && <VersionInfo data={data} />}
      {settings && <GeneralSettings key={settings.config_file} settings={settings} onSettings={onSettings} />}
      {settings && <PhoneMode settings={settings} onSettings={onSettings} />}

      <div className="section-head">
        <h2>Motorlar</h2>
        <button type="button" onClick={onRefresh} disabled={refreshing}>
          {refreshing ? "Taranıyor…" : "Yeniden tara"}
        </button>
      </div>
      {!data ? <p className="muted">Yükleniyor…</p> : <EngineList data={data} onRefresh={onRefresh} />}

      <p>
        <button type="button" className="link-button" onClick={onShowWelcome}>
          Tanıtımı yeniden göster
        </button>
      </p>

      {data && (
        <details className="advanced">
          <summary>Gelişmiş</summary>
          {settings && <PortSetting settings={settings} onSettings={onSettings} />}
          <h3>Klasörler</h3>
          <dl className="kv">
            <div>
              <dt>Veri klasörü</dt>
              <dd className="mono">{data.data_dir}</dd>
            </div>
            <div>
              <dt>Ayar dosyası</dt>
              <dd className="mono">{settings?.config_file ?? data.config_file ?? "—"}</dd>
            </div>
            <div>
              <dt>Günlük dosyası</dt>
              <dd className="mono">{data.log_file}</dd>
            </div>
            {data.install_dir && (
              <div>
                <dt>Kurulum klasörü</dt>
                <dd className="mono">{data.install_dir}</dd>
              </div>
            )}
          </dl>
          <h3>Motor yolları</h3>
          <dl className="kv">
            {data.engines.map((e) => (
              <div key={e.key}>
                <dt>{e.name}</dt>
                <dd className="mono">{e.path ?? "bulunamadı"}</dd>
              </div>
            ))}
          </dl>
          <h3>Kütüphaneler</h3>
          <dl className="kv">
            {Object.entries(data.libraries).map(([k, v]) => (
              <div key={k}>
                <dt>{k}</dt>
                <dd className="mono">{v ?? "yok"}</dd>
              </div>
            ))}
          </dl>
          <p className="muted small">
            Sınırlar ve motor yolları gibi diğer ayarlar ayar dosyasından değiştirilebilir (açıklamalı örnek:
            config.example.toml).
          </p>
        </details>
      )}
    </>
  );
}
