import { api } from "./api";

const sleep = (ms: number) => new Promise((r) => window.setTimeout(r, ms));

/** Yeni adres (başka port = başka köken) yanıt veriyor mu? İçerik okunamaz (CORS yok), yalnızca
 * bağlantının kurulduğu anlaşılır; sunucu /api/health'i bunun için köken dışına açar. */
async function reachable(url: string): Promise<boolean> {
  try {
    await fetch(`${url}/api/health`, { mode: "no-cors", cache: "no-store" });
    return true;
  } catch {
    return false;
  }
}

/** Masaüstü uygulamasını yeni ayarlarla (port, telefon modu) yeniden başlatır; pencere açık kalır.
 * Yeni sunucu açılınca sayfa yeni adreste yeniden yüklenir. Sunucu aynı porttaysa yeni örneğin
 * açıldığı `instance` alanından anlaşılır (eski sunucu kapanmadan önce yanıt verebilir). */
export async function restartApp(timeoutMs = 60_000): Promise<void> {
  const before = await api.health().catch(() => null);
  const { url } = await api.restart();
  const sameOrigin = new URL(url).origin === window.location.origin;
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    await sleep(500);
    if (!sameOrigin && (await reachable(url))) {
      window.location.replace(`${url}/${window.location.hash}`);
      return;
    }
    // Aynı port ya da yeni port doluydu ve eski porta dönüldü.
    try {
      const h = await api.health();
      if (h.instance !== before?.instance) {
        window.location.reload();
        return;
      }
    } catch {
      /* sunucu henüz açılmadı */
    }
  }
  throw new Error("Uygulama yeniden açılamadı. Pencereyi kapatıp masaüstündeki simgeden yeniden aç.");
}
