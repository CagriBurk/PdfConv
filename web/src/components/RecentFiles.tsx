import { ArrowLeftRight, Download, FolderOpen, LayoutGrid } from "lucide-react";
import { useEffect, useState } from "react";
import { api, errorMessage, formatSize, type FileMeta } from "../api";
import { useJobActivity } from "../hooks";
import { convertTargets } from "../tools";
import Icon from "./Icon";

const LIMIT = 5;
// İmza kitaplığındaki resimler kullanıcının "dosyaları" değil (sunucu da ayrı listeler).
const SIGNATURE_TAG = "signature";

/** "3 dk önce", "dün", "12 Kas" gibi kısa zaman. */
export function ago(seconds: number, now = Date.now()): string {
  const diff = Math.max(0, now / 1000 - seconds);
  if (diff < 60) return "az önce";
  if (diff < 3600) return `${Math.floor(diff / 60)} dk önce`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} sa önce`;
  if (diff < 2 * 86400) return "dün";
  if (diff < 7 * 86400) return `${Math.floor(diff / 86400)} gün önce`;
  return new Date(seconds * 1000).toLocaleDateString("tr-TR", { day: "numeric", month: "short" });
}

/** Dosya türü rozetindeki kısa ad: uzantı (en çok 4 harf). */
function typeLabel(f: FileMeta): string {
  const ext = f.name.includes(".") ? f.name.split(".").pop()! : f.kind;
  return ext.slice(0, 4).toLocaleUpperCase("tr");
}

function retentionText(hours: number | undefined): string {
  if (!hours) return "Bir süre açılmayan dosyalar";
  return hours % 24 === 0 ? `${hours / 24} günden uzun süre açılmayan dosyalar` : `${hours} saatten uzun süre açılmayan dosyalar`;
}

/** Ana sayfadaki son dosyalar kartı (en yeniler üstte). Sunucu yoklanmaz: pencereye dönülünce,
 * bu oturumda başlatılan bir iş bitince ve `refreshKey` değişince (ana sayfadan yükleme) yenilenir. */
export default function RecentFiles({ retentionHours, refreshKey = 0 }: { retentionHours?: number; refreshKey?: number }) {
  const [files, setFiles] = useState<FileMeta[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [focusCount, setFocusCount] = useState(0);
  const { running, done, failed } = useJobActivity();

  useEffect(() => {
    const again = () => {
      if (document.visibilityState === "visible") setFocusCount((n) => n + 1);
    };
    window.addEventListener("focus", again);
    document.addEventListener("visibilitychange", again);
    return () => {
      window.removeEventListener("focus", again);
      document.removeEventListener("visibilitychange", again);
    };
  }, []);

  useEffect(() => {
    let alive = true;
    api
      .files()
      .then((all) => {
        if (!alive) return;
        const mine = all.filter((f) => f.tag !== SIGNATURE_TAG).sort((a, b) => b.updated - a.updated);
        setFiles(mine.slice(0, LIMIT));
        setError(null);
      })
      .catch((e) => alive && setError(errorMessage(e)));
    return () => {
      alive = false;
    };
  }, [refreshKey, focusCount, running, done, failed]);

  return (
    <section className="card recent" aria-labelledby="son-dosyalar">
      <div className="recent-head">
        <h2 id="son-dosyalar">Son dosyalar</h2>
        <a href="#/isler" className="text-link">
          Tümünü gör
        </a>
      </div>
      {error ? (
        <p className="recent-empty error-text">Son dosyalar alınamadı: {error}</p>
      ) : files === null ? (
        <p className="recent-empty muted">Yükleniyor…</p>
      ) : files.length === 0 ? (
        <div className="recent-empty-box">
          <span className="tile">
            <Icon icon={FolderOpen} size={19} />
          </span>
          <p className="muted">Henüz dosya yok. İlk dosyanı bırak; en son çalıştıkların burada görünür.</p>
        </div>
      ) : (
        <ul className="recent-list">
          {files.map((f) => {
            const canConvert = f.kind === "pdf" || f.kind === "image" || f.kind === "office" || convertTargets(f.name).length > 0;
            return (
              <li key={f.id} className="recent-row">
                <span className="ftype" aria-hidden="true">
                  {typeLabel(f)}
                </span>
                <div className="recent-text">
                  <p className="recent-name" title={f.name}>
                    {f.name}
                  </p>
                  <p className="recent-meta">
                    {[
                      formatSize(f.size),
                      f.page_count ? `${f.page_count} sayfa` : null,
                      ago(f.updated),
                      f.pinned ? "sabitlendi" : null,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </p>
                </div>
                {f.kind === "pdf" && (
                  <a className="icon-button" href={`#/duzenle/${f.id}`} aria-label={`${f.name} dosyasını düzenleyicide aç`} title="Düzenleyicide aç">
                    <Icon icon={LayoutGrid} />
                  </a>
                )}
                {canConvert && (
                  <a className="icon-button" href={`#/donustur?dosya=${encodeURIComponent(f.id)}`} aria-label={`${f.name} dosyasını dönüştür`} title="Biçim Dönüştür'de aç">
                    <Icon icon={ArrowLeftRight} />
                  </a>
                )}
                <a className="icon-button" href={api.downloadUrl(f.id)} aria-label={`${f.name} dosyasını indir`} title="İndir">
                  <Icon icon={Download} />
                </a>
              </li>
            );
          })}
        </ul>
      )}
      <p className="recent-note">
        {retentionText(retentionHours)} kendiliğinden silinir. Saklamak istediklerini İşler ve dosyalar ekranında sabitle.
      </p>
    </section>
  );
}
